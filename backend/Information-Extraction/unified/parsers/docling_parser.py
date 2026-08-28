"""Docling-backed structured PDF parsing for ScholarLens.

The adapter produces a canonical paper document and raw Docling artifacts. It
does not split text into chunks and does not call embedding or vector services.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import (
    ContentBlock,
    PaperDocument,
    PaperMetadata,
    ParseQualityReport,
    ParserInfo,
    Section,
)
from .section_hierarchy_postprocessor import SectionHierarchyPostProcessor
from .table_postprocessor import LogicalTable, TablePostProcessor


LABEL_MAP = {
    "title": "title",
    "section_header": "heading",
    "heading": "heading",
    "paragraph": "paragraph",
    "text": "paragraph",
    "list_item": "list_item",
    "code": "code",
    "table": "table",
    "picture": "figure",
    "image": "figure",
    "caption": "caption",
    "formula": "formula",
    "reference": "reference",
    "footnote": "footnote",
    "page_header": "page_header",
    "page_footer": "page_footer",
}


@dataclass
class DoclingParseResult:
    document: PaperDocument
    markdown: str
    raw_document: Dict[str, Any]
    logical_tables: List[LogicalTable]


class DoclingParser:
    """Convert a PDF into ScholarLens' canonical, non-chunked document model."""

    def __init__(
        self,
        converter: Optional[Any] = None,
        *,
        table_mode: str = "accurate",
        do_ocr: bool = False,
        section_hierarchy_postprocessor: Optional[
            SectionHierarchyPostProcessor
        ] = None,
        table_postprocessor: Optional[TablePostProcessor] = None,
    ) -> None:
        self.table_mode = table_mode.lower()
        self.do_ocr = do_ocr
        self._converter = converter
        self.section_hierarchy_postprocessor = (
            section_hierarchy_postprocessor or SectionHierarchyPostProcessor()
        )
        self.table_postprocessor = table_postprocessor or TablePostProcessor()

    def _build_converter(self) -> Any:
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions,
                TableFormerMode,
            )
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise RuntimeError(
                "Docling 未安装。请先安装 backend/requirements.txt 中的 "
                "docling-slim PDF 解析依赖。"
            ) from exc

        options = PdfPipelineOptions()
        options.do_ocr = self.do_ocr
        options.do_table_structure = True
        options.table_structure_options.mode = (
            TableFormerMode.ACCURATE
            if self.table_mode == "accurate"
            else TableFormerMode.FAST
        )
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            }
        )

    @property
    def converter(self) -> Any:
        if self._converter is None:
            self._converter = self._build_converter()
        return self._converter

    def parse(
        self,
        pdf_path: Path | str,
        *,
        file_id: Optional[str] = None,
        original_filename: Optional[str] = None,
    ) -> DoclingParseResult:
        source = Path(pdf_path)
        if not source.is_file():
            raise FileNotFoundError(f"PDF 文件不存在: {source}")
        if source.suffix.lower() != ".pdf":
            raise ValueError(f"仅支持 PDF 文件: {source}")

        started = time.perf_counter()
        paper_id = _sha256_file(source)
        conversion = self.converter.convert(str(source))
        docling_document = conversion.document
        raw_document = _export_dict(docling_document)
        markdown = _export_markdown(docling_document)
        blocks, _ = self._normalize_items(docling_document)
        section_result = self.section_hierarchy_postprocessor.process(blocks)
        blocks = section_result.blocks
        sections = section_result.sections
        table_result = self.table_postprocessor.process(blocks)
        blocks = table_result.blocks
        total_pages = _page_count(docling_document, raw_document)
        metadata = _extract_metadata(
            blocks,
            markdown,
            original_filename or source.name,
        )
        quality = _build_quality_report(
            blocks,
            total_pages=total_pages,
            duration_seconds=time.perf_counter() - started,
            metadata=metadata,
        )
        quality.warnings.extend(section_result.warnings)

        try:
            parser_version = importlib.metadata.version("docling-slim")
        except importlib.metadata.PackageNotFoundError:
            parser_version = "injected-test-adapter"

        document = PaperDocument(
            schema_version="1.0",
            paper_id=paper_id,
            file_id=file_id or f"sha256_{paper_id[:16]}",
            filename=original_filename or source.name,
            parser=ParserInfo(
                version=parser_version,
                table_mode=self.table_mode,
                ocr_enabled=self.do_ocr,
            ),
            metadata=metadata,
            sections=sections,
            blocks=blocks,
            quality=quality,
        )
        return DoclingParseResult(
            document=document,
            markdown=markdown,
            raw_document=raw_document,
            logical_tables=table_result.tables,
        )

    def _normalize_items(self, document: Any) -> Tuple[List[ContentBlock], List[Section]]:
        blocks: List[ContentBlock] = []

        for order, (item, traversal_level) in enumerate(_iterate_items(document)):
            source_label = _label_value(getattr(item, "label", None))
            block_type = LABEL_MAP.get(source_label, source_label or "unknown")
            page, bbox = _provenance(item)
            heading_level = _heading_level(item, traversal_level)
            relations: Dict[str, Any] = {}
            if block_type == "heading":
                relations["docling_heading_level"] = heading_level

            if block_type == "table":
                text = _table_markdown(item, document)
            elif block_type == "formula":
                text, formula_source = _formula_text(item)
                relations["formula_text_source"] = formula_source
            else:
                text = str(getattr(item, "text", "") or "").strip()

            blocks.append(
                ContentBlock(
                    block_id=f"block_{order:06d}",
                    order=order,
                    type=block_type,
                    text=text,
                    page=page,
                    bbox=bbox,
                    section_path=[],
                    confidence=_confidence(item),
                    source_label=source_label or None,
                    relations=relations,
                )
            )

        return blocks, []


def save_parse_result(output_dir: Path | str, result: DoclingParseResult) -> Dict[str, str]:
    """Persist parsing artifacts. No chunk artifact is produced here."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    paths = {
        "markdown": destination / "content.md",
        "document": destination / "document.json",
        "docling_document": destination / "docling-document.json",
        "quality_report": destination / "quality-report.json",
        "tables": destination / "tables.json",
    }
    paths["markdown"].write_text(result.markdown, encoding="utf-8")
    paths["document"].write_text(
        json.dumps(result.document.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["docling_document"].write_text(
        json.dumps(result.raw_document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["quality_report"].write_text(
        json.dumps(asdict(result.document.quality), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["tables"].write_text(
        json.dumps(
            [asdict(table) for table in result.logical_tables],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {name: str(path) for name, path in paths.items()}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _export_dict(document: Any) -> Dict[str, Any]:
    exporter = getattr(document, "export_to_dict", None)
    if callable(exporter):
        return exporter()
    model_dump = getattr(document, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    raise TypeError("DoclingDocument 不支持 export_to_dict/model_dump")


def _export_markdown(document: Any) -> str:
    exporter = getattr(document, "export_to_markdown", None)
    if not callable(exporter):
        raise TypeError("DoclingDocument 不支持 export_to_markdown")
    return str(exporter())


def _iterate_items(document: Any) -> Iterable[Tuple[Any, int]]:
    iterator = getattr(document, "iterate_items", None)
    if not callable(iterator):
        raise TypeError("DoclingDocument 不支持 iterate_items")
    for entry in iterator():
        if isinstance(entry, tuple):
            item = entry[0]
            level = entry[1] if len(entry) > 1 and isinstance(entry[1], int) else 1
        else:
            item, level = entry, 1
        yield item, max(1, level)


def _label_value(label: Any) -> str:
    value = getattr(label, "value", label)
    return str(value or "").strip().lower()


def _heading_level(item: Any, traversal_level: int) -> int:
    explicit = getattr(item, "level", None)
    if isinstance(explicit, int) and explicit > 0:
        return explicit
    return max(1, traversal_level)


def _provenance(item: Any) -> Tuple[Optional[int], Optional[List[float]]]:
    provenance = getattr(item, "prov", None) or []
    if not provenance:
        return None, None
    first = provenance[0]
    page = _get(first, "page_no") or _get(first, "page")
    try:
        page = int(page) if page is not None else None
    except (TypeError, ValueError):
        page = None
    bbox_obj = _get(first, "bbox")
    if bbox_obj is None:
        return page, None
    coordinates = []
    for names in (("l", "left"), ("t", "top"), ("r", "right"), ("b", "bottom")):
        value = None
        for name in names:
            value = _get(bbox_obj, name)
            if value is not None:
                break
        if value is None:
            return page, None
        coordinates.append(float(value))
    return page, coordinates


def _get(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _confidence(item: Any) -> Optional[float]:
    value = getattr(item, "confidence", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _table_markdown(item: Any, document: Any) -> str:
    exporter = getattr(item, "export_to_markdown", None)
    if callable(exporter):
        try:
            return str(exporter(document)).strip()
        except TypeError:
            return str(exporter()).strip()
    return str(getattr(item, "text", "") or "").strip()


def _formula_text(item: Any) -> Tuple[str, str]:
    """Return Docling's normalized formula text or its raw recognition fallback."""
    text = str(getattr(item, "text", "") or "").strip()
    if text:
        return text, "text"
    original = str(getattr(item, "orig", "") or "").strip()
    if original:
        return original, "orig_fallback"
    return "", "missing"


def _page_count(document: Any, raw_document: Dict[str, Any]) -> int:
    pages = getattr(document, "pages", None)
    if pages is not None:
        try:
            return len(pages)
        except TypeError:
            pass
    raw_pages = raw_document.get("pages", {})
    return len(raw_pages) if hasattr(raw_pages, "__len__") else 0


def _extract_metadata(
    blocks: List[ContentBlock], markdown: str, filename: str = ""
) -> PaperMetadata:
    title_index = next((i for i, block in enumerate(blocks) if block.type == "title" and block.text), None)
    abstract_heading_index = next(
        (
            i
            for i, block in enumerate(blocks)
            if block.type == "heading" and re.fullmatch(r"abstract", block.text.strip(), re.IGNORECASE)
        ),
        None,
    )
    # Docling commonly labels an academic paper's title as the first
    # section_header. Treat only a heading before Abstract as the title.
    if title_index is None and abstract_heading_index:
        title_index = next(
            (
                i
                for i, block in enumerate(blocks[:abstract_heading_index])
                if block.type == "heading" and block.text
            ),
            None,
        )
    title = blocks[title_index].text if title_index is not None else _markdown_title(markdown)
    abstract_parts: List[str] = []
    if abstract_heading_index is not None:
        for block in blocks[abstract_heading_index + 1 :]:
            if block.type == "heading":
                break
            if block.type in {"paragraph", "list_item"} and block.text:
                abstract_parts.append(block.text)
    else:
        for block in blocks:
            match = re.match(r"^abstract\s*[:.—-]?\s*(.+)$", block.text, re.IGNORECASE | re.DOTALL)
            if match:
                abstract_parts.append(match.group(1).strip())
                break

    authors: List[str] = []
    if title_index is not None:
        upper_bound = abstract_heading_index if abstract_heading_index is not None else min(len(blocks), title_index + 5)
        # Authors may be one comma-separated line, alternate with affiliation
        # blocks, or share a block with email/affiliation text.
        for block in blocks[title_index + 1 : upper_bound]:
            if block.type != "paragraph" or not block.text:
                continue
            authors.extend(_parse_authors(block.text))
        # Two-column first pages can place an author/email fragment after the
        # Abstract in reading order (GAAP is one example). Only accept explicit
        # email-adjacent names in this broader pass to avoid treating prose as authors.
        title_page = blocks[title_index].page
        for block in blocks[upper_bound:]:
            if block.page != title_page:
                break
            if block.type in {"paragraph", "footnote"} and block.text:
                authors.extend(_parse_authors(block.text, require_email=True))
        authors = list(dict.fromkeys(authors))

    searchable = "\n".join(block.text for block in blocks if block.text)
    front_matter = "\n".join(
        block.text for block in blocks if block.text and (block.page or 1) <= 2
    )
    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", front_matter, re.IGNORECASE)
    arxiv_match = re.search(
        r"(?:arXiv\s*:\s*)?(\d{4}\.\d{4,5})(?:v\d+)?\b",
        filename,
        re.IGNORECASE,
    ) or re.search(
        r"arXiv\s*:\s*(\d{4}\.\d{4,5})(?:v\d+)?\b",
        front_matter,
        re.IGNORECASE,
    )
    filename_year = re.search(r"(?:^|[_-])((?:19|20)\d{2})(?:[._-]|$)", filename)
    if filename_year:
        year = int(filename_year.group(1))
    elif arxiv_match:
        year = 2000 + int(arxiv_match.group(1)[:2])
    else:
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", front_matter)
        year = int(year_match.group(1)) if year_match else None
    language = _detect_language(searchable)

    return PaperMetadata(
        title=title or None,
        authors=authors,
        abstract=" ".join(abstract_parts).strip() or None,
        year=year,
        doi=doi_match.group(0).rstrip(".,;)") if doi_match else None,
        arxiv_id=arxiv_match.group(1) if arxiv_match else None,
        language=language,
    )


def _markdown_title(markdown: str) -> Optional[str]:
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else None


def _parse_authors(text: str, *, require_email: bool = False) -> List[str]:
    candidate = re.sub(r"\s+", " ", text).strip()
    if not candidate:
        return []

    email_name_matches = list(
        re.finditer(
            r"((?:\b[A-Z][A-Za-z'’-]*\s+){1,4}[A-Z][A-Za-z'’-]*)\s+"
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            candidate,
        )
    )
    if "@" in candidate:
        authors = []
        for match in email_name_matches:
            name_tokens = re.findall(r"\b[A-Z][A-Za-z'’-]*\b", match.group(1))
            if len(name_tokens) >= 2:
                authors.append(" ".join(name_tokens[-2:]))
        return list(dict.fromkeys(authors))

    if require_email or len(candidate) > 500:
        return []

    if any(token in candidate.lower() for token in ("university", "institute", "department", "@")):
        return []
    parts = re.split(r"\s*(?:,|;|\band\b|\&)\s*", candidate)
    authors = []
    for part in parts:
        cleaned = re.sub(r"[\d*∗†‡]+", "", part).strip(" ,")
        if cleaned and 1 < len(cleaned.split()) <= 8:
            authors.append(cleaned)
    return authors


def _detect_language(text: str) -> Optional[str]:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return None
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in letters)
    return "zh" if cjk / len(letters) > 0.2 else "en"


def _build_quality_report(
    blocks: List[ContentBlock],
    *,
    total_pages: int,
    duration_seconds: float,
    metadata: PaperMetadata,
) -> ParseQualityReport:
    counts = Counter(block.type for block in blocks)
    pages_with_content = {
        block.page for block in blocks if block.page is not None and block.text.strip()
    }
    eligible = [block for block in blocks if block.type not in {"unknown"}]
    with_provenance = [
        block for block in eligible if block.page is not None and block.bbox is not None
    ]
    warnings = []
    if not metadata.title:
        warnings.append("未识别论文标题")
    if not metadata.abstract:
        warnings.append("未识别论文摘要")
    if total_pages and len(pages_with_content) < total_pages:
        warnings.append("部分页面没有带文本的结构块")
    empty_formula_count = sum(
        block.type == "formula" and not block.text.strip() for block in blocks
    )
    if empty_formula_count:
        warnings.append(f"{empty_formula_count} 个公式没有可用文本")

    return ParseQualityReport(
        total_pages=total_pages,
        parsed_pages=len(pages_with_content),
        total_blocks=len(blocks),
        block_counts=dict(sorted(counts.items())),
        provenance_coverage=(len(with_provenance) / len(eligible)) if eligible else 0.0,
        empty_page_numbers=[
            page for page in range(1, total_pages + 1) if page not in pages_with_content
        ],
        empty_block_count=sum(not block.text.strip() for block in blocks),
        duration_seconds=round(duration_seconds, 3),
        warnings=warnings,
    )
