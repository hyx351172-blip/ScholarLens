"""Replay saved native Docling JSON through the production adapter, without inference.

Writes a fresh output directory and verifies text, bindings and chunk compatibility.
No gold labels, model calls, embedding calls or database writes are involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend/Information-Extraction/unified"))

from scripts.evaluate_chunker_v2 import _load_document
from parsers.docling_parser import DoclingParser, save_parse_result
from parsers.evidence_context_postprocessor import LogicalFigure, LogicalFormula
from parsers.table_postprocessor import LogicalTable
from chunkers.structure_aware_chunker import StructureAwareChunker


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SavedDoclingConverter:
    """Explicit offline adapter, using already-completed native model output."""
    def __init__(self, path: Path):
        from docling_core.types.doc import DoclingDocument
        self.document = DoclingDocument.model_validate_json(path.read_text(encoding="utf-8"))

    def convert(self, _path: str):
        return SimpleNamespace(document=self.document)


def _load_evidence(path: Path, cls):
    return [cls(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def replay(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if output == source or source in output.parents:
        raise ValueError("Replay output must be outside the source directory")
    if output.exists():
        raise ValueError("Use a new output directory; never overwrite experiment evidence")
    documents = sorted((source / "artifacts").glob("*/document.json"))
    if not documents:
        raise ValueError("No saved parser artifacts found")
    # Preflight all input pairs before creating output.
    for path in documents:
        if not (path.parent / "docling-document.json").is_file() or not (source / "pdfs" / (path.parent.name + ".pdf")).is_file():
            raise ValueError(f"Missing native JSON or PDF for {path.parent.name}")
    output.mkdir(parents=True)
    (output / "predictions").mkdir()
    records, failures = [], []
    for path in documents:
        try:
            old = _load_document(path)
            pdf = source / "pdfs" / (path.parent.name + ".pdf")
            if _sha(pdf) != old.paper_id:
                raise ValueError("Saved PDF digest differs from the original parser document")
            native = path.parent / "docling-document.json"
            parsed = DoclingParser(
                converter=SavedDoclingConverter(native), table_mode=old.parser.table_mode,
                do_ocr=old.parser.ocr_enabled,
                do_formula_enrichment=old.parser.formula_enrichment_enabled,
            ).parse(pdf, file_id=old.file_id, original_filename=old.filename)
            destination = output / "artifacts" / path.parent.name
            save_parse_result(destination, parsed)
            (output / "predictions" / (path.parent.name + ".md")).write_text(parsed.markdown, encoding="utf-8")
            old_tables = _load_evidence(path.parent / "tables.json", LogicalTable)
            old_figures = _load_evidence(path.parent / "figures.json", LogicalFigure)
            old_formulas = _load_evidence(path.parent / "formulas.json", LogicalFormula)
            chunker = StructureAwareChunker()
            previous_chunks = chunker.chunk(old, logical_tables=old_tables,
                                            logical_figures=old_figures, logical_formulas=old_formulas).to_dict()
            current_chunks = chunker.chunk(parsed.document, logical_tables=parsed.logical_tables,
                                           logical_figures=parsed.logical_figures, logical_formulas=parsed.logical_formulas).to_dict()
            (destination / "chunks.json").write_text(json.dumps(current_chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            def legacy_blocks(blocks):
                return [{k: v for k, v in asdict(block).items() if k != "table_structure"} for block in blocks]
            structures = [block.table_structure for block in parsed.document.blocks if block.type == "table" and block.table_structure]
            record = {
                "page": old.filename, "source_document_sha256": _sha(path), "native_docling_sha256": _sha(native),
                "legacy_blocks_unchanged": legacy_blocks(old.blocks) == legacy_blocks(parsed.document.blocks),
                "logical_tables_unchanged": [asdict(t) for t in old_tables] == [asdict(t) for t in parsed.logical_tables],
                "chunks_unchanged": previous_chunks == current_chunks,
                "chunk_count": len(current_chunks["chunks"]),
                "table_count": len(structures), "valid_tables": sum(t["valid"] for t in structures),
                "cell_count": sum(len(t["table_cells"]) for t in structures),
                "spanning_cells": sum(c["row_span"] > 1 or c["col_span"] > 1 for t in structures for c in t["table_cells"]),
                "structure_warnings": [w for t in structures for w in t["warnings"]],
                "replay_seconds": parsed.document.quality.duration_seconds,
                "original_parse_seconds": old.quality.duration_seconds,
            }
            records.append(record)
            print(f"{old.filename}: {record['valid_tables']}/{record['table_count']} valid tables; chunks unchanged={record['chunks_unchanged']}")
        except Exception as exc:
            failures.append({"page": path.parent.name, "error": str(exc)})
    result = {
        "schema_version": "1.0", "mode": "saved_native_docling_replay_no_inference",
        "model_calls": 0, "api_calls": 0, "source_directory": str(source),
        "selected_pages": len(documents), "successful_pages": len(records), "failed_pages": len(failures),
        "compatibility_pass": all(r["legacy_blocks_unchanged"] and r["logical_tables_unchanged"] and r["chunks_unchanged"] for r in records) and not failures,
        "results": records, "failures": failures,
    }
    (output / "replay-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.source_dir, args.output_dir)
    print(json.dumps({k: v for k, v in result.items() if k not in {"results", "failures"}}, ensure_ascii=False, indent=2))
    return 0 if result["compatibility_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
