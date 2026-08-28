"""Rebuild scientific-paper section hierarchy from normalized heading blocks."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from .models import ContentBlock, Section


_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?P<number>\d+(?:\.\d+)*)[.)]?\s+(?P<title>.+?)\s*$"
)
_NUMBER_TOKEN_RE = re.compile(r"(?<!\S)(?P<number>\d+(?:\.\d+)*)[.)]?\s+")
_APPENDIX_RE = re.compile(
    r"^\s*(?P<number>[A-Z](?:\.\d+)*)[.)]?\s+(?P<title>.+?)\s*$"
)
_APPENDIX_PREFIX_RE = re.compile(
    r"^\s*Appendix\s+(?P<number>[A-Z](?:\.\d+)*)[.):]?\s+(?P<title>.+?)\s*$",
    re.IGNORECASE,
)
_TOP_LEVEL_HEADINGS = {
    "abstract",
    "references",
    "bibliography",
    "acknowledgment",
    "acknowledgments",
    "acknowledgement",
    "acknowledgements",
    "limitations",
    "ethics statement",
    "appendix",
    "introduction",
    "related work",
    "background",
    "method",
    "methods",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
}


@dataclass
class SectionHierarchyResult:
    blocks: List[ContentBlock]
    sections: List[Section]
    warnings: List[str]


@dataclass(frozen=True)
class _HeadingInfo:
    title: str
    level: int
    number: Optional[str]
    inferred: bool
    kind: str = "regular"


class SectionHierarchyPostProcessor:
    """Infer a stable Section tree and assign section paths to every block."""

    def process(self, blocks: Sequence[ContentBlock]) -> SectionHierarchyResult:
        processed = [
            replace(
                block,
                section_path=[],
                relations=copy.deepcopy(block.relations),
            )
            for block in blocks
        ]
        for block in processed:
            block.relations.pop("containing_section_id", None)
            block.relations.pop("section_kind", None)
        sections: List[Section] = []
        stack: List[Section] = []
        last_numbered_stack: List[Section] = []
        anchor_ids = set()
        warnings: List[str] = []
        title_index = _find_title_index(processed)
        explicit_appendix_root: Optional[Section] = None

        for index, block in enumerate(processed):
            if index == title_index:
                block.type = "title"
                block.section_path = []
                block.relations.update(
                    {
                        "section_postprocess_status": "retyped_as_title",
                        "generated_section_ids": [],
                    }
                )
                continue

            if block.type != "heading":
                block.section_path = [section.title for section in stack]
                _bind_special_section(block, stack)
                continue

            parts = split_merged_heading(block.text)
            generated: List[Section] = []
            numbers: List[Optional[str]] = []
            levels: List[int] = []
            used_fallback = False

            for part in parts:
                info = _heading_info(part)
                if info is None:
                    if (
                        stack
                        and _normalized_heading(stack[-1].title) == "abstract"
                        and last_numbered_stack
                    ):
                        stack[:] = last_numbered_stack
                    level = _fallback_level(stack, anchor_ids)
                    info = _HeadingInfo(
                        title=part,
                        level=level,
                        number=None,
                        inferred=False,
                        kind=_inherited_special_kind(stack),
                    )
                    used_fallback = True
                    warnings.append(
                        f"{block.block_id}: inferred unnumbered heading level "
                        f"{level} for {part!r}"
                    )

                effective_level = info.level
                if info.kind == "appendix" and _is_lettered_appendix(part):
                    if explicit_appendix_root is not None:
                        effective_level += 1

                while stack and stack[-1].level >= effective_level:
                    stack.pop()

                if stack and effective_level > stack[-1].level + 1:
                    warnings.append(
                        f"{block.block_id}: level jump from {stack[-1].level} "
                        f"to {effective_level} for {part!r}"
                    )

                parent = stack[-1] if stack else None
                section = Section(
                    section_id=f"section_{len(sections):04d}",
                    title=info.title,
                    level=effective_level,
                    parent_id=parent.section_id if parent else None,
                    page=block.page,
                    kind=info.kind,
                )
                sections.append(section)
                stack.append(section)
                generated.append(section)
                numbers.append(info.number)
                levels.append(effective_level)
                if info.inferred:
                    anchor_ids.add(section.section_id)
                if info.number and info.number[0].isdigit():
                    last_numbered_stack = list(stack)
                if _is_explicit_appendix_root(part):
                    explicit_appendix_root = section

            if len(parts) > 1:
                status = "split_merged_heading"
            elif used_fallback:
                status = "hierarchy_fallback"
            else:
                status = "hierarchy_inferred"

            block.section_path = [section.title for section in stack]
            deepest = generated[-1]
            block.relations.update(
                {
                    "section_id": deepest.section_id,
                    "parent_section_id": deepest.parent_id,
                    "section_level": deepest.level,
                    "section_number": numbers[-1],
                    "generated_section_ids": [
                        section.section_id for section in generated
                    ],
                    "generated_section_titles": [
                        section.title for section in generated
                    ],
                    "generated_section_levels": levels,
                    "section_postprocess_status": status,
                }
            )
            if deepest.kind != "regular":
                block.relations["section_kind"] = deepest.kind
            if used_fallback:
                block.relations["section_warning"] = "level_inferred_by_context"

        return SectionHierarchyResult(
            blocks=processed,
            sections=sections,
            warnings=warnings,
        )


def split_merged_heading(text: str) -> List[str]:
    """Split only plausible section-number transitions inside a heading block."""
    value = (text or "").strip()
    matches = list(_NUMBER_TOKEN_RE.finditer(value))
    if len(matches) < 2 or matches[0].start() != 0:
        return [value]

    accepted = [matches[0]]
    previous = _number_tuple(matches[0].group("number"))
    for match in matches[1:]:
        current = _number_tuple(match.group("number"))
        if _plausible_transition(previous, current):
            accepted.append(match)
            previous = current

    if len(accepted) < 2:
        return [value]

    parts = []
    for index, match in enumerate(accepted):
        end = accepted[index + 1].start() if index + 1 < len(accepted) else len(value)
        part = value[match.start() : end].strip()
        if part:
            parts.append(part)
    return parts or [value]


def _find_title_index(blocks: Sequence[ContentBlock]) -> Optional[int]:
    for index, block in enumerate(blocks):
        if block.type == "title":
            return index
    heading_indexes = [
        index for index, block in enumerate(blocks) if block.type == "heading"
    ]
    if len(heading_indexes) < 2:
        return None
    first = heading_indexes[0]
    first_text = blocks[first].text.strip()
    normalized = first_text.rstrip(".:").strip().lower()
    if normalized in _TOP_LEVEL_HEADINGS:
        return None
    if _NUMBERED_HEADING_RE.match(first_text):
        return None
    return first


def _heading_info(text: str) -> Optional[_HeadingInfo]:
    value = (text or "").strip()
    normalized = _normalized_heading(value)
    if normalized == "abstract":
        return _HeadingInfo(value, 1, None, True, "abstract")
    if _is_explicit_appendix_root(value):
        return _HeadingInfo(value, 1, None, True, "appendix")
    if normalized in _TOP_LEVEL_HEADINGS:
        return _HeadingInfo(value, 1, None, True)

    prefixed_appendix = _APPENDIX_PREFIX_RE.match(value)
    if prefixed_appendix:
        number = prefixed_appendix.group("number").upper()
        return _HeadingInfo(
            value,
            number.count(".") + 1,
            number,
            True,
            "appendix",
        )

    numbered = _NUMBERED_HEADING_RE.match(value)
    if numbered:
        number = numbered.group("number")
        return _HeadingInfo(value, number.count(".") + 1, number, True)

    appendix = _APPENDIX_RE.match(value)
    if appendix:
        number = appendix.group("number")
        return _HeadingInfo(
            value,
            number.count(".") + 1,
            number,
            True,
            "appendix",
        )
    return None


def _is_explicit_appendix_root(text: str) -> bool:
    normalized = _normalized_heading(text)
    return normalized in {"appendix", "appendices", "appendix overview"}


def _is_lettered_appendix(text: str) -> bool:
    value = (text or "").strip()
    return bool(_APPENDIX_RE.match(value) or _APPENDIX_PREFIX_RE.match(value))


def _inherited_special_kind(stack: Sequence[Section]) -> str:
    for section in reversed(stack):
        if section.kind in {"abstract", "appendix"}:
            return section.kind
    return "regular"


def _bind_special_section(block: ContentBlock, stack: Sequence[Section]) -> None:
    for section in reversed(stack):
        if section.kind in {"abstract", "appendix"}:
            block.relations["containing_section_id"] = stack[-1].section_id
            block.relations["section_kind"] = section.kind
            return


def _normalized_heading(value: str) -> str:
    return value.rstrip(".:").strip().lower()


def _fallback_level(stack: Sequence[Section], anchor_ids: set) -> int:
    for section in reversed(stack):
        if section.section_id in anchor_ids:
            return section.level + 1
    return 1


def _number_tuple(number: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in number.split("."))


def _plausible_transition(
    previous: Tuple[int, ...], current: Tuple[int, ...]
) -> bool:
    if len(current) == len(previous) + 1:
        return current[:-1] == previous
    if len(current) == len(previous):
        return (
            current[:-1] == previous[:-1]
            and current[-1] == previous[-1] + 1
        )
    return False
