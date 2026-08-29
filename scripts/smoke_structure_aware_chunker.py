"""Parse one real PDF and report structure-aware chunking statistics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"
sys.path.insert(0, str(UNIFIED_DIR))

from chunkers.structure_aware_chunker import StructureAwareChunker  # noqa: E402
from parsers.docling_parser import DoclingParser  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    parsed = DoclingParser(table_mode="accurate", do_ocr=False).parse(args.pdf)
    result = StructureAwareChunker().chunk(
        parsed.document,
        logical_tables=parsed.logical_tables,
        logical_figures=parsed.logical_figures,
        logical_formulas=parsed.logical_formulas,
    ).to_dict()
    block_ids = {block.block_id for block in parsed.document.blocks}
    dangling = sorted(
        {
            block_id
            for chunk in result["chunks"]
            for key in ("source_block_ids", "context_block_ids", "caption_block_ids")
            for block_id in chunk[key]
            if block_id not in block_ids
        }
    )
    summary = {
        "filename": parsed.document.filename,
        "pages": parsed.document.quality.total_pages,
        "blocks": len(parsed.document.blocks),
        "logical_tables": len(parsed.logical_tables),
        "logical_figures": len(parsed.logical_figures),
        "logical_formulas": len(parsed.logical_formulas),
        "chunk_stats": result["chunk_stats"],
        "warnings": result["warnings"],
        "dangling_block_ids": dangling,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 1 if dangling else 0


if __name__ == "__main__":
    raise SystemExit(main())
