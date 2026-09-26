"""Re-export saved canonical documents to isolate serialization from inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "Information-Extraction" / "unified"))
from parsers.markdown_renderer import render_document_markdown
from parsers.models import ContentBlock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.artifact_dir.resolve()
    destination = args.output_dir.resolve()
    if destination == source or source in destination.parents:
        raise ValueError("Export to a separate directory to preserve the original artifacts")
    files = sorted(source.glob("*/document.json"))
    if not files:
        raise ValueError("No saved canonical documents found")
    predictions = destination / "predictions"
    predictions.mkdir(parents=True, exist_ok=True)
    records = []
    for path in files:
        raw = path.read_bytes()
        document = json.loads(raw)
        blocks = [ContentBlock(**item) for item in document["blocks"]]
        output_path = predictions / f"{path.parent.name}.md"
        output_path.write_text(render_document_markdown(blocks), encoding="utf-8")
        formulas = [block for block in blocks if block.type == "formula"]
        records.append({
            "image_path": document["filename"],
            "source_document_sha256": hashlib.sha256(raw).hexdigest(),
            "formulas": len(formulas),
            "nonempty_formulas": sum(bool(block.text.strip()) for block in formulas),
            "ocr_fallback_formulas": sum(block.relations.get("formula_text_source") == "orig_fallback" for block in formulas),
        })
    summary = {
        "scope": "export-only ablation; no OCR or formula model rerun",
        "pages": len(records),
        "results": records,
    }
    (destination / "reexport-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Re-exported {len(records)} pages to {destination}")


if __name__ == "__main__":
    main()
