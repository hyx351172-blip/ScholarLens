"""Generate a reviewable table-ground-truth draft from PDFs and Docling artifacts.

This script does not claim automated output is human truth. It pre-fills the
repetitive mapping work and marks every element as pending human review.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pymupdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = PROJECT_ROOT / "output" / "uploads" / "2026" / "08" / "27"
DOCLING_DIR = PROJECT_ROOT / "output" / "docling_evaluation_v1"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "evaluation" / "table-ground-truth-v1.json"


PAPERS: Dict[str, Dict[str, Any]] = {
    "charactereval": {
        "display_name": "CharacterEval",
        "filename": "file_20260827_c11e9075_2024.acl-long.638.pdf",
        "table_pages": {1: 6, 2: 7, 3: 7, 4: 9, 5: 14},
    },
    "gaap": {
        "display_name": "GAAP",
        "filename": "file_20260827_a3b1a024_2604.19657v1.pdf",
        "table_pages": {1: 3, 2: 8, 3: 10, 4: 17, 5: 18},
    },
    "memlineage": {
        "display_name": "MemLineage",
        "filename": "file_20260827_9e0dae27_2605.14421v1.pdf",
        "table_pages": {
            1: 13, 2: 14, 3: 15, 4: 16, 5: 16, 6: 16, 7: 17,
            8: 18, 9: 18, 10: 18, 11: 19, 12: 19, 13: 19,
        },
    },
    "map_graph": {
        "display_name": "MAP-Graph",
        "filename": "file_20260827_d6b086f1_2608.10509v1.pdf",
        "table_pages": {
            1: 6, 2: 7, 3: 7, 4: 9, 5: 10, 6: 10,
            7: 13, 8: 13, 9: 13, 10: 13, 11: 13,
        },
    },
}


ISSUE_OVERRIDES: Dict[Tuple[str, int], Dict[str, Any]] = {
    ("charactereval", 4): {
        "docling_status": "fragmented",
        "expected_action": "merge",
        "layout": "multi_panel",
        "expected_panels": 2,
        "issues": ["one_logical_table_split_into_two_table_blocks"],
        "draft_confidence": "high",
    },
    ("charactereval", 5): {
        "docling_status": "fragmented",
        "expected_action": "merge",
        "layout": "multi_panel",
        "expected_panels": 2,
        "issues": ["one_logical_table_split_into_two_table_blocks"],
        "draft_confidence": "high",
    },
    ("gaap", 4): {
        "docling_status": "fragmented",
        "expected_action": "merge",
        "layout": "column_continuation",
        "expected_panels": 2,
        "issues": ["one_logical_table_split_at_column_boundary"],
        "draft_confidence": "high",
    },
    ("memlineage", 4): {
        "docling_status": "caption_misbound",
        "expected_action": "split_and_attach_caption",
        "layout": "single_table",
        "expected_panels": 1,
        "issues": [
            "table_4_cells_are_inside_block_000254",
            "block_000254_is_wrongly_bound_to_table_5_caption",
        ],
        "draft_confidence": "high",
    },
    ("memlineage", 5): {
        "docling_status": "caption_detached",
        "expected_action": "attach_caption",
        "layout": "single_table",
        "expected_panels": 1,
        "issues": [
            "table_5_data_is_block_000256",
            "table_5_caption_is_wrongly_associated_with_block_000254",
        ],
        "draft_confidence": "high",
    },
    ("map_graph", 9): {
        "docling_status": "caption_detached",
        "expected_action": "attach_caption",
        "issues": ["caption_precedes_table_as_independent_block"],
        "draft_confidence": "high",
    },
    ("map_graph", 10): {
        "docling_status": "caption_detached",
        "expected_action": "attach_caption",
        "issues": ["caption_precedes_table_as_independent_block"],
        "draft_confidence": "high",
    },
    ("map_graph", 11): {
        "docling_status": "caption_detached",
        "expected_action": "attach_caption",
        "issues": ["caption_precedes_table_as_independent_block"],
        "draft_confidence": "high",
    },
}


MANUAL_BLOCK_MAPPING: Dict[Tuple[str, int], Dict[str, List[str]]] = {
    ("memlineage", 4): {
        "table_block_ids": ["block_000254"],
        "caption_block_ids": [],
        "conflicting_block_ids": ["block_000255"],
    },
    ("memlineage", 5): {
        "table_block_ids": ["block_000256"],
        "caption_block_ids": ["block_000255"],
        "conflicting_block_ids": ["block_000254"],
    },
}


def compact(text: str) -> str:
    return " ".join(text.replace("\ufffd", "").split())


def label_number(text: str, kind: str = "Table") -> Optional[int]:
    match = re.match(rf"^{kind}\s+(\d+)\s*[:.]", compact(text), re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_pdf_captions(pdf_path: Path) -> Dict[int, Dict[str, Any]]:
    captions: Dict[int, Dict[str, Any]] = {}
    with pymupdf.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, 1):
            for raw_block in page.get_text("blocks"):
                text = compact(raw_block[4])
                number = label_number(text)
                if number is None:
                    continue
                captions.setdefault(
                    number,
                    {
                        "caption": text,
                        "page": page_number,
                        "caption_source": "original_pdf_text_block",
                    },
                )
    return captions


def block_index(blocks: Iterable[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    return {int(block["order"]): block for block in blocks}


def infer_mapping(
    paper_key: str,
    table_number: int,
    blocks: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    override = MANUAL_BLOCK_MAPPING.get((paper_key, table_number))
    if override:
        return override

    by_order = block_index(blocks)
    table_ids: List[str] = []
    caption_ids: List[str] = []
    conflicting_ids: List[str] = []

    for block in blocks:
        if block.get("type") == "caption" and label_number(block.get("text", "")) == table_number:
            caption_ids.append(block["block_id"])

    for block in blocks:
        if block.get("type") != "table":
            continue
        direct_number = label_number(block.get("text", ""))
        if direct_number == table_number:
            table_ids.append(block["block_id"])
            continue
        # A table block with its own explicit label must not also inherit an
        # adjacent caption belonging to a different logical table. Docling can
        # emit a table's caption after the table, immediately before the next
        # table block, so unconditional previous-block association creates
        # duplicate mappings.
        if direct_number is not None:
            continue
        previous = by_order.get(int(block["order"]) - 1)
        if (
            previous
            and previous.get("type") == "caption"
            and label_number(previous.get("text", "")) == table_number
        ):
            table_ids.append(block["block_id"])

    return {
        "table_block_ids": list(dict.fromkeys(table_ids)),
        "caption_block_ids": list(dict.fromkeys(caption_ids)),
        "conflicting_block_ids": conflicting_ids,
    }


def caption_from_docling(
    table_number: int, blocks: List[Dict[str, Any]]
) -> Optional[str]:
    for block in blocks:
        if block.get("type") == "caption" and label_number(block.get("text", "")) == table_number:
            return compact(block.get("text", ""))
    for block in blocks:
        if block.get("type") == "table" and label_number(block.get("text", "")) == table_number:
            return compact(block.get("text", "")).split("|")[0].strip()
    return None


def table_element(
    paper_key: str,
    table_number: int,
    expected_page: int,
    blocks: List[Dict[str, Any]],
    pdf_captions: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    mapping = infer_mapping(paper_key, table_number, blocks)
    pdf_caption = pdf_captions.get(table_number)
    if pdf_caption:
        caption = pdf_caption["caption"]
        caption_source = pdf_caption["caption_source"]
        observed_page = pdf_caption["page"]
    else:
        caption = caption_from_docling(table_number, blocks)
        caption_source = "docling_caption_fallback"
        observed_page = expected_page

    override = ISSUE_OVERRIDES.get((paper_key, table_number), {})
    status = override.get("docling_status", "correct")
    action = override.get("expected_action", "keep")
    issues = list(override.get("issues", []))
    if not mapping["table_block_ids"]:
        status = "missing"
        action = "manual_recovery"
        issues.append("no_docling_table_block_mapped")

    return {
        "element_id": f"{paper_key}-table-{table_number}",
        "ground_truth_type": "table",
        "label": f"Table {table_number}",
        "pages": [expected_page],
        "caption": caption,
        "caption_source": caption_source,
        "pdf_caption_page_matches_expected": observed_page == expected_page,
        "layout": override.get("layout", "single_table"),
        "expected_panels": override.get("expected_panels", 1),
        "cross_page": False,
        **mapping,
        "docling_status": status,
        "expected_action": action,
        "issues": issues,
        "header_complete": None,
        "data_complete": None,
        "review_status": "pending_human_review",
        "reviewer_notes": "",
        "draft_confidence": override.get("draft_confidence", "medium" if status == "correct" else "high"),
    }


def confusing_elements(paper_key: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if paper_key != "memlineage":
        return []
    table_block = next(block for block in blocks if block["block_id"] == "block_000235")
    return [
        {
            "element_id": "memlineage-figure-3",
            "ground_truth_type": "figure",
            "label": "Figure 3",
            "pages": [14],
            "caption": compact(table_block["text"]).split("|")[0].strip(),
            "table_block_ids": ["block_000235"],
            "caption_block_ids": ["block_000236"],
            "docling_status": "misclassified",
            "expected_action": "retype_as_figure",
            "issues": ["heatmap_figure_classified_as_table"],
            "review_status": "pending_human_review",
            "reviewer_notes": "",
            "draft_confidence": "high",
        }
    ]


def build() -> Dict[str, Any]:
    paper_results = []
    all_elements: List[Dict[str, Any]] = []
    confusing_count = 0

    for paper_key, spec in PAPERS.items():
        pdf_path = UPLOAD_DIR / spec["filename"]
        document_path = DOCLING_DIR / paper_key / "document.json"
        document = json.loads(document_path.read_text(encoding="utf-8"))
        blocks = document["blocks"]
        pdf_captions = extract_pdf_captions(pdf_path)
        elements = [
            table_element(paper_key, number, page, blocks, pdf_captions)
            for number, page in spec["table_pages"].items()
        ]
        confusing = confusing_elements(paper_key, blocks)
        all_elements.extend(elements)
        confusing_count += len(confusing)
        paper_results.append(
            {
                "paper_id": paper_key,
                "display_name": spec["display_name"],
                "filename": spec["filename"],
                "source_pdf": str(
                    Path("output") / "uploads" / "2026" / "08" / "27" / spec["filename"]
                ).replace("\\", "/"),
                "docling_document": str(
                    Path("output") / "docling_evaluation_v1" / paper_key / "document.json"
                ).replace("\\", "/"),
                "expected_logical_table_count": len(spec["table_pages"]),
                "elements": elements,
                "confusing_non_table_elements": confusing,
            }
        )

    status_counts = Counter(element["docling_status"] for element in all_elements)
    return {
        "version": "table-ground-truth-v1-draft",
        "draft": True,
        "generated_at": datetime.now().astimezone().isoformat(),
        "review_status": "pending_human_review",
        "annotation_scope": "logical tables and table-like false positives; no cell-level ground truth yet",
        "annotation_guideline": {
            "page_numbering": "1-based",
            "logical_table_rule": "one numbered Table caption equals one logical table",
            "multi_panel_rule": "panels under one caption remain one logical table",
            "continuation_rule": "continuations without a new numbered caption remain the same logical table",
            "type_rule": "Figure/chart/heatmap remains a figure even when it contains a grid",
            "truth_source": "original PDF; Docling artifacts are predictions to be reviewed",
        },
        "allowed_docling_status": [
            "correct",
            "fragmented",
            "merged_wrongly",
            "caption_detached",
            "caption_misbound",
            "misclassified",
            "missing",
            "incomplete",
        ],
        "review_checklist": [
            "Confirm every numbered Table in the source PDF is present exactly once.",
            "Confirm pages, captions, table block IDs, and caption block IDs.",
            "Set header_complete and data_complete to true or false after visual comparison.",
            "Confirm fragmented blocks belong to one logical table before approving merge.",
            "Confirm confusing_non_table_elements are truly figures rather than tables.",
            "Change review_status to approved or corrected and add reviewer_notes.",
        ],
        "summary": {
            "papers": len(paper_results),
            "expected_logical_tables": len(all_elements),
            "confusing_non_table_elements": confusing_count,
            "status_counts": dict(sorted(status_counts.items())),
            "pending_human_review": len(all_elements) + confusing_count,
        },
        "papers": paper_results,
    }


def mark_reviewed(document: Dict[str, Any]) -> Dict[str, Any]:
    """Promote a generated draft after explicit human confirmation."""
    reviewed_at = datetime.now().astimezone().isoformat()
    document["version"] = "table-ground-truth-v1"
    document["draft"] = False
    document["review_status"] = "approved"
    document["reviewed_at"] = reviewed_at

    approved_count = 0
    for paper in document["papers"]:
        for element in paper["elements"]:
            element["header_complete"] = True
            element["data_complete"] = True
            element["review_status"] = "approved"
            element["reviewer_notes"] = "Human-reviewed and approved."
            approved_count += 1
        for element in paper["confusing_non_table_elements"]:
            element["review_status"] = "approved"
            element["reviewer_notes"] = "Human-reviewed and approved."
            approved_count += 1

    document["summary"]["pending_human_review"] = 0
    document["summary"]["approved"] = approved_count
    return document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate table annotation metadata from PDFs and Docling artifacts."
    )
    parser.add_argument(
        "--mark-reviewed",
        action="store_true",
        help="mark all generated annotations approved after explicit human review",
    )
    args = parser.parse_args()

    draft = build()
    if args.mark_reviewed:
        draft = mark_reviewed(draft)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote: {OUTPUT_PATH}")
    print(json.dumps(draft["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
