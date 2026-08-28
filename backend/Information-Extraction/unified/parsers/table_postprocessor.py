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


_LABEL_RE = re.compile(r"\b(Table|Figure)\s+(\d+)\s*[:.]", re.IGNORECASE)


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


@dataclass
class TablePostProcessResult:
    blocks: List[ContentBlock]
    tables: List[LogicalTable]
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Label:
    kind: str
    number: int
    start: int
    end: int


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
        assignments: Dict[int, Optional[int]] = {}
        table_warnings: Dict[int, List[str]] = {index: [] for index in table_indexes}
        collision_caption_targets: Dict[int, int] = {}

        # Docling can prepend the next table's caption to the current table's
        # malformed grid. If that caption is repeated as the next block and is
        # followed by an unlabeled table, assign the repeated caption forward
        # and recover the embedded label for the current table.
        for index in table_indexes:
            labels = occurrences[index]
            assignments[index] = labels[0].number if labels else None
            distinct = list(dict.fromkeys(label.number for label in labels))
            if len(distinct) < 2:
                continue
            next_caption = captions.get(index + 1)
            next_table_labels = occurrences.get(index + 2, [])
            if (
                next_caption
                and next_caption.kind == "table"
                and next_caption.number == distinct[0]
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

        caption_targets: Dict[int, int] = dict(collision_caption_targets)
        for caption_index, label in captions.items():
            if label.kind != "table" or caption_index in caption_targets:
                continue
            target = self._find_caption_target(
                caption_index,
                label.number,
                processed,
                table_indexes,
                occurrences,
                assignments,
            )
            if target is None:
                warnings.append(
                    f"{processed[caption_index].block_id}: no table matched "
                    f"Table {label.number} caption"
                )
                continue
            caption_targets[caption_index] = target
            assignments[target] = label.number

            # Pattern: labelled table -> its trailing caption -> unlabeled table.
            # This is how Docling emits the tested multi-panel/column fragments.
            fragment_index = caption_index + 1
            if (
                target == caption_index - 1
                and fragment_index in occurrences
                and not occurrences[fragment_index]
                and assignments.get(fragment_index) is None
                and _same_page(processed[target], processed[fragment_index])
            ):
                assignments[fragment_index] = label.number

        # Captions that lead an unlabeled table are attached to that table.
        for caption_index, target in caption_targets.items():
            label = captions[caption_index]
            assignments[target] = label.number

        groups: Dict[Tuple[str, int], List[int]] = {}
        anonymous = 0
        for index in table_indexes:
            number = assignments.get(index)
            if number is None:
                anonymous += 1
                key = ("anonymous", anonymous)
            else:
                key = ("numbered", number)
            groups.setdefault(key, []).append(index)

        logical_tables: List[LogicalTable] = []
        for sequence, (key, indexes) in enumerate(groups.items(), 1):
            number = key[1] if key[0] == "numbered" else None
            caption_indexes = sorted(
                index
                for index, target in caption_targets.items()
                if target in indexes
                or (number is not None and assignments.get(target) == number)
            )
            # Avoid sharing a caption across unrelated anonymous groups.
            if number is None:
                caption_indexes = [
                    index for index in caption_indexes if caption_targets[index] in indexes
                ]
            table_id = (
                f"logical_table_{number:04d}"
                if number is not None
                else f"logical_table_unlabelled_{sequence:04d}"
            )
            group_warnings = list(
                dict.fromkeys(
                    warning for index in indexes for warning in table_warnings[index]
                )
            )
            if group_warnings:
                status = "caption_collision_recovered"
            elif len(indexes) > 1:
                status = "merged_fragments"
            elif caption_indexes and not occurrences[indexes[0]]:
                status = "caption_attached"
            elif not caption_indexes:
                status = "caption_missing"
                group_warnings.append("caption_missing")
            else:
                status = "correct"

            caption = _caption_text(processed, caption_indexes)
            if caption is None:
                caption = _embedded_caption(processed[indexes[0]].text, number)
            source_blocks = [processed[index] for index in indexes]
            pages = [block.page for block in source_blocks if block.page is not None]
            logical_table = LogicalTable(
                table_id=table_id,
                label=f"Table {number}" if number is not None else None,
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
            )
            logical_tables.append(logical_table)

            for fragment_index, block_index in enumerate(indexes, 1):
                block = processed[block_index]
                block.relations.update(
                    {
                        "logical_table_id": table_id,
                        "logical_table_label": logical_table.label,
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
        number: int,
        blocks: Sequence[ContentBlock],
        table_indexes: Sequence[int],
        occurrences: Dict[int, List[_Label]],
        assignments: Dict[int, Optional[int]],
    ) -> Optional[int]:
        same_page = [
            index
            for index in table_indexes
            if _same_page(blocks[caption_index], blocks[index])
        ]
        explicit = [
            index
            for index in same_page
            if assignments.get(index) == number
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
                and captions[candidate].number == label.number
                and _same_page(block, blocks[candidate])
            ]
            block.type = "figure"
            block.relations.update(
                {
                    "original_type": "table",
                    "figure_label": f"Figure {label.number}",
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
        label_kind = match.group(1).lower()
        if kind and label_kind != kind.lower():
            continue
        labels.append(
            _Label(
                kind=label_kind,
                number=int(match.group(2)),
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


def _same_page(left: ContentBlock, right: ContentBlock) -> bool:
    return left.page is not None and left.page == right.page


def _caption_text(
    blocks: Sequence[ContentBlock], caption_indexes: Sequence[int]
) -> Optional[str]:
    if not caption_indexes:
        return None
    return " ".join(blocks[index].text.strip() for index in caption_indexes if blocks[index].text)


def _embedded_caption(text: str, number: Optional[int]) -> Optional[str]:
    if number is None:
        return None
    match = re.search(rf"\bTable\s+{number}\s*[:.]", text or "", re.IGNORECASE)
    if not match:
        return None
    tail = (text or "")[match.start() :]
    line = tail.splitlines()[0].strip(" |")
    return line or None
