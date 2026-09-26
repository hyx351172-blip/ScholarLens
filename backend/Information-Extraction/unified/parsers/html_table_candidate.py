"""Strict, bounded HTML transcription adapter for offline experiments only.

Unlike a browser, do not silently repair omitted tags or fill missing cells.
Only canonical escaped HTML leaves this adapter; model markup is untrusted.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

if __package__:
    from .table_structure import render_table_html
else:
    # Direct import for the isolated evaluator: do not execute parsers/__init__,
    # which intentionally imports production PDF/model integrations.
    from table_structure import render_table_html


class _TableParser(HTMLParser):
    INLINE = {"b", "strong", "i", "em", "sup", "sub", "span"}
    PRESENTATION = {"border", "class", "style", "id", "align", "valign", "width", "height",
                    "cellpadding", "cellspacing", "scope"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.rows = []
        self.current = None
        self.tables = 0

    def handle_starttag(self, tag, attrs):
        parent = self.stack[-1] if self.stack else None
        seen = set()
        spans = {"rowspan": 1, "colspan": 1}
        for name, value in attrs:
            if name in seen:
                raise ValueError("Duplicate HTML attribute")
            seen.add(name)
            if name in spans and tag in {"td", "th"}:
                if not value or not re.fullmatch(r"[0-9]{1,3}", value):
                    raise ValueError("Invalid span")
                spans[name] = int(value)
                if not 1 <= spans[name] <= (500 if name == "rowspan" else 100):
                    raise ValueError("Excessive or zero span")
            elif name not in self.PRESENTATION:
                raise ValueError("Unsupported or unsafe HTML attribute")
        if tag == "html":
            valid = parent is None and self.tables == 0
        elif tag == "body":
            valid = parent in {None, "html"} and self.tables == 0
        elif tag == "table":
            valid = parent in {None, "html", "body"} and self.tables == 0
            self.tables += 1
        elif tag in {"thead", "tbody", "tfoot"}:
            valid = parent == "table"
        elif tag == "tr":
            valid = parent in {"table", "thead", "tbody", "tfoot"}
            if len(self.rows) >= 500:
                raise ValueError("Excessive row count")
            self.rows.append([])
        elif tag in {"td", "th"}:
            valid = parent == "tr" and self.current is None
            self.current = {"rs": spans["rowspan"], "cs": spans["colspan"],
                            "header": tag == "th", "parts": []}
        elif tag in self.INLINE or tag == "br":
            valid = self.current is not None and parent in self.INLINE | {"td", "th"}
            if valid and tag == "br":
                self.current["parts"].append("\n")
        else:
            valid = False
        if not valid:
            raise ValueError("Unsupported or incorrectly nested HTML tag")
        if tag != "br":
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            raise ValueError("Unbalanced HTML tags")
        self.stack.pop()
        if tag in {"td", "th"}:
            self.rows[-1].append(self.current)
            self.current = None

    def handle_startendtag(self, tag, attrs):
        if tag != "br":
            raise ValueError("Only br may be self-closing")
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.current is not None:
            self.current["parts"].append(data)
        elif data.strip():
            raise ValueError("Text outside table cells")

    def handle_comment(self, data):
        raise ValueError("Comments are not table content")

    def handle_decl(self, decl):
        raise ValueError("Declarations are not table content")

    def handle_pi(self, data):
        raise ValueError("Processing instructions are not table content")

    def unknown_decl(self, data):
        raise ValueError("Unknown HTML declaration")


def parse_html_table(raw: str):
    if not isinstance(raw, str) or not raw or len(raw) > 1_000_000:
        raise ValueError("Missing or excessive HTML response")
    raw = raw.strip()
    fenced = re.fullmatch(r"```(?:html)?\s*\n(.*?)\n```", raw, flags=re.S | re.I)
    if fenced:
        raw = fenced.group(1)
    parser = _TableParser()
    parser.feed(raw)
    parser.close()
    if parser.stack or parser.tables != 1 or not parser.rows or parser.rawdata:
        raise ValueError("Incomplete HTML table")
    occupied, cells, uncertain = set(), [], []
    cols = 0
    for r, row in enumerate(parser.rows):
        c = 0
        for source in row:
            while (r, c) in occupied:
                c += 1
            rs, cs = source["rs"], source["cs"]
            if r + rs > len(parser.rows) or c + cs > 100:
                raise ValueError("Span extends outside declared rows or safe column limit")
            slots = {(i, j) for i in range(r, r + rs) for j in range(c, c + cs)}
            if slots & occupied:
                raise ValueError("Overlapping HTML spans")
            occupied.update(slots)
            if len(occupied) > 5000:
                raise ValueError("Excessive table grid")
            text = "".join(source["parts"]).strip()
            if len(text) > 10000:
                raise ValueError("Excessive cell text")
            if "[UNCERTAIN]" in text:
                uncertain.append([r, c])
            cells.append({"text": text, "start_row_offset_idx": r, "end_row_offset_idx": r + rs,
                          "start_col_offset_idx": c, "end_col_offset_idx": c + cs,
                          "row_span": rs, "col_span": cs, "column_header": source["header"],
                          "row_header": False, "row_section": False, "bbox": None})
            c += cs
            cols = max(cols, c)
    if not cells or len(occupied) != len(parser.rows) * cols:
        missing = len(parser.rows) * cols - len(occupied)
        raise ValueError(f"Incomplete grid coverage: {missing} uncovered slots in {len(parser.rows)}x{cols}; explicit empty cells required")
    structure = {"schema_version": "1.0", "source": "vlm_html_experiment",
                 "num_rows": len(parser.rows), "num_cols": cols, "table_cells": cells,
                 "valid": True, "uncovered_slots": 0, "uncertain_cells": uncertain,
                 "warnings": ["Offline candidate: human review required; schema validity is not correctness"]}
    rendered = render_table_html(structure)
    if rendered is None:
        raise ValueError("Invalid canonical table")
    return structure, rendered
