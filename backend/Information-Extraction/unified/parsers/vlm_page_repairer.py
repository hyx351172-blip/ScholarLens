"""VLM-assisted repair for difficult scientific-PDF pages.

The VLM is deliberately constrained to selecting existing parser block IDs. It
cannot rewrite table cells, formulas, or body text.  All accepted changes are
validated, additive, auditable, and applied to a deep copy of the Docling result.
"""

from __future__ import annotations

import base64
import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

import pymupdf

from .docling_parser import DoclingParseResult


_CAPTION_TYPES = {"caption", "figure_caption", "paragraph", "text", "list_item"}
_GENERIC_TITLES = {"perspective", "article", "research article", "contents"}
_LABEL_RE = re.compile(r"\b(Table|Figure|Fig\.)\s*(\d+)\b", re.IGNORECASE)


class VLMPageClient(Protocol):
    def analyze_page(
        self,
        *,
        page: int,
        image_data_url: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]: ...


@dataclass(frozen=True)
class VLMPageRepairConfig:
    min_confidence: float = 0.8
    max_pages: int = 8
    render_dpi: int = 144
    max_block_text_chars: int = 1200

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence 必须位于 [0, 1]")
        if self.max_pages < 1:
            raise ValueError("max_pages 必须至少为 1")
        if self.render_dpi < 72:
            raise ValueError("render_dpi 不能低于 72")


@dataclass
class VLMPageRepairResult:
    parse_result: DoclingParseResult
    candidate_pages: List[int]
    accepted_repairs: List[Dict[str, Any]] = field(default_factory=list)
    rejected_repairs: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def audit_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.0",
            "candidate_pages": self.candidate_pages,
            "accepted_repairs": self.accepted_repairs,
            "rejected_repairs": self.rejected_repairs,
            "warnings": self.warnings,
        }


class OpenAICompatibleVLMClient:
    """Small synchronous adapter for OpenAI-compatible multimodal endpoints."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        if not api_key or not model_name or not base_url:
            raise ValueError("VLM repair requires api_key, model_name and base_url")
        from openai import OpenAI

        normalized_url = base_url.replace("/chat/completions", "").rstrip("/")
        self.model_name = model_name
        self._client = OpenAI(
            api_key=api_key,
            base_url=normalized_url,
            timeout=timeout_seconds,
        )

    def analyze_page(
        self,
        *,
        page: int,
        image_data_url: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        system_prompt = (
            "You repair scientific PDF parser relationships. Return one JSON object only. "
            "You may select only block_id values present in allowed_blocks. Never transcribe, "
            "rewrite, infer, or correct table cells, equations, or body text. For metadata, "
            "return source block IDs rather than generated text. For bindings, connect an "
            "existing table/figure block to existing caption text on this page. If uncertain, "
            "return empty arrays."
        )
        response = self._client.chat.completions.create(
            model=self.model_name,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Analyze page "
                                f"{page}. Output schema: "
                                '{"title_block_ids":[],"abstract_block_ids":[],"bindings":['
                                '{"kind":"table|figure","object_block_ids":[],"caption_block_ids":[],'
                                '"confidence":0.0,"reason":""}]}. Context:\n'
                                + json.dumps(context, ensure_ascii=False)
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        return _parse_json_object(content)


class VLMPageRepairer:
    def __init__(
        self,
        *,
        client: VLMPageClient,
        config: Optional[VLMPageRepairConfig] = None,
        renderer: Optional[Callable[[Path, int, int], str]] = None,
    ) -> None:
        self.client = client
        self.config = config or VLMPageRepairConfig()
        self.renderer = renderer or render_pdf_page_data_url

    def select_candidate_pages(self, parsed: DoclingParseResult) -> List[int]:
        """Return deterministic, high-value pages requiring visual inspection."""
        ordered: List[int] = []

        def add(page: Optional[int]) -> None:
            if page and page > 0 and page not in ordered:
                ordered.append(page)

        metadata = parsed.document.metadata
        if (
            not metadata.abstract
            or _is_suspicious_title(metadata.title)
        ):
            add(1)
        for table in parsed.logical_tables:
            if not table.caption_block_ids:
                add(table.page_start)
        for figure in parsed.logical_figures:
            if not figure.caption_block_ids:
                add(figure.page)
        return ordered[: self.config.max_pages]

    def repair(
        self,
        pdf_path: Path | str,
        parsed: DoclingParseResult,
    ) -> VLMPageRepairResult:
        repaired = copy.deepcopy(parsed)
        pages = self.select_candidate_pages(parsed)
        result = VLMPageRepairResult(parse_result=repaired, candidate_pages=pages)
        for page in pages:
            try:
                context = self._page_context(repaired, page)
                image_data_url = self.renderer(
                    Path(pdf_path), page, self.config.render_dpi
                )
                payload = self.client.analyze_page(
                    page=page,
                    image_data_url=image_data_url,
                    context=context,
                )
                if not isinstance(payload, dict):
                    raise TypeError("VLM response is not a JSON object")
                self._apply_metadata(page, payload, repaired, result)
                self._apply_bindings(page, payload, repaired, result)
            except Exception as exc:  # one paid-page failure must not discard Docling output
                result.warnings.append(
                    f"page {page}: VLM repair failed: {type(exc).__name__}: {exc}"
                )
        return result

    def _page_context(
        self,
        parsed: DoclingParseResult,
        page: int,
    ) -> Dict[str, Any]:
        blocks = [block for block in parsed.document.blocks if block.page == page]
        return {
            "filename": parsed.document.filename,
            "current_metadata": {
                "title": parsed.document.metadata.title,
                "abstract_present": bool(parsed.document.metadata.abstract),
                "authors_count": len(parsed.document.metadata.authors),
                "year": parsed.document.metadata.year,
            },
            "allowed_blocks": [
                {
                    "block_id": block.block_id,
                    "type": block.type,
                    "text": block.text[: self.config.max_block_text_chars],
                    "bbox": block.bbox,
                }
                for block in blocks
            ],
            "unbound_tables": [
                {
                    "table_id": table.table_id,
                    "source_block_ids": table.source_block_ids,
                }
                for table in parsed.logical_tables
                if not table.caption_block_ids
                and table.page_start is not None
                and table.page_start <= page <= (table.page_end or table.page_start)
            ],
            "unbound_figures": [
                {
                    "figure_id": figure.figure_id,
                    "source_block_ids": figure.source_block_ids,
                }
                for figure in parsed.logical_figures
                if not figure.caption_block_ids and figure.page == page
            ],
        }

    def _apply_metadata(
        self,
        page: int,
        payload: Dict[str, Any],
        parsed: DoclingParseResult,
        result: VLMPageRepairResult,
    ) -> None:
        if page != 1:
            return
        block_map = {block.block_id: block for block in parsed.document.blocks}
        metadata = parsed.document.metadata
        metadata_specs = (
            ("title", "title_block_ids", _is_suspicious_title(metadata.title)),
            ("abstract", "abstract_block_ids", not bool(metadata.abstract)),
        )
        for field_name, response_key, needs_repair in metadata_specs:
            raw_ids = payload.get(response_key, [])
            if not raw_ids:
                continue
            ids = _string_list(raw_ids)
            valid = bool(ids) and all(
                block_id in block_map
                and block_map[block_id].page == 1
                and bool(block_map[block_id].text.strip())
                for block_id in ids
            )
            allowed_types = (
                {"title", "heading", "paragraph"}
                if field_name == "title"
                else {"paragraph", "text", "list_item"}
            )
            valid = valid and all(
                block_map[block_id].type in allowed_types for block_id in ids
            )
            if not needs_repair or not valid:
                result.rejected_repairs.append(
                    {
                        "type": f"metadata_{field_name}",
                        "page": page,
                        "source_block_ids": ids,
                        "reason": "not_needed_or_invalid_block_ids",
                    }
                )
                continue
            value = " ".join(block_map[block_id].text.strip() for block_id in ids)
            previous = getattr(metadata, field_name)
            setattr(metadata, field_name, value)
            result.accepted_repairs.append(
                {
                    "type": f"metadata_{field_name}",
                    "page": page,
                    "source_block_ids": ids,
                    "previous_value": previous,
                    "new_value": value,
                }
            )

    def _apply_bindings(
        self,
        page: int,
        payload: Dict[str, Any],
        parsed: DoclingParseResult,
        result: VLMPageRepairResult,
    ) -> None:
        bindings = payload.get("bindings", [])
        if not isinstance(bindings, list):
            result.rejected_repairs.append(
                {"type": "bindings", "page": page, "reason": "not_a_list"}
            )
            return
        block_map = {block.block_id: block for block in parsed.document.blocks}
        for raw in bindings:
            if not isinstance(raw, dict):
                result.rejected_repairs.append(
                    {"type": "caption_binding", "page": page, "reason": "not_an_object"}
                )
                continue
            kind = str(raw.get("kind", "")).lower()
            object_ids = _string_list(raw.get("object_block_ids", []))
            caption_ids = _string_list(raw.get("caption_block_ids", []))
            try:
                confidence = float(raw.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            reject_reason = self._binding_rejection_reason(
                kind=kind,
                object_ids=object_ids,
                caption_ids=caption_ids,
                confidence=confidence,
                page=page,
                block_map=block_map,
            )
            logical_object = None
            if reject_reason is None:
                logical_object = self._find_logical_object(kind, object_ids, parsed)
                if logical_object is None:
                    reject_reason = "no_matching_logical_object"
                elif logical_object.caption_block_ids:
                    reject_reason = "logical_object_already_has_caption"
            if reject_reason is not None:
                result.rejected_repairs.append(
                    {
                        "type": "caption_binding",
                        "page": page,
                        "kind": kind,
                        "object_block_ids": object_ids,
                        "caption_block_ids": caption_ids,
                        "confidence": confidence,
                        "reason": reject_reason,
                    }
                )
                continue
            caption_text = " ".join(
                block_map[block_id].text.strip() for block_id in caption_ids
            )
            logical_object.caption_block_ids = caption_ids
            logical_object.caption = caption_text
            logical_object.status = "vlm_bound"
            label_match = _LABEL_RE.search(caption_text)
            if label_match:
                logical_object.label = label_match.group(0)
                logical_object.number = int(label_match.group(2))
            bound_object_ids = list(logical_object.source_block_ids)
            audit = {
                "type": "caption_binding",
                "page": page,
                "kind": kind,
                "logical_object_id": (
                    logical_object.table_id if kind == "table" else logical_object.figure_id
                ),
                "selected_object_block_ids": object_ids,
                "object_block_ids": bound_object_ids,
                "caption_block_ids": caption_ids,
                "confidence": confidence,
                "reason": str(raw.get("reason", ""))[:500],
            }
            for object_id in bound_object_ids:
                _append_unique_relation(
                    block_map[object_id].relations, "caption_block_ids", caption_ids
                )
                block_map[object_id].relations.setdefault("vlm_repairs", []).append(audit)
            for caption_id in caption_ids:
                _append_unique_relation(
                    block_map[caption_id].relations, "describes_block_ids", object_ids
                )
                block_map[caption_id].relations.setdefault("vlm_repairs", []).append(audit)
            result.accepted_repairs.append(audit)

    def _binding_rejection_reason(
        self,
        *,
        kind: str,
        object_ids: List[str],
        caption_ids: List[str],
        confidence: float,
        page: int,
        block_map: Dict[str, Any],
    ) -> Optional[str]:
        if confidence < self.config.min_confidence:
            return "confidence_below_threshold"
        if kind not in {"table", "figure"}:
            return "unsupported_kind"
        if not object_ids or not caption_ids:
            return "missing_block_ids"
        all_ids = object_ids + caption_ids
        if any(block_id not in block_map for block_id in all_ids):
            return "unknown_block_id"
        if any(block_map[block_id].page != page for block_id in all_ids):
            return "cross_page_binding_not_allowed"
        if any(block_map[block_id].type != kind for block_id in object_ids):
            return "object_type_mismatch"
        if any(block_map[block_id].type not in _CAPTION_TYPES for block_id in caption_ids):
            return "caption_type_not_allowed"
        if any(not block_map[block_id].text.strip() for block_id in caption_ids):
            return "empty_caption_text"
        return None

    @staticmethod
    def _find_logical_object(
        kind: str,
        object_ids: List[str],
        parsed: DoclingParseResult,
    ) -> Any:
        requested = set(object_ids)
        candidates = (
            parsed.logical_tables if kind == "table" else parsed.logical_figures
        )
        matches = [
            item for item in candidates if requested.issubset(set(item.source_block_ids))
        ]
        return matches[0] if len(matches) == 1 else None


def render_pdf_page_data_url(pdf_path: Path, page: int, dpi: int) -> str:
    """Render a one-based PDF page to an inline PNG data URL."""
    with pymupdf.open(pdf_path) as document:
        if page < 1 or page > document.page_count:
            raise ValueError(f"page {page} outside PDF range 1..{document.page_count}")
        scale = dpi / 72.0
        pixmap = document.load_page(page - 1).get_pixmap(
            matrix=pymupdf.Matrix(scale, scale), alpha=False
        )
        encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _parse_json_object(content: str) -> Dict[str, Any]:
    value = content.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise TypeError("VLM response root must be an object")
    return parsed


def _is_suspicious_title(value: Optional[str]) -> bool:
    if not value:
        return True
    normalized = " ".join(value.split()).strip()
    return (
        normalized.lower().startswith(("http://", "https://", "www."))
        or normalized.casefold() in _GENERIC_TITLES
        or len(normalized) < 8
    )


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item))


def _append_unique_relation(
    relations: Dict[str, Any], key: str, values: List[str]
) -> None:
    current = relations.setdefault(key, [])
    if not isinstance(current, list):
        current = []
        relations[key] = current
    for value in values:
        if value not in current:
            current.append(value)
