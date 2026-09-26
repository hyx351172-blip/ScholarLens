"""Serialize canonical blocks after ordering, section and evidence processing."""

from __future__ import annotations

import re
from typing import Literal, Sequence

from .models import ContentBlock
from .table_structure import render_table_with_context


def render_document_markdown(
    blocks: Sequence[ContentBlock], *, table_format: Literal["html", "markdown"] = "html"
) -> str:
    """Keep Markdown consistent with the blocks used for chunking.

    OCR fallback formulas remain visibly marked as unverified transcription.
    Missing formulas remain missing instead of being reconstructed or invented.
    """
    if table_format not in {"html", "markdown"}:
        raise ValueError("table_format must be html or markdown")
    parts: list[str] = []
    for block in sorted(blocks, key=lambda item: item.order):
        if block.type in {"page_header", "page_footer"}:
            continue
        text = block.text.strip()
        if block.type == "table":
            table_text = render_table_with_context(text, block.table_structure) if table_format == "html" else text
            if table_text:
                parts.append(table_text)
        elif block.type == "formula":
            if not text:
                parts.append("<!-- formula-not-decoded -->")
                continue
            if block.relations.get("formula_text_source") == "orig_fallback":
                parts.append("<!-- formula-ocr-fallback: unverified transcription -->")
            # Avoid nested math delimiters when the upstream model supplies them.
            for opening, closing in (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)")):
                if text.startswith(opening) and text.endswith(closing):
                    text = text[len(opening):-len(closing)].strip()
                    break
            parts.append("$$\n" + text + "\n$$")
        elif not text:
            continue
        elif block.type == "title":
            parts.append("# " + text)
        elif block.type == "heading":
            titles = block.relations.get("generated_section_titles") or [text]
            levels = block.relations.get("generated_section_levels") or [
                block.relations.get("section_level", 1)
            ]
            for index, title in enumerate(titles):
                level = levels[min(index, len(levels) - 1)]
                parts.append("#" * max(1, min(6, int(level))) + " " + title)
        elif block.type == "list_item":
            parts.append(text if re.match(r"^(?:[-*+] |\d+[.)] )", text) else "- " + text)
        elif block.type == "code":
            fence = "`" * max(3, max((len(run) + 1 for run in re.findall(r"`+", text)), default=3))
            parts.append(f"{fence}\n{text}\n{fence}")
        else:
            parts.append(text)
    return "\n\n".join(parts) + ("\n" if parts else "")
