"""Re-chunk saved structured parser artifacts and index them in Milvus.

This script intentionally creates a new collection by default so a retrieval
experiment cannot overwrite an existing ScholarLens knowledge base.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
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


def _post_json(url: str, payload: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _get_json(url: str, timeout: int = 60) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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


def _chunk_document(path: Path, config: ChunkingConfig) -> tuple[PaperDocument, list[dict[str, Any]]]:
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
    chunks = [chunk.to_dict() for chunk in result.chunks]
    return normalized, chunks


def _create_collection(api_url: str, display_name: str) -> str:
    query = urllib.parse.urlencode({"display_name": display_name})
    result = _post_json(f"{api_url}/knowledge_base/create?{query}", {})
    collection_id = result.get("collection_id")
    if not collection_id:
        raise RuntimeError(f"Milvus API did not return collection_id: {result}")
    return str(collection_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="document.json or dataset directory")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--collection")
    parser.add_argument("--display-name", default="ScholarLens Chunker v2 retrieval baseline")
    parser.add_argument("--target-tokens", type=int, default=600)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    paths = [args.input] if args.input.is_file() else sorted(args.input.rglob("document.json"))
    if args.limit is not None:
        paths = paths[: args.limit]
    if not paths:
        raise SystemExit("No document.json artifacts found")

    collection_id = args.collection or _create_collection(args.api_url, args.display_name)
    existing_documents = _get_json(
        f"{args.api_url}/knowledge_base/{collection_id}/documents"
    ).get("documents", [])
    existing_by_filename = {
        str(item.get("filename")): item
        for item in existing_documents
        if item.get("filename")
    }
    config = ChunkingConfig(target_tokens=args.target_tokens, max_tokens=args.max_tokens)
    papers: list[dict[str, Any]] = []
    total_chunks = 0

    for index, path in enumerate(paths, 1):
        document, chunks = _chunk_document(path, config)
        if document.filename in existing_by_filename:
            existing = existing_by_filename[document.filename]
            count = int(existing.get("chunks", len(chunks)))
            total_chunks += count
            papers.append(
                {
                    "filename": document.filename,
                    "paper_id": document.paper_id,
                    "file_id": document.file_id,
                    "chunks": count,
                    "status": "already_indexed",
                }
            )
            print(
                f"[{index}/{len(paths)}] skipped {document.filename}: already indexed",
                file=sys.stderr,
            )
            continue
        payload = {
            "collection_name": collection_id,
            "file_data": {
                "filename": document.filename,
                "data": {
                    "chunks": chunks,
                    "metadata": {
                        "paper_id": document.paper_id,
                        "file_id": document.file_id,
                        "schema_version": "1.1",
                    },
                },
            },
        }
        response = _post_json(f"{args.api_url}/upload_json", payload)
        count = int(response.get("chunks_count", len(chunks)))
        total_chunks += count
        papers.append(
            {
                "filename": document.filename,
                "paper_id": document.paper_id,
                "file_id": document.file_id,
                "chunks": count,
                "status": "indexed",
            }
        )
        print(f"[{index}/{len(paths)}] indexed {document.filename}: {count} chunks", file=sys.stderr)

    manifest = {
        "schema_version": "1.0",
        "collection_id": collection_id,
        "display_name": args.display_name,
        "target_tokens": config.target_tokens,
        "max_tokens": config.max_tokens,
        "paper_count": len(papers),
        "total_chunks": total_chunks,
        "papers": papers,
    }
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
