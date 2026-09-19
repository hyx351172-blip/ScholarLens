"""Replay ScholarLens Chunker v2 on saved structured parser artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"
sys.path.insert(0, str(UNIFIED_DIR))

from chunkers.structure_aware_chunker import (  # noqa: E402
    ChunkingConfig,
    StructureAwareChunker,
)
from parsers.evidence_context_postprocessor import (  # noqa: E402
    EvidenceContextPostProcessor,
)
from parsers.models import (  # noqa: E402
    ContentBlock,
    PaperDocument,
    PaperMetadata,
    ParseQualityReport,
    ParserInfo,
    Section,
)
from parsers.table_postprocessor import TablePostProcessor  # noqa: E402


def _load_document(path: Path) -> PaperDocument:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PaperDocument(
        schema_version=raw["schema_version"],
        paper_id=raw["paper_id"],
        file_id=raw["file_id"],
        filename=raw["filename"],
        parser=ParserInfo(**raw.get("parser", {})),
        metadata=PaperMetadata(**raw.get("metadata", {})),
        sections=[Section(**item) for item in raw.get("sections", [])],
        blocks=[ContentBlock(**item) for item in raw.get("blocks", [])],
        quality=ParseQualityReport(**raw.get("quality", {})),
    )


def evaluate(path: Path, config: ChunkingConfig) -> dict[str, Any]:
    document = _load_document(path)
    table_result = TablePostProcessor().process(document.blocks)
    evidence_result = EvidenceContextPostProcessor().process(table_result.blocks)
    normalized = replace(document, blocks=evidence_result.blocks)
    result = StructureAwareChunker(config).chunk(
        normalized,
        logical_tables=table_result.tables,
        logical_figures=evidence_result.figures,
        logical_formulas=evidence_result.formulas,
    )
    counts = Counter(chunk.content_type for chunk in result.chunks)
    oversized = [
        chunk
        for chunk in result.chunks
        if chunk.token_count > config.max_tokens
    ]
    known = {block.block_id for block in normalized.blocks}
    blocks_by_id = {block.block_id: block for block in normalized.blocks}
    dangling = sorted(
        {
            block_id
            for chunk in result.chunks
            for block_id in (
                chunk.source_block_ids
                + chunk.context_block_ids
                + chunk.caption_block_ids
            )
            if block_id not in known
        }
    )
    chunk_ids = [chunk.chunk_id for chunk in result.chunks]
    expected_table_sources = {
        block_id
        for table in table_result.tables
        for block_id in table.source_block_ids
        if block_id in known and blocks_by_id[block_id].text.strip()
    }
    empty_table_sources = {
        block_id
        for table in table_result.tables
        for block_id in table.source_block_ids
        if block_id in known and not blocks_by_id[block_id].text.strip()
    }
    chunked_table_sources = {
        block_id
        for chunk in result.chunks
        if chunk.content_type == "table"
        for block_id in chunk.source_block_ids
    }
    return {
        "filename": document.filename,
        "blocks": len(document.blocks),
        "logical_tables": len(table_result.tables),
        "logical_figures": len(evidence_result.figures),
        "logical_formulas": len(evidence_result.formulas),
        "chunks": len(result.chunks),
        "content_type_counts": dict(sorted(counts.items())),
        "max_tokens": max((chunk.token_count for chunk in result.chunks), default=0),
        "oversized_chunks": len(oversized),
        "oversized_ids": [chunk.chunk_id for chunk in oversized],
        "dangling_block_ids": dangling,
        "duplicate_chunk_ids": len(chunk_ids) - len(set(chunk_ids)),
        "missing_table_source_ids": sorted(
            expected_table_sources - chunked_table_sources
        ),
        "empty_table_source_ids": sorted(empty_table_sources),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="document.json or a dataset directory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--target-tokens", type=int, default=600)
    parser.add_argument("--max-tokens", type=int, default=900)
    args = parser.parse_args()

    paths = (
        [args.input]
        if args.input.is_file()
        else sorted(args.input.rglob("document.json"))
    )
    config = ChunkingConfig(
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
    )
    papers = [evaluate(path, config) for path in paths]
    report = {
        "schema_version": "1.0",
        "target_tokens": config.target_tokens,
        "max_tokens": config.max_tokens,
        "papers": papers,
        "summary": {
            "paper_count": len(papers),
            "total_chunks": sum(item["chunks"] for item in papers),
            "oversized_chunks": sum(item["oversized_chunks"] for item in papers),
            "papers_with_dangling_ids": sum(
                bool(item["dangling_block_ids"]) for item in papers
            ),
            "duplicate_chunk_ids": sum(item["duplicate_chunk_ids"] for item in papers),
            "missing_table_source_ids": sum(
                len(item["missing_table_source_ids"]) for item in papers
            ),
            "empty_table_source_ids": sum(
                len(item["empty_table_source_ids"]) for item in papers
            ),
            "max_tokens_observed": max(
                (item["max_tokens"] for item in papers), default=0
            ),
        },
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    return 1 if report["summary"]["oversized_chunks"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
