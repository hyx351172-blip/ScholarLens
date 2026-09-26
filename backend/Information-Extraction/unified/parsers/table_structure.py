"""Lossless cell metadata alongside the legacy Markdown retrieval representation.

No OCR correction or table merging happens here. Invalid geometry stays auditable
and uses the pre-existing text fallback instead of guessing a repaired grid.
"""
from __future__ import annotations

import html
import math
from typing import Any


MAX_GRID_SLOTS = 100_000
CELL_FIELDS = (
    "text", "start_row_offset_idx", "end_row_offset_idx", "start_col_offset_idx",
    "end_col_offset_idx", "row_span", "col_span", "column_header", "row_header", "row_section",
)


def _get(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _scalar(value: Any) -> Any:
    value = getattr(value, "value", value)
    if isinstance(value, float) and not math.isfinite(value):
        return None  # Keep saved artifacts strict JSON, even for invalid input.
    return value


def extract_table_structure(item: Any) -> dict[str, Any] | None:
    data = _get(item, "data")
    if data is None:
        return None
    cells = []
    for cell in _get(data, "table_cells", []) or []:
        mapped = {name: _scalar(_get(cell, name)) for name in CELL_FIELDS}
        bbox = _get(cell, "bbox")
        mapped["bbox"] = None if bbox is None else {
            key: _scalar(_get(bbox, key)) for key in ("l", "t", "r", "b", "coord_origin")
        }
        cells.append(mapped)
    result = {
        "schema_version": "1.0", "source": "docling",
        "source_ref": _get(item, "self_ref"),
        "num_rows": _scalar(_get(data, "num_rows")),
        "num_cols": _scalar(_get(data, "num_cols")), "table_cells": cells,
    }
    _, occupied, errors = _grid(result)
    result["valid"] = not errors
    result["warnings"] = errors
    if not errors:
        gaps = result["num_rows"] * result["num_cols"] - len(occupied)
        result["uncovered_slots"] = gaps
        if gaps:
            result["warnings"].append(f"{gaps} unrecognized grid slots exported as empty cells")
    return result


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _grid(data: dict[str, Any]) -> tuple[dict, set, list[str]]:
    rows, cols = data.get("num_rows"), data.get("num_cols")
    if not all(_integer(n) and n > 0 for n in (rows, cols)):
        return {}, set(), ["invalid table dimensions"]
    if rows * cols > MAX_GRID_SLOTS:
        return {}, set(), ["table exceeds safe grid size"]
    cells = data.get("table_cells")
    if not isinstance(cells, list) or not cells or len(cells) > MAX_GRID_SLOTS:
        return {}, set(), ["missing or excessive table cells"]
    starts, occupied = {}, set()
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            return {}, set(), [f"cell {index}: invalid cell payload"]
        r0, r1 = cell.get("start_row_offset_idx"), cell.get("end_row_offset_idx")
        c0, c1 = cell.get("start_col_offset_idx"), cell.get("end_col_offset_idx")
        rs, cs = cell.get("row_span"), cell.get("col_span")
        if not all(_integer(n) for n in (r0, r1, c0, c1, rs, cs)):
            return {}, set(), [f"cell {index}: offsets/spans must be integers"]
        if not (0 <= r0 < r1 <= rows and 0 <= c0 < c1 <= cols):
            return {}, set(), [f"cell {index}: out-of-bounds offsets"]
        if rs != r1 - r0 or cs != c1 - c0:
            return {}, set(), [f"cell {index}: spans disagree with offsets"]
        if not isinstance(cell.get("text"), str):
            return {}, set(), [f"cell {index}: text is not a string"]
        bbox = cell.get("bbox")
        if bbox is not None:
            if not isinstance(bbox, dict) or not all(
                isinstance(bbox.get(key), (float, int)) and math.isfinite(bbox[key])
                for key in ("l", "t", "r", "b")
            ):
                return {}, set(), [f"cell {index}: invalid bbox coordinates"]
        slots = {(r, c) for r in range(r0, r1) for c in range(c0, c1)}
        if slots & occupied:
            return {}, set(), [f"cell {index}: overlapping cells"]
        occupied.update(slots)
        starts[(r0, c0)] = cell
    return starts, occupied, []


def render_table_html(data: dict[str, Any] | None) -> str | None:
    if not data or data.get("schema_version") != "1.0" or not data.get("valid"):
        return None
    starts, occupied, errors = _grid(data)  # Validate loaded artifacts as well.
    if errors:
        return None
    lines = ["<table>"]
    for row in range(data["num_rows"]):
        cells = []
        for col in range(data["num_cols"]):
            cell = starts.get((row, col))
            if cell is None:
                if (row, col) not in occupied:
                    cells.append("<td></td>")
                continue
            tag = "th" if any(cell.get(key) for key in ("column_header", "row_header", "row_section")) else "td"
            attrs = ""
            if cell["row_span"] > 1:
                attrs += f' rowspan="{cell["row_span"]}"'
            if cell["col_span"] > 1:
                attrs += f' colspan="{cell["col_span"]}"'
            text = html.escape(cell["text"]).replace("\n", "<br>")
            cells.append(f"<{tag}{attrs}>{text}</{tag}>")
        lines.append("<tr>" + "".join(cells) + "</tr>")
    return "\n".join([*lines, "</table>"])


def render_table_with_context(text: str, data: dict[str, Any] | None) -> str:
    table_html = render_table_html(data)
    if table_html is None:
        return text
    lines = text.splitlines()
    grid = [i for i, line in enumerate(lines) if line.strip().startswith("|") and line.strip().endswith("|")]
    if not grid:
        # Preserve any caption/context even when the old exporter had no grid.
        return "\n\n".join(part for part in (text.strip(), table_html) if part)
    start, end = grid[0], grid[-1]
    grid_positions = set(grid)
    if any(line.strip() and i not in grid_positions for i, line in enumerate(lines) if start <= i <= end):
        return text  # Ambiguous multiple grids: don't discard intervening evidence.
    return "\n\n".join(part for part in (
        "\n".join(lines[:start]).strip(), table_html, "\n".join(lines[end + 1:]).strip()
    ) if part)
