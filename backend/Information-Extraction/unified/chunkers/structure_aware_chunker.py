"""Build retrieval chunks from canonical blocks and their evidence relations."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from parsers.evidence_context_postprocessor import LogicalFigure, LogicalFormula
from parsers.models import ContentBlock, PaperDocument
from parsers.table_postprocessor import LogicalTable


_TOKEN_RE = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|[^\s]")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？.!?])\s+")
_IMAGE_PATH_RE = re.compile(
    r"^(?:[.\\/\w-]+[\\/])?[\w.-]+\.(?:png|jpe?g|gif|svg|webp)$",
    re.IGNORECASE,
)
CHUNK_SCHEMA_VERSION = "1.1"


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 600
    max_tokens: int = 900

    def __post_init__(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if self.max_tokens < self.target_tokens:
            raise ValueError("max_tokens must be greater than or equal to target_tokens")


@dataclass
class ScientificChunk:
    schema_version: str
    chunk_id: str
    paper_id: str
    file_id: str
    chunk_index: int
    content_type: str
    text: str
    retrieval_text: str
    page_start: Optional[int]
    page_end: Optional[int]
    section_path: List[str]
    source_block_ids: List[str]
    context_block_ids: List[str] = field(default_factory=list)
    caption_block_ids: List[str] = field(default_factory=list)
    table_id: Optional[str] = None
    table_identifier: Optional[str] = None
    figure_id: Optional[str] = None
    formula_id: Optional[str] = None
    fragment_indexes: List[int] = field(default_factory=list)
    part_index: int = 1
    part_count: int = 1
    row_start: Optional[int] = None
    row_end: Optional[int] = None
    token_count: int = 0
    is_generated_description: bool = False
    warnings: List[str] = field(default_factory=list)
    legacy_chunk_id: Optional[str] = None
    _anchor_order: int = field(default=10**9, repr=False, compare=False)

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data.pop("_anchor_order", None)
        pages = (
            list(range(self.page_start, self.page_end + 1))
            if self.page_start is not None and self.page_end is not None
            else []
        )
        data.update(
            {
                "pages": pages,
                "text_length": len(self.text),
                "headers": list(self.section_path),
                "continued": self.part_count > 1,
                "cross_page_bridge": False,
                "is_table_like": self.content_type == "table",
            }
        )
        return data


@dataclass
class ChunkingResult:
    chunks: List[ScientificChunk]
    warnings: List[str] = field(default_factory=list)
    schema_version: str = CHUNK_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, object]:
        counts: Dict[str, int] = {}
        for chunk in self.chunks:
            counts[chunk.content_type] = counts.get(chunk.content_type, 0) + 1
        return {
            "schema_version": self.schema_version,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "chunk_stats": {
                "total_chunks": len(self.chunks),
                "content_type_counts": dict(sorted(counts.items())),
                "avg_chunk_tokens": (
                    round(sum(chunk.token_count for chunk in self.chunks) / len(self.chunks), 2)
                    if self.chunks
                    else 0
                ),
                "max_chunk_tokens": max((chunk.token_count for chunk in self.chunks), default=0),
                "oversized_chunks": sum(
                    "oversized_atomic_unit" in chunk.warnings for chunk in self.chunks
                ),
                "bridge_chunks": 0,
            },
            "warnings": list(self.warnings),
        }


class StructureAwareChunker:
    """Route canonical evidence types to deterministic chunking strategies."""

    def __init__(
        self,
        config: Optional[ChunkingConfig] = None,
        *,
        token_counter: Optional[Callable[[str], int]] = None,
    ) -> None:
        self.config = config or ChunkingConfig()
        self._token_count = token_counter or estimate_tokens

    def chunk(
        self,
        document: PaperDocument,
        *,
        logical_tables: Sequence[LogicalTable] = (),
        logical_figures: Sequence[LogicalFigure] = (),
        logical_formulas: Sequence[LogicalFormula] = (),
    ) -> ChunkingResult:
        blocks = {block.block_id: block for block in document.blocks}
        warnings: List[str] = []
        drafts: List[ScientificChunk] = []
        special_source_ids = {
            block_id
            for evidence in (*logical_tables, *logical_figures)
            for block_id in evidence.source_block_ids
        }
        special_source_ids.update(formula.source_block_id for formula in logical_formulas)

        drafts.extend(self._abstract_chunks(document))
        drafts.extend(self._table_chunks(document, logical_tables, blocks, warnings))
        drafts.extend(self._figure_chunks(document, logical_figures, blocks, warnings))
        drafts.extend(self._formula_chunks(document, logical_formulas, blocks, warnings))
        drafts.extend(self._paragraph_chunks(document, special_source_ids))

        drafts.sort(
            key=lambda chunk: (
                chunk._anchor_order,
                _content_priority(chunk.content_type),
                chunk.part_index,
            )
        )
        title = document.metadata.title or document.filename
        used_chunk_ids: set[str] = set()
        for index, chunk in enumerate(drafts, 1):
            chunk.chunk_index = index
            chunk.legacy_chunk_id = f"{document.paper_id}:chunk_{index:04d}"
            chunk.chunk_id = _stable_chunk_id(document.paper_id, chunk, used_chunk_ids)
            prefix = [title]
            if chunk.section_path:
                prefix.append(" > ".join(chunk.section_path))
            chunk.retrieval_text = "\n".join(prefix + [chunk.text]).strip()
            chunk.token_count = self._token_count(chunk.text)

        self._validate_sources(drafts, blocks)
        return ChunkingResult(chunks=drafts, warnings=list(dict.fromkeys(warnings)))

    def _abstract_chunks(self, document: PaperDocument) -> List[ScientificChunk]:
        abstract_blocks = [
            block
            for block in document.blocks
            if block.type in {"paragraph", "list_item"}
            and (
                block.relations.get("section_kind") == "abstract"
                or any(part.strip().lower() == "abstract" for part in block.section_path)
            )
        ]
        title_blocks = [block for block in document.blocks if block.type == "title"]
        abstract_text = "\n\n".join(block.text for block in abstract_blocks if block.text)
        if not abstract_text:
            return []

        header_parts = []
        if document.metadata.title:
            header_parts.append(document.metadata.title)
        if document.metadata.authors:
            header_parts.append(", ".join(document.metadata.authors))
        header_parts.append("Abstract")
        core = "\n".join(header_parts)
        source_blocks = title_blocks + abstract_blocks
        if not source_blocks and document.blocks:
            source_blocks = [document.blocks[0]]
        source_ids = [block.block_id for block in source_blocks]
        anchor = min((block.order for block in source_blocks), default=0)
        units = self._split_text(
            abstract_text,
            max(1, self.config.max_tokens - self._token_count(core)),
        )
        chunks = []
        for part_index, unit in enumerate(units, 1):
            text = f"{core}\n\n{unit}".strip()
            chunk_warnings = (
                ["oversized_atomic_unit"]
                if self._token_count(text) > self.config.max_tokens
                else []
            )
            chunks.append(
                self._new_chunk(
                    document,
                    content_type="abstract",
                    text=text,
                    section_path=["Abstract"],
                    source_block_ids=source_ids,
                    pages=_pages(source_blocks),
                    part_index=part_index,
                    part_count=len(units),
                    warnings=chunk_warnings,
                    anchor_order=anchor,
                )
            )
        return chunks

    def _paragraph_chunks(
        self, document: PaperDocument, special_source_ids: set[str]
    ) -> List[ScientificChunk]:
        chunks: List[ScientificChunk] = []
        group: List[ContentBlock] = []
        current_path: Optional[List[str]] = None

        def flush() -> None:
            nonlocal group, current_path
            if group:
                chunks.extend(self._pack_paragraph_group(document, group))
            group = []
            current_path = None

        for block in document.blocks:
            is_candidate = (
                block.type in {"paragraph", "list_item"}
                and bool(block.text.strip())
                and block.block_id not in special_source_ids
                and block.relations.get("section_kind") not in {"abstract", "reference"}
            )
            lowered_path = [part.strip().lower() for part in block.section_path]
            if (
                not is_candidate
                or "abstract" in lowered_path
                or any(part.startswith("reference") for part in lowered_path)
            ):
                # Any structural object between prose blocks is a semantic
                # boundary, even when both prose blocks share section_path.
                flush()
                continue
            if current_path is None or block.section_path == current_path:
                group.append(block)
                current_path = list(block.section_path)
            else:
                flush()
                group = [block]
                current_path = list(block.section_path)
        flush()
        return chunks

    def _pack_paragraph_group(
        self, document: PaperDocument, group: Sequence[ContentBlock]
    ) -> List[ScientificChunk]:
        if not group:
            return []
        units: List[Tuple[str, str, ContentBlock]] = []
        for block in group:
            for text in self._split_text(block.text, self.config.max_tokens):
                units.append((block.block_id, text, block))

        packed: List[List[Tuple[str, str, ContentBlock]]] = []
        current: List[Tuple[str, str, ContentBlock]] = []
        for unit in units:
            candidate = "\n\n".join(item[1] for item in current + [unit])
            if current and self._token_count(candidate) > self.config.max_tokens:
                packed.append(current)
                current = []
            current.append(unit)
            current_tokens = self._token_count(
                "\n\n".join(item[1] for item in current)
            )
            if current_tokens >= self.config.target_tokens:
                packed.append(current)
                current = []
        if current:
            packed.append(current)

        chunks = []
        for part_index, part in enumerate(packed, 1):
            part_blocks = [item[2] for item in part]
            text = "\n\n".join(item[1] for item in part)
            chunk_warnings = (
                ["oversized_atomic_unit"]
                if self._token_count(text) > self.config.max_tokens
                else []
            )
            chunks.append(
                self._new_chunk(
                    document,
                    content_type="paragraph",
                    text=text,
                    section_path=list(group[0].section_path),
                    source_block_ids=list(dict.fromkeys(item[0] for item in part)),
                    pages=_pages(part_blocks),
                    part_index=part_index,
                    part_count=len(packed),
                    warnings=chunk_warnings,
                    anchor_order=min(block.order for block in part_blocks),
                )
            )
        return chunks

    def _table_chunks(
        self,
        document: PaperDocument,
        tables: Sequence[LogicalTable],
        blocks: Dict[str, ContentBlock],
        warnings: List[str],
    ) -> List[ScientificChunk]:
        chunks: List[ScientificChunk] = []
        for table in tables:
            source_blocks = _existing_blocks(table.source_block_ids, blocks)
            if not source_blocks:
                warnings.append(f"{table.table_id}: source blocks missing")
                continue
            caption_lines = [table.caption.strip()] if table.caption else []
            # Build parts per physical source block. This prevents a chunk on
            # page N from claiming all pages and blocks of a multi-page table.
            table_parts: List[
                Tuple[str, ContentBlock, int, Optional[int], Optional[int], List[str]]
            ] = []
            logical_row = 0
            structure_warning_recorded = False
            for fragment_index, source in enumerate(source_blocks, 1):
                lines = [line.strip() for line in source.text.splitlines() if line.strip()]
                if table.caption:
                    lines = [line for line in lines if line != table.caption.strip()]
                separator = next(
                    (
                        index
                        for index, line in enumerate(lines)
                        if _is_markdown_separator(line)
                    ),
                    None,
                )
                if separator is None:
                    header: List[str] = []
                    rows = lines
                    base_warnings = ["table_row_structure_unavailable"]
                    if not structure_warning_recorded:
                        warnings.append(
                            f"{table.table_id}: table row structure unavailable; "
                            "used bounded line fallback"
                        )
                        structure_warning_recorded = True
                else:
                    header = lines[: separator + 1]
                    rows = lines[separator + 1 :]
                    base_warnings = []

                core_lines = caption_lines + header
                core = "\n".join(core_lines).strip()
                core_tokens = self._token_count(core)
                if rows and core_tokens >= self.config.max_tokens:
                    # Repeating an over-budget caption/header is impossible.
                    # Split the whole physical fragment deterministically and
                    # retain an explicit quality warning instead of emitting an
                    # oversized chunk.
                    combined = "\n".join(core_lines + rows).strip()
                    for unit in self._split_text(combined, self.config.max_tokens):
                        table_parts.append(
                            (
                                unit,
                                source,
                                fragment_index,
                                None,
                                None,
                                base_warnings + ["table_core_split"],
                            )
                        )
                    continue

                available = max(1, self.config.max_tokens - core_tokens)
                row_units: List[Tuple[int, str, bool]] = []
                for row in rows:
                    logical_row += 1
                    pieces = self._split_text(row, available)
                    for piece in pieces:
                        row_units.append((logical_row, piece, len(pieces) > 1))

                if not row_units:
                    if core:
                        for unit in self._split_text(core, self.config.max_tokens):
                            table_parts.append(
                                (
                                    unit,
                                    source,
                                    fragment_index,
                                    None,
                                    None,
                                    list(base_warnings),
                                )
                            )
                    continue

                groups: List[List[Tuple[int, str, bool]]] = []
                current: List[Tuple[int, str, bool]] = []
                for unit in row_units:
                    candidate = "\n".join(
                        core_lines + [item[1] for item in current] + [unit[1]]
                    )
                    if current and self._token_count(candidate) > self.config.max_tokens:
                        groups.append(current)
                        current = []
                    current.append(unit)
                    current_text = "\n".join(
                        core_lines + [item[1] for item in current]
                    )
                    if self._token_count(current_text) >= self.config.target_tokens:
                        groups.append(current)
                        current = []
                if current:
                    groups.append(current)

                for group in groups:
                    text = "\n".join(core_lines + [item[1] for item in group]).strip()
                    chunk_warnings = list(base_warnings)
                    if any(item[2] for item in group):
                        chunk_warnings.append("split_oversized_table_row")
                    table_parts.append(
                        (
                            text,
                            source,
                            fragment_index,
                            group[0][0],
                            group[-1][0],
                            chunk_warnings,
                        )
                    )

            if not table_parts:
                warnings.append(
                    f"{table.table_id}: no textual table evidence; skipped"
                )
                continue

            part_count = len(table_parts)
            for part_index, (
                text,
                source,
                fragment_index,
                row_start,
                row_end,
                chunk_warnings,
            ) in enumerate(table_parts, 1):
                chunks.append(
                    self._new_chunk(
                        document,
                        content_type="table",
                        text=text,
                        section_path=list(table.section_path),
                        source_block_ids=[source.block_id],
                        caption_block_ids=list(table.caption_block_ids),
                        pages=[source.page] if source.page is not None else [],
                        table_id=table.table_id,
                        table_identifier=table.identifier,
                        fragment_indexes=[fragment_index],
                        part_index=part_index,
                        part_count=part_count,
                        row_start=row_start,
                        row_end=row_end,
                        warnings=list(dict.fromkeys(chunk_warnings)),
                        anchor_order=source.order,
                    )
                )
        return chunks

    def _figure_chunks(
        self,
        document: PaperDocument,
        figures: Sequence[LogicalFigure],
        blocks: Dict[str, ContentBlock],
        warnings: List[str],
    ) -> List[ScientificChunk]:
        chunks: List[ScientificChunk] = []
        for figure in figures:
            source_blocks = _existing_blocks(figure.source_block_ids, blocks)
            if not source_blocks:
                warnings.append(f"{figure.figure_id}: source blocks missing")
                continue
            descriptions = [
                block
                for block in source_blocks
                if block.text.strip()
                and not _looks_like_image_path(block.text.strip())
                and block.text.strip() != (figure.caption or "").strip()
            ]
            core = (figure.caption or "").strip()
            if not core and not descriptions:
                warnings.append(f"{figure.figure_id}: no caption or textual description; skipped")
                continue
            explanation_blocks = _existing_blocks(figure.explanation_block_ids, blocks)
            context_blocks = list(
                {
                    block.block_id: block
                    for block in descriptions + explanation_blocks
                }.values()
            )
            chunks.extend(
                self._evidence_chunks(
                    document,
                    content_type="figure",
                    entity_id=figure.figure_id,
                    core=core,
                    source_blocks=source_blocks,
                    caption_block_ids=list(figure.caption_block_ids),
                    context_blocks=context_blocks,
                    section_path=list(figure.section_path),
                    anchor_order=min(block.order for block in source_blocks),
                    is_generated_description=figure.is_generated_description,
                )
            )
        return chunks

    def _formula_chunks(
        self,
        document: PaperDocument,
        formulas: Sequence[LogicalFormula],
        blocks: Dict[str, ContentBlock],
        warnings: List[str],
    ) -> List[ScientificChunk]:
        chunks: List[ScientificChunk] = []
        for formula in formulas:
            source = blocks.get(formula.source_block_id)
            if source is None:
                warnings.append(f"{formula.formula_id}: source block missing")
                continue
            context_blocks = _existing_blocks(formula.context_block_ids, blocks)
            if not formula.text.strip():
                warnings.append(f"{formula.formula_id}: formula text missing; skipped")
                continue
            if not context_blocks:
                warnings.append(f"{formula.formula_id}: context missing; skipped")
                continue
            chunks.extend(
                self._evidence_chunks(
                    document,
                    content_type="formula",
                    entity_id=formula.formula_id,
                    core=formula.text.strip(),
                    source_blocks=[source],
                    context_blocks=context_blocks,
                    section_path=list(formula.section_path),
                    anchor_order=source.order,
                )
            )
        return chunks

    def _evidence_chunks(
        self,
        document: PaperDocument,
        *,
        content_type: str,
        entity_id: str,
        core: str,
        source_blocks: Sequence[ContentBlock],
        context_blocks: Sequence[ContentBlock],
        section_path: List[str],
        anchor_order: int,
        caption_block_ids: Optional[List[str]] = None,
        is_generated_description: bool = False,
    ) -> List[ScientificChunk]:
        source_block_ids = [block.block_id for block in source_blocks]
        core_tokens = self._token_count(core)
        core_parts = (
            self._split_text(core, self.config.target_tokens)
            if core and core_tokens >= self.config.max_tokens
            else ([core] if core else [])
        )
        anchor = core_parts[0] if core_parts else ""
        available = max(1, self.config.max_tokens - self._token_count(anchor))
        context_units: List[Tuple[str, str, ContentBlock]] = []
        for block in context_blocks:
            for text in self._split_text(block.text, available):
                context_units.append((block.block_id, text, block))

        groups: List[List[Tuple[str, str, ContentBlock]]] = []
        current: List[Tuple[str, str, ContentBlock]] = []
        for unit in context_units:
            candidate = "\n\n".join(
                [part for part in [anchor] + [item[1] for item in current] + [unit[1]] if part]
            )
            if current and self._token_count(candidate) > self.config.max_tokens:
                groups.append(current)
                current = []
            current.append(unit)
            current_text = "\n\n".join(
                [part for part in [anchor] + [item[1] for item in current] if part]
            )
            if self._token_count(current_text) >= self.config.target_tokens:
                groups.append(current)
                current = []
        if current:
            groups.append(current)

        specs: List[Tuple[str, List[Tuple[str, str, ContentBlock]], List[str]]] = []
        if len(core_parts) > 1:
            specs.extend(
                (part, [], ["split_oversized_evidence_core"])
                for part in core_parts
            )
        if groups:
            specs.extend(
                (
                    "\n\n".join(
                        [part for part in [anchor] + [item[1] for item in group] if part]
                    ).strip(),
                    group,
                    [],
                )
                for group in groups
            )
        elif len(core_parts) <= 1 and anchor:
            specs.append((anchor, [], []))

        chunks = []
        for part_index, (text, group, chunk_warnings) in enumerate(specs, 1):
            used_blocks = list(source_blocks) + [item[2] for item in group]
            chunks.append(
                self._new_chunk(
                    document,
                    content_type=content_type,
                    text=text,
                    section_path=section_path,
                    source_block_ids=source_block_ids,
                    context_block_ids=list(dict.fromkeys(item[0] for item in group)),
                    caption_block_ids=caption_block_ids or [],
                    pages=_pages(used_blocks),
                    figure_id=entity_id if content_type == "figure" else None,
                    formula_id=entity_id if content_type == "formula" else None,
                    part_index=part_index,
                    part_count=len(specs),
                    is_generated_description=is_generated_description,
                    warnings=chunk_warnings,
                    anchor_order=anchor_order,
                )
            )
        return chunks

    def _split_text(self, text: str, max_tokens: int) -> List[str]:
        text = text.strip()
        if not text:
            return []
        if self._token_count(text) <= max_tokens:
            return [text]
        sentences = [
            part.strip()
            for part in _SENTENCE_BOUNDARY_RE.split(text)
            if part.strip()
        ]
        if len(sentences) == 1:
            return _split_by_words(text, max_tokens, self._token_count)
        parts: List[str] = []
        current: List[str] = []
        for sentence in sentences:
            units = (
                [sentence]
                if self._token_count(sentence) <= max_tokens
                else _split_by_words(sentence, max_tokens, self._token_count)
            )
            for unit in units:
                candidate = " ".join(current + [unit])
                if current and self._token_count(candidate) > max_tokens:
                    parts.append(" ".join(current))
                    current = []
                current.append(unit)
        if current:
            parts.append(" ".join(current))
        return parts

    def _new_chunk(
        self,
        document: PaperDocument,
        *,
        content_type: str,
        text: str,
        section_path: List[str],
        source_block_ids: List[str],
        pages: List[int],
        context_block_ids: Optional[List[str]] = None,
        caption_block_ids: Optional[List[str]] = None,
        table_id: Optional[str] = None,
        table_identifier: Optional[str] = None,
        figure_id: Optional[str] = None,
        formula_id: Optional[str] = None,
        fragment_indexes: Optional[List[int]] = None,
        part_index: int = 1,
        part_count: int = 1,
        row_start: Optional[int] = None,
        row_end: Optional[int] = None,
        is_generated_description: bool = False,
        warnings: Optional[List[str]] = None,
        anchor_order: int = 10**9,
    ) -> ScientificChunk:
        return ScientificChunk(
            schema_version=CHUNK_SCHEMA_VERSION,
            chunk_id="",
            paper_id=document.paper_id,
            file_id=document.file_id,
            chunk_index=0,
            content_type=content_type,
            text=text,
            retrieval_text="",
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            section_path=section_path,
            source_block_ids=list(dict.fromkeys(source_block_ids)),
            context_block_ids=list(dict.fromkeys(context_block_ids or [])),
            caption_block_ids=list(dict.fromkeys(caption_block_ids or [])),
            table_id=table_id,
            table_identifier=table_identifier,
            figure_id=figure_id,
            formula_id=formula_id,
            fragment_indexes=list(dict.fromkeys(fragment_indexes or [])),
            part_index=part_index,
            part_count=part_count,
            row_start=row_start,
            row_end=row_end,
            token_count=self._token_count(text),
            is_generated_description=is_generated_description,
            warnings=warnings or [],
            _anchor_order=anchor_order,
        )

    @staticmethod
    def _validate_sources(
        chunks: Sequence[ScientificChunk], blocks: Dict[str, ContentBlock]
    ) -> None:
        known = set(blocks)
        for chunk in chunks:
            if not chunk.source_block_ids:
                raise ValueError(f"{chunk.chunk_id}: chunk has no source blocks")
            dangling = (
                set(chunk.source_block_ids)
                | set(chunk.context_block_ids)
                | set(chunk.caption_block_ids)
            ) - known
            if dangling:
                raise ValueError(
                    f"{chunk.chunk_id}: dangling block references: {sorted(dangling)}"
                )


def estimate_tokens(text: str) -> int:
    """Return a deterministic local estimate suitable for chunk budgeting."""
    return len(_TOKEN_RE.findall(text or ""))


def _split_by_words(
    text: str,
    max_tokens: int,
    token_counter: Callable[[str], int] = estimate_tokens,
) -> List[str]:
    words = text.split()
    if not words:
        tokens = _TOKEN_RE.findall(text)
        return [
            "".join(tokens[index : index + max_tokens])
            for index in range(0, len(tokens), max_tokens)
        ]
    parts: List[str] = []
    current: List[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        if current and token_counter(candidate) > max_tokens:
            parts.append(" ".join(current))
            current = []
        if token_counter(word) > max_tokens:
            if current:
                parts.append(" ".join(current))
                current = []
            # Custom tokenizers may count a lexical word as many model tokens.
            # Fall back to deterministic character windows until every piece
            # satisfies the injected counter.
            pending = [word]
            while pending:
                value = pending.pop(0)
                if token_counter(value) <= max_tokens or len(value) <= 1:
                    parts.append(value)
                    continue
                midpoint = max(1, len(value) // 2)
                pending[0:0] = [value[:midpoint], value[midpoint:]]
        else:
            current.append(word)
    if current:
        parts.append(" ".join(current))
    return parts


def _stable_chunk_id(
    paper_id: str, chunk: ScientificChunk, used_ids: set[str]
) -> str:
    anchor = (
        chunk.table_id
        or chunk.figure_id
        or chunk.formula_id
        or (chunk.source_block_ids[0] if chunk.source_block_ids else chunk.content_type)
    )
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", anchor).strip("_") or "evidence"
    base = (
        f"{paper_id}:{chunk.content_type}:{slug}:"
        f"part_{chunk.part_index:04d}"
    )
    candidate = base
    duplicate = 2
    while candidate in used_ids:
        candidate = f"{base}:duplicate_{duplicate:02d}"
        duplicate += 1
    used_ids.add(candidate)
    return candidate


def _is_markdown_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _looks_like_image_path(text: str) -> bool:
    candidate = text.strip().strip("![]()")
    return bool(_IMAGE_PATH_RE.fullmatch(candidate))


def _existing_blocks(
    block_ids: Iterable[str], blocks: Dict[str, ContentBlock]
) -> List[ContentBlock]:
    return [blocks[block_id] for block_id in block_ids if block_id in blocks]


def _pages(blocks: Sequence[ContentBlock]) -> List[int]:
    return sorted({block.page for block in blocks if block.page is not None})


def _page_range(start: Optional[int], end: Optional[int]) -> List[int]:
    if start is None and end is None:
        return []
    if start is None:
        return [end] if end is not None else []
    if end is None:
        return [start]
    return list(range(start, end + 1))


def _content_priority(content_type: str) -> int:
    return {
        "abstract": 0,
        "paragraph": 1,
        "table": 2,
        "figure": 3,
        "formula": 4,
    }.get(content_type, 9)
