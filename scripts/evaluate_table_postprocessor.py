"""Evaluate TablePostProcessor against the reviewed table ground truth."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"
sys.path.insert(0, str(UNIFIED_DIR))

from parsers.models import ContentBlock  # noqa: E402
from parsers.reading_order_postprocessor import ReadingOrderPostProcessor  # noqa: E402
from parsers.table_postprocessor import TablePostProcessor  # noqa: E402


def evaluate(ground_truth_path: Path) -> Dict[str, Any]:
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    processor = TablePostProcessor()
    reading_order_processor = ReadingOrderPostProcessor()
    paper_results: List[Dict[str, Any]] = []
    mismatches: List[Dict[str, Any]] = []

    totals = Counter()
    status_counts = Counter()
    for paper in ground_truth["papers"]:
        document_path = PROJECT_ROOT / paper["docling_document"]
        document = json.loads(document_path.read_text(encoding="utf-8"))
        blocks = [ContentBlock(**block) for block in document["blocks"]]
        reading_order_result = reading_order_processor.process(blocks)
        result = processor.process(reading_order_result.blocks)
        actual_by_label = {
            table.label: table for table in result.tables if table.label is not None
        }
        expected = paper["elements"]
        paper_counts = Counter(expected=len(expected), actual=len(result.tables))

        for truth in expected:
            actual = actual_by_label.get(truth["label"])
            totals["expected"] += 1
            if actual is None:
                mismatches.append(
                    {
                        "paper_id": paper["paper_id"],
                        "element_id": truth["element_id"],
                        "kind": "missing_logical_table",
                    }
                )
                continue
            totals["recalled"] += 1
            paper_counts["recalled"] += 1
            source_match = set(actual.source_block_ids) == set(truth["table_block_ids"])
            caption_match = set(actual.caption_block_ids) == set(
                truth["caption_block_ids"]
            )
            if source_match:
                totals["source_exact"] += 1
                paper_counts["source_exact"] += 1
            if caption_match:
                totals["caption_exact"] += 1
                paper_counts["caption_exact"] += 1
            if not source_match or not caption_match:
                mismatches.append(
                    {
                        "paper_id": paper["paper_id"],
                        "element_id": truth["element_id"],
                        "kind": "mapping_mismatch",
                        "expected_source_blocks": truth["table_block_ids"],
                        "actual_source_blocks": actual.source_block_ids,
                        "expected_caption_blocks": truth["caption_block_ids"],
                        "actual_caption_blocks": actual.caption_block_ids,
                    }
                )
            status_counts[actual.status] += 1

        corrected_types = 0
        processed_by_id = {block.block_id: block for block in result.blocks}
        for confusing in paper["confusing_non_table_elements"]:
            totals["type_corrections_expected"] += 1
            ids = confusing["table_block_ids"]
            if all(
                processed_by_id[block_id].type == confusing["ground_truth_type"]
                for block_id in ids
            ):
                totals["type_corrections"] += 1
                corrected_types += 1
            else:
                mismatches.append(
                    {
                        "paper_id": paper["paper_id"],
                        "element_id": confusing["element_id"],
                        "kind": "type_correction_failed",
                    }
                )

        paper_results.append(
            {
                "paper_id": paper["paper_id"],
                "expected_logical_tables": paper_counts["expected"],
                "actual_logical_tables": paper_counts["actual"],
                "logical_table_recalled": paper_counts["recalled"],
                "source_mapping_exact": paper_counts["source_exact"],
                "caption_mapping_exact": paper_counts["caption_exact"],
                "type_corrections": corrected_types,
                "processor_warnings": result.warnings,
                "tables": [asdict(table) for table in result.tables],
            }
        )

    expected = totals["expected"]
    return {
        "version": "table-postprocessor-evaluation-v1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "ground_truth": str(ground_truth_path.relative_to(PROJECT_ROOT)).replace(
            "\\", "/"
        ),
        "summary": {
            "papers": len(paper_results),
            "expected_logical_tables": expected,
            "logical_table_recall": totals["recalled"] / expected if expected else 0.0,
            "source_mapping_exact_rate": totals["source_exact"] / expected
            if expected
            else 0.0,
            "caption_mapping_exact_rate": totals["caption_exact"] / expected
            if expected
            else 0.0,
            "type_correction_rate": totals["type_corrections"]
            / totals["type_corrections_expected"]
            if totals["type_corrections_expected"]
            else 1.0,
            "status_counts": dict(sorted(status_counts.items())),
            "mismatch_count": len(mismatches),
        },
        "papers": paper_results,
        "mismatches": mismatches,
    }


def write_markdown(path: Path, report: Dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        "# TablePostProcessor 评测（v1）",
        "",
        f"> 生成时间：{report['generated_at']}",
        f"> 人工基准：`{report['ground_truth']}`",
        "",
        "## 评测边界",
        "",
        "本报告评测逻辑表识别、物理 Source block 归并、Caption block 绑定和类型纠正。",
        "它不评测逐单元格文本准确率，也不表示 Docling 已恢复原本损坏的表格网格。",
        "例如 MemLineage Table 4 的 Caption 冲突已被正确归属，但 block_000254 内部的乱码网格仍需局部重解析。",
        "",
        "## 总结",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 论文 | {summary['papers']} |",
        f"| 逻辑表 | {summary['expected_logical_tables']} |",
        f"| 逻辑表召回率 | {summary['logical_table_recall']:.1%} |",
        f"| Source block 精确映射率 | {summary['source_mapping_exact_rate']:.1%} |",
        f"| Caption block 精确映射率 | {summary['caption_mapping_exact_rate']:.1%} |",
        f"| Figure/Table 类型修正率 | {summary['type_correction_rate']:.1%} |",
        f"| 映射不一致 | {summary['mismatch_count']} |",
        "",
        "## 分论文结果",
        "",
        "| 论文 | 预期/实际 | 召回 | Source 精确 | Caption 精确 | 类型修正 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for paper in report["papers"]:
        lines.append(
            f"| {paper['paper_id']} | {paper['expected_logical_tables']}/"
            f"{paper['actual_logical_tables']} | {paper['logical_table_recalled']} | "
            f"{paper['source_mapping_exact']} | {paper['caption_mapping_exact']} | "
            f"{paper['type_corrections']} |"
        )
    lines.extend(["", "## 后处理状态", ""])
    for status, count in summary["status_counts"].items():
        lines.append(f"- `{status}`：{count}")
    lines.extend(["", "## 不一致项", ""])
    if report["mismatches"]:
        for mismatch in report["mismatches"]:
            lines.append(
                f"- `{mismatch['paper_id']}/{mismatch['element_id']}`："
                f"{mismatch['kind']}"
            )
    else:
        lines.append("- 无。")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evaluation" / "table-ground-truth-v1.json",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=PROJECT_ROOT / "output" / "table_postprocessor_v1.json",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evaluation" / "table-postprocessor-v1.md",
    )
    args = parser.parse_args()

    report = evaluate(args.ground_truth.resolve())
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(args.report_output, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"JSON: {args.json_output}")
    print(f"Report: {args.report_output}")
    return 0 if report["summary"]["mismatch_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
