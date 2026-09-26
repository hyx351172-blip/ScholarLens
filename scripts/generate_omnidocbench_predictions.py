"""Generate ScholarLens/Docling predictions for an OmniDocBench subset.

OmniDocBench distributes rendered page images, while ScholarLens accepts PDF
inputs.  This adapter wraps each image in a lossless one-page PDF, runs the
same parser used by ScholarLens, and writes one Markdown prediction per page
using the filename contract expected by the official OmniDocBench evaluator.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"


def _image_name(page: dict[str, Any]) -> str:
    return str(page["page_info"]["image_path"])


def _subset_name(page: dict[str, Any]) -> str:
    return str(
        page["page_info"].get("page_attribute", {}).get("subset", "unknown")
    )


def select_stratified_pages(
    pages: list[dict[str, Any]], limit: int | None
) -> list[dict[str, Any]]:
    """Select a deterministic subset while retaining every available stratum."""

    ordered = sorted(pages, key=_image_name)
    if limit is None or limit >= len(ordered):
        return ordered
    if limit <= 0:
        raise ValueError("limit must be positive")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in ordered:
        groups[_subset_name(page)].append(page)
    keys = sorted(groups)
    selected_by_group: dict[str, int] = {key: 0 for key in keys}

    if limit >= len(keys):
        for key in keys:
            selected_by_group[key] = 1
    else:
        for key in sorted(keys, key=lambda value: (-len(groups[value]), value))[:limit]:
            selected_by_group[key] = 1

    while sum(selected_by_group.values()) < limit:
        candidates = [
            key
            for key in keys
            if selected_by_group[key] < len(groups[key])
        ]
        key = min(
            candidates,
            key=lambda value: (
                selected_by_group[value] / len(groups[value]),
                value,
            ),
        )
        selected_by_group[key] += 1

    selected = [
        page
        for key in keys
        for page in groups[key][: selected_by_group[key]]
    ]
    return sorted(selected, key=_image_name)


def image_to_pdf(image_path: Path, pdf_path: Path) -> None:
    """Wrap an image in a single-page PDF without resampling it."""

    with Image.open(image_path) as image:
        width, height = image.size
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    try:
        page = document.new_page(width=width, height=height)
        page.insert_image(page.rect, filename=str(image_path))
        document.save(pdf_path)
    finally:
        document.close()


def generate_predictions(
    *,
    annotations_path: Path,
    image_dir: Path,
    output_dir: Path,
    limit: int | None,
    table_mode: str,
    do_ocr: bool,
    reuse: bool,
    do_formula_enrichment: bool = True,
) -> dict[str, Any]:
    pages = json.loads(annotations_path.read_text(encoding="utf-8"))
    selected = select_stratified_pages(pages, limit)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = output_dir / "pdfs"
    prediction_dir = output_dir / "predictions"
    artifact_root = output_dir / "artifacts"
    prediction_dir.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    (output_dir / "selected_annotations.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if str(UNIFIED_DIR) not in sys.path:
        sys.path.insert(0, str(UNIFIED_DIR))
    from parsers.docling_parser import DoclingParser, save_parse_result

    parser = DoclingParser(
        table_mode=table_mode, do_ocr=do_ocr,
        do_formula_enrichment=do_formula_enrichment,
    )
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, page in enumerate(selected, 1):
        image_name = _image_name(page)
        image_path = image_dir / image_name
        stem = Path(image_name).stem
        pdf_path = pdf_dir / f"{stem}.pdf"
        prediction_path = prediction_dir / f"{stem}.md"
        artifact_dir = artifact_root / stem
        started = time.perf_counter()
        try:
            if not image_path.is_file():
                raise FileNotFoundError(f"Missing page image: {image_path}")
            if not pdf_path.is_file():
                image_to_pdf(image_path, pdf_path)

            reused = bool(
                reuse
                and prediction_path.is_file()
                and (artifact_dir / "document.json").is_file()
            )
            if reused:
                document = json.loads(
                    (artifact_dir / "document.json").read_text(encoding="utf-8")
                )
                config = document.get("parser", {})
                if (
                    config.get("formula_enrichment_enabled", False) != do_formula_enrichment
                    or config.get("ocr_enabled") != do_ocr
                    or config.get("table_mode") != table_mode
                ):
                    raise ValueError("Cached parser settings differ; use a new output directory")
                block_count = len(document.get("blocks", []))
                warning_count = len(document.get("quality", {}).get("warnings", []))
            else:
                parsed = parser.parse(pdf_path, original_filename=image_name)
                save_parse_result(artifact_dir, parsed)
                prediction_path.write_text(parsed.markdown, encoding="utf-8")
                block_count = len(parsed.document.blocks)
                warning_count = len(parsed.document.quality.warnings)

            elapsed = round(time.perf_counter() - started, 3)
            # A resumed run retains the original successful inference timing.
            # Cached loading time is separate and must not look like a speedup.
            inference_seconds = (
                document.get("quality", {}).get("duration_seconds", 0.0)
                if reused else elapsed
            )
            result = {
                "image_path": image_name,
                "subset": _subset_name(page),
                "layout": page["page_info"].get("page_attribute", {}).get("layout"),
                "prediction": str(prediction_path.relative_to(output_dir)),
                "blocks": block_count,
                "warnings": warning_count,
                "duration_seconds": inference_seconds,
                "current_run_seconds": elapsed,
                "reused": reused,
            }
            results.append(result)
            print(
                f"[{index}/{len(selected)}] {image_name}: "
                f"{block_count} blocks, {result['duration_seconds']:.2f}s"
            )
        except Exception as exc:  # Keep the batch auditable after one bad page.
            failures.append({"image_path": image_name, "error": str(exc)})
            print(f"[{index}/{len(selected)}] {image_name}: ERROR {exc}")

    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "ScholarLens Docling parser predictions for OmniDocBench",
        "annotations": annotations_path.name,
        "table_mode": table_mode,
        "ocr_enabled": do_ocr,
        "formula_enrichment_enabled": do_formula_enrichment,
        "selected_pages": len(selected),
        "successful_pages": len(results),
        "failed_pages": len(failures),
        "duration_seconds": round(sum(item["duration_seconds"] for item in results), 3),
        "subsets": {
            subset: sum(item["subset"] == subset for item in results)
            for subset in sorted({item["subset"] for item in results})
        },
        "results": results,
        "failures": failures,
    }
    (output_dir / "inference-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--table-mode", choices=("fast", "accurate"), default="accurate")
    parser.add_argument("--ocr", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--formula-enrichment", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    result = generate_predictions(
        annotations_path=args.annotations,
        image_dir=args.image_dir,
        output_dir=args.output_dir,
        limit=args.limit,
        table_mode=args.table_mode,
        do_ocr=args.ocr,
        reuse=args.reuse,
        do_formula_enrichment=args.formula_enrichment,
    )
    print(json.dumps({key: value for key, value in result.items() if key not in {"results", "failures"}}, ensure_ascii=False, indent=2))
    return 0 if not result["failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
