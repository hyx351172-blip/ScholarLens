"""Reconstruct deterministic page reading order from block geometry."""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import DefaultDict, Dict, List, Optional, Sequence, Tuple

from .models import ContentBlock


@dataclass
class ReadingOrderResult:
    blocks: List[ContentBlock]
    page_methods: Dict[int, str]
    pages_reordered: int
    warnings: List[str]


class ReadingOrderPostProcessor:
    """Order blocks by page, full-width bands, columns, and vertical position."""

    def __init__(self, *, full_width_ratio: float = 0.72) -> None:
        if not 0.5 < full_width_ratio <= 1.0:
            raise ValueError("full_width_ratio must be in (0.5, 1.0]")
        self.full_width_ratio = full_width_ratio

    def process(self, blocks: Sequence[ContentBlock]) -> ReadingOrderResult:
        processed = [
            replace(block, relations=copy.deepcopy(block.relations)) for block in blocks
        ]
        grouped: DefaultDict[Optional[int], List[ContentBlock]] = defaultdict(list)
        for block in processed:
            block.relations.setdefault("original_order", block.order)
            grouped[block.page].append(block)

        ordered: List[ContentBlock] = []
        page_methods: Dict[int, str] = {}
        warnings: List[str] = []
        pages_reordered = 0
        page_keys = sorted(
            grouped,
            key=lambda page: (page is None, page if page is not None else 0),
        )
        for page in page_keys:
            source_page = sorted(
                grouped[page], key=lambda item: item.relations["original_order"]
            )
            if page is None or any(not _valid_bbox(block.bbox) for block in source_page):
                page_order = source_page
                method = "original_order_fallback"
                page_label = "unknown" if page is None else str(page)
                warnings.append(
                    f"page {page_label}: missing or invalid bbox; kept original order"
                )
                _annotate_fallback(page_order, method)
            else:
                page_order, method = self._order_geometric_page(source_page)
                page_order = _restore_evidence_groups(page_order, source_page)
            if [block.block_id for block in page_order] != [
                block.block_id for block in source_page
            ]:
                pages_reordered += 1
            if page is not None:
                page_methods[page] = method
            ordered.extend(page_order)

        for reading_order, block in enumerate(ordered):
            block.order = reading_order
            block.relations["reading_order"] = reading_order

        return ReadingOrderResult(
            blocks=ordered,
            page_methods=page_methods,
            pages_reordered=pages_reordered,
            warnings=warnings,
        )

    def _order_geometric_page(
        self, blocks: Sequence[ContentBlock]
    ) -> Tuple[List[ContentBlock], str]:
        front_matter = _front_matter_blocks(blocks)
        front_matter_ids = {block.block_id for block in front_matter}
        layout_blocks = [
            block for block in blocks if block.block_id not in front_matter_ids
        ]
        if not layout_blocks:
            _annotate_front_matter(front_matter, "single_column_geometry", 0.95)
            return front_matter, "single_column_geometry"
        page_left = min(block.bbox[0] for block in blocks if block.bbox)
        page_right = max(block.bbox[2] for block in blocks if block.bbox)
        page_width = page_right - page_left
        if page_width <= 0:
            fallback = sorted(blocks, key=lambda block: block.relations["original_order"])
            _annotate_fallback(fallback, "original_order_fallback")
            return fallback, "original_order_fallback"

        split_x = page_left + page_width / 2
        spanning = [
            block
            for block in layout_blocks
            if _is_spanning(block, split_x, page_width, self.full_width_ratio)
        ]
        column_blocks = [block for block in layout_blocks if block not in spanning]
        left = [block for block in column_blocks if _center_x(block) < split_x]
        right = [block for block in column_blocks if _center_x(block) >= split_x]
        two_column = _has_two_columns(left, right, page_width)

        if not two_column:
            ordered = sorted(layout_blocks, key=_vertical_key)
            for block in ordered:
                block.relations.update(
                    {
                        "column_index": 0,
                        "reading_band_index": 0,
                        "reading_order_method": "single_column_geometry",
                        "reading_order_confidence": 0.95,
                    }
                )
            _annotate_front_matter(front_matter, "single_column_geometry", 0.95)
            return front_matter + ordered, "single_column_geometry"

        remaining = list(column_blocks)
        ordered: List[ContentBlock] = []
        band_index = 0
        for boundary in sorted(spanning, key=_vertical_key):
            boundary_center = _center_y(boundary)
            above = [block for block in remaining if _center_y(block) > boundary_center]
            if above:
                ordered.extend(_order_column_band(above, split_x, band_index))
                remaining = [block for block in remaining if block not in above]
                band_index += 1
            boundary.relations.update(
                {
                    "column_index": -1,
                    "reading_band_index": band_index,
                    "reading_order_method": "two_column_geometry",
                    "reading_order_confidence": 0.9,
                }
            )
            ordered.append(boundary)
            band_index += 1
        if remaining:
            ordered.extend(_order_column_band(remaining, split_x, band_index))
        _annotate_front_matter(front_matter, "two_column_geometry", 0.9)
        return front_matter + ordered, "two_column_geometry"


def _valid_bbox(bbox: Optional[List[float]]) -> bool:
    return bool(
        bbox
        and len(bbox) == 4
        and bbox[0] <= bbox[2]
        and bbox[3] <= bbox[1]
    )


def _center_x(block: ContentBlock) -> float:
    assert block.bbox is not None
    return (block.bbox[0] + block.bbox[2]) / 2


def _center_y(block: ContentBlock) -> float:
    assert block.bbox is not None
    return (block.bbox[1] + block.bbox[3]) / 2


def _vertical_key(block: ContentBlock) -> Tuple[float, float, int]:
    assert block.bbox is not None
    return (-block.bbox[1], block.bbox[0], block.relations["original_order"])


def _is_spanning(
    block: ContentBlock,
    split_x: float,
    page_width: float,
    full_width_ratio: float,
) -> bool:
    assert block.bbox is not None
    width = block.bbox[2] - block.bbox[0]
    gutter_margin = page_width * 0.04
    crosses_gutter = (
        block.bbox[0] <= split_x - gutter_margin
        and block.bbox[2] >= split_x + gutter_margin
    )
    return crosses_gutter or width / page_width >= full_width_ratio


def _has_two_columns(
    left: Sequence[ContentBlock],
    right: Sequence[ContentBlock],
    page_width: float,
) -> bool:
    if not left or not right:
        return False
    left_edge = max(block.bbox[2] for block in left if block.bbox)
    right_edge = min(block.bbox[0] for block in right if block.bbox)
    return right_edge - left_edge >= page_width * 0.015


def _order_column_band(
    blocks: Sequence[ContentBlock], split_x: float, band_index: int
) -> List[ContentBlock]:
    left = sorted(
        (block for block in blocks if _center_x(block) < split_x),
        key=_vertical_key,
    )
    right = sorted(
        (block for block in blocks if _center_x(block) >= split_x),
        key=_vertical_key,
    )
    for column_index, column in enumerate((left, right)):
        for block in column:
            block.relations.update(
                {
                    "column_index": column_index,
                    "reading_band_index": band_index,
                    "reading_order_method": "two_column_geometry",
                    "reading_order_confidence": 0.9,
                }
            )
    return left + right


def _annotate_fallback(blocks: Sequence[ContentBlock], method: str) -> None:
    for block in blocks:
        block.relations.update(
            {
                "column_index": None,
                "reading_band_index": None,
                "reading_order_method": method,
                "reading_order_confidence": 0.0,
            }
        )


def _front_matter_blocks(blocks: Sequence[ContentBlock]) -> List[ContentBlock]:
    abstract = next(
        (
            block
            for block in blocks
            if block.type == "heading"
            and block.text.rstrip(".:").strip().casefold() == "abstract"
        ),
        None,
    )
    if abstract is None or abstract.bbox is None:
        return []
    front_matter = [
        block
        for block in blocks
        if block.block_id != abstract.block_id
        and block.bbox is not None
        and _center_y(block) > abstract.bbox[1]
    ]
    return sorted(front_matter, key=_vertical_key)


def _annotate_front_matter(
    blocks: Sequence[ContentBlock], method: str, confidence: float
) -> None:
    for block in blocks:
        block.relations.update(
            {
                "column_index": -1,
                "reading_band_index": -1,
                "reading_order_method": method,
                "reading_order_confidence": confidence,
            }
        )


def _restore_evidence_groups(
    geometric_order: Sequence[ContentBlock],
    original_order: Sequence[ContentBlock],
) -> List[ContentBlock]:
    """Keep Docling's local table/figure fragments together after page sorting."""
    evidence_types = {"table", "figure", "caption", "table_caption", "figure_caption"}
    groups: List[List[ContentBlock]] = []
    current: List[ContentBlock] = []
    for block in original_order:
        if block.type in evidence_types:
            current.append(block)
            continue
        if len(current) > 1 and any(
            item.type in {"table", "figure"} for item in current
        ):
            groups.append(current)
        current = []
    if len(current) > 1 and any(item.type in {"table", "figure"} for item in current):
        groups.append(current)

    restored = list(geometric_order)
    for group in groups:
        group_ids = {block.block_id for block in group}
        positions = [
            index for index, block in enumerate(restored) if block.block_id in group_ids
        ]
        if len(positions) != len(group):
            continue
        insert_at = min(positions)
        restored = [block for block in restored if block.block_id not in group_ids]
        restored[insert_at:insert_at] = group
    return restored
