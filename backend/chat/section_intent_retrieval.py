"""Deterministic section-aware scoring for broad scientific-paper questions.

Dense retrieval remains the candidate generator.  This module only adjusts a
bounded candidate pool when the query clearly asks for a conventional paper
section such as the method or conclusion.  The original dense score is always
retained as provenance.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


_QUERY_CUES = {
    "method": (
        "方法",
        "模型",
        "架构",
        "怎么做",
        "如何实现",
        "method",
        "methodology",
        "approach",
        "architecture",
    ),
    "conclusion": (
        "结论",
        "总结",
        "主要发现",
        "conclusion",
        "conclusions",
        "summary",
        "finding",
    ),
    "abstract": ("摘要", "概述", "abstract", "overview"),
    "experiment": (
        "实验",
        "评测",
        "结果",
        "性能",
        "experiment",
        "evaluation",
        "result",
        "performance",
    ),
}

_SECTION_CUES = {
    "method": (
        "method",
        "methodology",
        "model architecture",
        "approach",
        "encoder and decoder",
        "proposed model",
        "scaled dot-product attention",
        "multi-head attention",
        "position-wise feed-forward networks",
        "positional encoding",
    ),
    "conclusion": (
        "conclusion",
        "conclusions",
        "discussion and conclusion",
        "summary and conclusion",
    ),
    "abstract": ("abstract",),
    "experiment": (
        "experiment",
        "experiments",
        "evaluation",
        "results",
        "experimental results",
    ),
}

_REFERENCE_SECTION_CUES = ("references", "bibliography", "参考文献")
_CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[-,]\s*\d+)*\s*\]")


def infer_section_intent(query: str) -> str | None:
    """Return one unambiguous conventional section intent, if present."""

    normalized = str(query or "").casefold()
    matched = [
        intent
        for intent, cues in _QUERY_CUES.items()
        if any(cue in normalized for cue in cues)
    ]
    return matched[0] if len(matched) == 1 else None


def _metadata(document: dict[str, Any]) -> dict[str, Any]:
    value = document.get("metadata") or {}
    return value if isinstance(value, dict) else {}


def _section_text(document: dict[str, Any]) -> str:
    metadata = _metadata(document)
    parts: list[str] = []
    for key in ("section_path", "headers"):
        value = metadata.get(key, [])
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, Iterable):
            parts.extend(str(item) for item in value)
    return " ".join(parts).casefold()


def _body_text(document: dict[str, Any]) -> str:
    metadata = _metadata(document)
    original = metadata.get("text")
    return str(original if original is not None else document.get("chunk_text", ""))


def _cue_in_text(text: str, cue: str) -> bool:
    if any("\u3400" <= character <= "\u9fff" for character in cue):
        return cue in text
    return re.search(rf"(?<![a-z0-9]){re.escape(cue)}(?![a-z0-9])", text) is not None


def _has_explicit_heading(document: dict[str, Any], cues: tuple[str, ...]) -> bool:
    """Recognize Markdown/numbered headings, not incidental body words."""

    window = _body_text(document)[:1200].casefold()
    boundary = r"(?:^|[\r\n]|[.!?]\s+)"
    number = r"(?:\*{0,2}\d+(?:\.\d+)*\*{0,2}\s*)?"
    for cue in cues:
        pattern = re.compile(
            rf"{boundary}\s*(?:#{{1,6}}\s*)?{number}\*{{0,2}}"
            rf"{re.escape(cue)}\*{{0,2}}(?=\s|:)",
            re.IGNORECASE,
        )
        if pattern.search(window):
            return True
    return False


def _reference_penalty(document: dict[str, Any]) -> float:
    metadata = _metadata(document)
    section = _section_text(document)
    content_type = str(metadata.get("content_type", "")).casefold()
    if content_type == "reference" or any(cue in section for cue in _REFERENCE_SECTION_CUES):
        return 0.24
    if len(_CITATION_RE.findall(_body_text(document)[:1600])) >= 3:
        return 0.18
    return 0.0


def _section_boost(intent: str, document: dict[str, Any]) -> float:
    cues = _SECTION_CUES[intent]
    section = _section_text(document)
    if any(_cue_in_text(section, cue) for cue in cues):
        return 0.42

    if _has_explicit_heading(document, cues):
        return 0.34

    metadata = _metadata(document)
    if str(metadata.get("content_type", "")).casefold() == intent:
        return 0.30
    return 0.0


def rerank_section_intent(
    query: str,
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rerank a bounded dense candidate list using explicit section signals."""

    intent = infer_section_intent(query)
    scored: list[tuple[int, dict[str, Any]]] = []
    for position, document in enumerate(documents):
        item = dict(document)
        dense_score = float(item.get("retrieval_score", item.get("score", 0.0)))
        item["retrieval_score"] = dense_score
        item["section_intent"] = intent
        if intent is None:
            item["section_boost"] = 0.0
            item["score"] = dense_score
        else:
            boost = _section_boost(intent, item)
            # Citation markers are common in real Method/Conclusion prose. A
            # positively identified section must not be punished for citing
            # prior work; reference penalties only apply to unmatched noise.
            penalty = 0.0 if boost > 0 else _reference_penalty(item)
            item["section_boost"] = round(boost - penalty, 6)
            item["score"] = max(0.0, min(1.0, dense_score + boost - penalty))
        scored.append((position, item))

    scored.sort(key=lambda pair: (-float(pair[1]["score"]), pair[0]))
    return [item for _, item in scored]
