"""Deterministic post-processing for Docling table blocks.

The processor keeps physical blocks intact for provenance, then records logical
table membership in ``ContentBlock.relations`` and emits a logical-table view
for downstream structure-aware chunking.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from .models import ContentBlock


_IDENTIFIER_PATTERN = r"(?:\d+(?:\.\d+)*[A-Za-z]?|[A-Za-z]+\.?\d+(?:\.\d+)*[A-Za-z]?)"
_LABEL_RE = re.compile(
    rf"\b(Table|Figure|Fig\.?)\s+({_IDENTIFIER_PATTERN})\s*[:.]",
    re.IGNORECASE,
)


@dataclass
class LogicalTable:
    table_id: str
    label: Optional[str]
    number: Optional[int]
    caption: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    section_path: List[str]
    source_block_ids: List[str]
    caption_block_ids: List[str]
    text: str
    status: str
    warnings: List[str] = field(default_factory=list)
    identifier: Optional[str] = None


@dataclass
class TablePostProcessResult:
    blocks: List[ContentBlock]
    tables: List[LogicalTable]
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Label:
    kind: str
    identifier: str
    number: Optional[int]
    start: int
    end: int


@dataclass
class _TableGroup:
    table_indexes: List[int]
    caption_indexes: List[int]
    identifier: Optional[str]


class TablePostProcessor:
    """Recover logical table relationships using labels and local adjacency."""

    def process(self, blocks: Sequence[ContentBlock]) -> TablePostProcessResult:
        processed = [
            replace(block, relations=copy.deepcopy(block.relations)) for block in blocks
        ]
        positions = {block.block_id: index for index, block in enumerate(processed)}
        captions = {
            index: _leading_label(block.text)
            for index, block in enumerate(processed)
            if block.type == "caption"
        }
        captions = {index: label for index, label in captions.items() if label}

        warnings: List[str] = []
        self._retype_figures(processed, captions)

        table_indexes = [
            index for index, block in enumerate(processed) if block.type == "table"
        ]
        occurrences = {
            index: _labels(block.text, kind="table")
            for index, block in enumerate(processed)
            if block.type == "table"
        }
        leading_labels = {
            index: _leading_label(block.text)
            for index, block in enumerate(processed)
            if block.type == "table"
        }
        assignments: Dict[int, Optional[str]] = {}
        table_warnings: Dict[int, List[str]] = {index: [] for index in table_indexes}
        collision_caption_targets: Dict[int, int] = {}

        # Docling can prepend the next table's caption to the current table's
        # malformed grid. If that caption is repeated as the next block and is
        # followed by an unlabeled table, assign the repeated caption forward
        # and recover the embedded label for the current table.
        for index in table_indexes:
            labels = occurrences[index]
            leading = leading_labels.get(index)
            assignments[index] = (
                leading.identifier
                if leading is not None and leading.kind == "table"
                else None
            )
            distinct = list(dict.fromkeys(label.identifier for label in labels))
            if len(distinct) < 2:
                continue
            next_caption = captions.get(index + 1)
            next_table_labels = occurrences.get(index + 2, [])
            if (
                next_caption
                and next_caption.kind == "table"
                and next_caption.identifier == distinct[0]
                and index + 2 in occurrences
                and not next_table_labels
                and _same_page(processed[index], processed[index + 2])
            ):
                assignments[index] = distinct[1]
                assignments[index + 2] = distinct[0]
                collision_caption_targets[index + 1] = index + 2
                table_warnings[index].append("caption_collision")
                warnings.append(
                    f"{processed[index].block_id}: recovered Table {distinct[1]} "
                    f"from a caption collision with Table {distinct[0]}"
                )

        target_candidates: List[Tuple[int, int, bool]] = [
            (caption_index, target, True)
            for caption_index, target in collision_caption_targets.items()
        ]
        for caption_index, label in captions.items():
            if label.kind != "table" or caption_index in collision_caption_targets:
                continue
            target = self._find_caption_target(
                caption_index,
                label.identifier,
                processed,
                table_indexes,
                occurrences,
                assignments,
            )
            if target is None:
                warnings.append(
                    f"{processed[caption_index].block_id}: no table matched "
                    f"Table {label.identifier} caption"
                )
                continue
            target_candidates.append((caption_index, target, False))

        # A physical table has only one primary caption. Collision-recovery
        # assignments take precedence, then the nearest caption wins.
        caption_targets: Dict[int, int] = {}
        claimed_targets: Dict[int, int] = {}
        target_candidates.sort(
            key=lambda item: (
                not item[2],
                abs(item[0] - item[1]),
                item[0],
            )
        )
        for caption_index, target, _is_collision in target_candidates:
            if target in claimed_targets:
                warnings.append(
                    f"{processed[caption_index].block_id}: caption target already owned by "
                    f"{processed[claimed_targets[target]].block_id}"
                )
                continue
            caption_targets[caption_index] = target
            claimed_targets[target] = caption_index
            assignments[target] = captions[caption_index].identifier

        reserved_targets = {
            target: caption_index for caption_index, target in caption_targets.items()
        }
        table_owner: Dict[int, int] = {}
        caption_members: Dict[int, List[int]] = {}
        for caption_index, target in sorted(caption_targets.items()):
            identifier = captions[caption_index].identifier
            members = _caption_owned_table_indexes(
                caption_index=caption_index,
                target_index=target,
                identifier=identifier,
                blocks=processed,
                table_indexes=table_indexes,
                assignments=assignments,
                reserved_targets=reserved_targets,
                leading_labels=leading_labels,
            )
            owned_members = []
            for member in members:
                existing_owner = table_owner.get(member)
                if existing_owner is not None:
                    warnings.append(
                        f"{processed[member].block_id}: table already owned by "
                        f"{processed[existing_owner].block_id}"
                    )
                    continue
                table_owner[member] = caption_index
                assignments[member] = identifier
                owned_members.append(member)
            if owned_members:
                caption_members[caption_index] = owned_members

        groups: List[_TableGroup] = [
            _TableGroup(
                table_indexes=members,
                caption_indexes=[caption_index],
                identifier=captions[caption_index].identifier,
            )
            for caption_index, members in caption_members.items()
        ]

        # Without a caption, only directly adjacent blocks with the same full
        # identifier may be merged. Anonymous tables remain independent.
        unowned_group: Optional[_TableGroup] = None
        for index in table_indexes:
            if index in table_owner:
                unowned_group = None
                continue
            identifier = assignments.get(index)
            can_continue = (
                identifier is not None
                and unowned_group is not None
                and unowned_group.identifier == identifier
                and unowned_group.table_indexes[-1] + 1 == index
            )
            if can_continue:
                unowned_group.table_indexes.append(index)
                continue
            unowned_group = _TableGroup(
                table_indexes=[index],
                caption_indexes=[],
                identifier=identifier,
            )
            groups.append(unowned_group)

        groups.sort(key=lambda group: min(group.table_indexes))

        logical_tables: List[LogicalTable] = []
        used_table_ids: set[str] = set()
        for sequence, group in enumerate(groups, 1):
            indexes = group.table_indexes
            caption_indexes = group.caption_indexes
            identifier = group.identifier
            number = int(identifier) if identifier and identifier.isdigit() else None
            table_id = _logical_table_id(identifier, sequence, used_table_ids)
            group_warnings = list(
                dict.fromkeys(
                    warning for index in indexes for warning in table_warnings[index]
                )
            )
            if group_warnings:
                status = "caption_collision_recovered"
            elif len(indexes) > 1:
                status = "merged_fragments"
            elif caption_indexes and assignments.get(indexes[0]) == identifier and not (
                leading_labels.get(indexes[0])
                and leading_labels[indexes[0]].kind == "table"
                and leading_labels[indexes[0]].identifier == identifier
            ):
                status = "caption_attached"
            elif not caption_indexes:
                status = "caption_missing"
                group_warnings.append("caption_missing")
            else:
                status = "correct"

            caption = _caption_text(processed, caption_indexes)
            if caption is None:
                caption = _embedded_caption(processed[indexes[0]].text, identifier)
            source_blocks = [processed[index] for index in indexes]
            pages = [block.page for block in source_blocks if block.page is not None]
            logical_table = LogicalTable(
                table_id=table_id,
                label=f"Table {identifier}" if identifier is not None else None,
                number=number,
                caption=caption,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                section_path=source_blocks[0].section_path,
                source_block_ids=[block.block_id for block in source_blocks],
                caption_block_ids=[processed[index].block_id for index in caption_indexes],
                text="\n\n".join(block.text for block in source_blocks if block.text),
                status=status,
                warnings=group_warnings,
                identifier=identifier,
            )
            logical_tables.append(logical_table)

            for fragment_index, block_index in enumerate(indexes, 1):
                block = processed[block_index]
                block.relations.update(
                    {
                        "logical_table_id": table_id,
                        "logical_table_label": logical_table.label,
                        "logical_table_identifier": identifier,
                        "source_block_ids": logical_table.source_block_ids,
                        "caption_block_ids": logical_table.caption_block_ids,
                        "fragment_index": fragment_index,
                        "fragment_count": len(indexes),
                        "postprocess_status": status,
                        "warnings": group_warnings,
                    }
                )
            for caption_index in caption_indexes:
                processed[caption_index].relations.update(
                    {
                        "logical_table_id": table_id,
                        "logical_table_label": logical_table.label,
                        "logical_table_identifier": identifier,
                        "describes_block_ids": logical_table.source_block_ids,
                        "postprocess_status": "attached_to_table",
                    }
                )

        logical_tables.sort(
            key=lambda table: positions.get(table.source_block_ids[0], 10**9)
        )
        return TablePostProcessResult(
            blocks=processed,
            tables=logical_tables,
            warnings=warnings,
        )

    @staticmethod
    def _find_caption_target(
        caption_index: int,
        identifier: str,
        blocks: Sequence[ContentBlock],
        table_indexes: Sequence[int],
        occurrences: Dict[int, List[_Label]],
        assignments: Dict[int, Optional[str]],
    ) -> Optional[int]:
        same_page = [
            index
            for index in table_indexes
            if _same_page(blocks[caption_index], blocks[index])
        ]
        explicit = [
            index
            for index in same_page
            if assignments.get(index) == identifier
        ]
        if explicit:
            return min(explicit, key=lambda index: abs(index - caption_index))

        for index in (caption_index + 1, caption_index - 1):
            if (
                index in occurrences
                and not occurrences[index]
                and assignments.get(index) is None
                and _same_page(blocks[caption_index], blocks[index])
            ):
                return index
        return None

    @staticmethod
    def _retype_figures(
        blocks: List[ContentBlock], captions: Dict[int, _Label]
    ) -> None:
        for index, block in enumerate(blocks):
            if block.type != "table":
                continue
            label = _leading_label(block.text)
            if not label or label.kind != "figure":
                continue
            caption_indexes = [
                candidate
                for candidate in (index - 1, index + 1)
                if candidate in captions
                and captions[candidate].kind == "figure"
                and captions[candidate].identifier == label.identifier
                and _same_page(block, blocks[candidate])
            ]
            block.type = "figure"
            block.relations.update(
                {
                    "original_type": "table",
                    "figure_label": f"Figure {label.identifier}",
                    "caption_block_ids": [
                        blocks[candidate].block_id for candidate in caption_indexes
                    ],
                    "postprocess_status": "retyped_as_figure",
                    "warnings": ["figure_classified_as_table"],
                }
            )
            for caption_index in caption_indexes:
                blocks[caption_index].relations.update(
                    {
                        "describes_block_ids": [block.block_id],
                        "postprocess_status": "attached_to_figure",
                    }
                )


def _labels(text: str, *, kind: Optional[str] = None) -> List[_Label]:
    labels = []
    for match in _LABEL_RE.finditer(text or ""):
        raw_kind = match.group(1).lower()
        label_kind = "figure" if raw_kind.startswith("fig") else "table"
        if kind and label_kind != kind.lower():
            continue
        identifier = _normalize_identifier(match.group(2))
        labels.append(
            _Label(
                kind=label_kind,
                identifier=identifier,
                number=int(identifier) if identifier.isdigit() else None,
                start=match.start(),
                end=match.end(),
            )
        )
    return labels


def _leading_label(text: str) -> Optional[_Label]:
    labels = _labels(text)
    if not labels:
        return None
    prefix = (text or "")[: labels[0].start]
    return labels[0] if not prefix.strip(" \t\r\n|#*_") else None


def _caption_owned_table_indexes(
    *,
    caption_index: int,
    target_index: int,
    identifier: str,
    blocks: Sequence[ContentBlock],
    table_indexes: Sequence[int],
    assignments: Dict[int, Optional[str]],
    reserved_targets: Dict[int, int],
    leading_labels: Dict[int, Optional[_Label]],
) -> List[int]:
    """Return the bounded physical-table region owned by one caption."""
    table_set = set(table_indexes)
    members = {target_index}

    def scan(direction: int) -> None:
        index = caption_index + direction
        while 0 <= index < len(blocks):
            if index not in table_set:
                break
            reserved_owner = reserved_targets.get(index)
            if reserved_owner is not None and reserved_owner != caption_index:
                break
            assignment = assignments.get(index)
            if assignment is not None and assignment != identifier:
                break
            if not _same_page(blocks[caption_index], blocks[index]):
                break
            members.add(index)
            index += direction

    if target_index > caption_index:
        scan(1)
    else:
        scan(-1)
        target_label = leading_labels.get(target_index)
        if (
            target_index == caption_index - 1
            and target_label is not None
            and target_label.kind == "table"
            and target_label.identifier == identifier
        ):
            # Docling sometimes places a repeated trailing caption between two
            # physical fragments of the same labelled table.
            scan(1)
    return sorted(members)


def _logical_table_id(
    identifier: Optional[str], sequence: int, used_ids: set[str]
) -> str:
    if identifier is None:
        base = f"logical_table_unlabelled_{sequence:04d}"
    elif identifier.isdigit():
        base = f"logical_table_{int(identifier):04d}"
    else:
        slug = re.sub(r"[^a-z0-9]+", "_", identifier.casefold()).strip("_")
        base = f"logical_table_{slug or sequence}"
    candidate = base
    if candidate in used_ids:
        candidate = f"{base}_{sequence:04d}"
    used_ids.add(candidate)
    return candidate


def _normalize_identifier(value: str) -> str:
    value = value.strip()
    if value and value[0].isalpha():
        return value.upper()
    if value and value[-1].isalpha():
        return value[:-1] + value[-1].lower()
    return value


def _same_page(left: ContentBlock, right: ContentBlock) -> bool:
    return left.page is not None and left.page == right.page


def _caption_text(
    blocks: Sequence[ContentBlock], caption_indexes: Sequence[int]
) -> Optional[str]:
    if not caption_indexes:
        return None
    return " ".join(blocks[index].text.strip() for index in caption_indexes if blocks[index].text)


def _embedded_caption(text: str, identifier: Optional[str]) -> Optional[str]:
    if identifier is None:
        return None
    match = next(
        (
            label
            for label in _labels(text, kind="table")
            if label.identifier.casefold() == identifier.casefold()
        ),
        None,
    )
    if match is None:
        return None
    tail = (text or "")[match.start :]
    line = tail.splitlines()[0].strip(" |")
    return line or None
