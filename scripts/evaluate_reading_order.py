"""Evaluate deterministic Reading Order invariants on parser artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"
sys.path.insert(0, str(UNIFIED_DIR))

from parsers.models import ContentBlock  # noqa: E402
from parsers.reading_order_postprocessor import ReadingOrderPostProcessor  # noqa: E402


PAPERS = ("charactereval", "gaap", "memlineage", "map_graph")


def evaluate(input_dir: Path) -> Dict[str, Any]:
    processor = ReadingOrderPostProcessor()
    papers: List[Dict[str, Any]] = []
    totals = Counter()

    for paper_id in PAPERS:
        document = json.loads(
            (input_dir / paper_id / "document.json").read_text(encoding="utf-8")
        )
        source = [ContentBlock(**block) for block in document["blocks"]]
        result = processor.process(source)
        repeated = processor.process(result.blocks)
        source_ids = [block.block_id for block in source]
        result_ids = [block.block_id for block in result.blocks]
        identity_preserved = set(source_ids) == set(result_ids) and len(source_ids) == len(
            result_ids
        )
        page_membership_preserved = all(
            source_block.page == result_block.page
            for source_block, result_block in zip(
                sorted(source, key=lambda block: block.block_id),
                sorted(result.blocks, key=lambda block: block.block_id),
            )
        )
        idempotent = result.blocks == repeated.blocks
        methods = Counter(result.page_methods.values())
        paper = {
            "paper_id": paper_id,
            "blocks": len(source),
            "pages": len(result.page_methods),
            "pages_reordered": result.pages_reordered,
            "page_methods": dict(sorted(methods.items())),
            "fallback_pages": methods["original_order_fallback"],
            "identity_preserved": identity_preserved,
            "page_membership_preserved": page_membership_preserved,
            "idempotent": idempotent,
            "warnings": result.warnings,
        }
        papers.append(paper)
        totals["blocks"] += len(source)
        totals["pages"] += len(result.page_methods)
        totals["pages_reordered"] += result.pages_reordered
        totals["two_column_pages"] += methods["two_column_geometry"]
        totals["single_column_pages"] += methods["single_column_geometry"]
        totals["fallback_pages"] += methods["original_order_fallback"]
        totals["identity_failures"] += not identity_preserved
        totals["page_membership_failures"] += not page_membership_preserved
        totals["idempotence_failures"] += not idempotent

    return {
        "version": "reading-order-evaluation-v1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": (
            "structural invariants and deterministic geometry coverage; no human "
            "page-order ground truth, so this does not claim semantic accuracy"
        ),
        "summary": dict(totals),
        "papers": papers,
    }


def write_markdown(path: Path, report: Dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        "# ReadingOrderPostProcessor 评测（v1）",
        "",
        f"> 生成时间：{report['generated_at']}",
        "",
        "## 评测边界",
        "",
        "本报告验证 block/page 不丢失、幂等性、几何策略覆盖和回退情况。",
        "尚未建立逐页人工 Reading Order ground truth，因此不宣称语义顺序准确率为 100%。",
        "",
        "## 汇总",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 论文 | {len(report['papers'])} |",
        f"| Blocks | {summary['blocks']} |",
        f"| Pages | {summary['pages']} |",
        f"| 双栏页 | {summary['two_column_pages']} |",
        f"| 单栏页 | {summary['single_column_pages']} |",
        f"| 实际重排页 | {summary['pages_reordered']} |",
        f"| 原顺序回退页 | {summary['fallback_pages']} |",
        f"| Block 身份保持失败 | {summary['identity_failures']} |",
        f"| Page 归属保持失败 | {summary['page_membership_failures']} |",
        f"| 幂等性失败 | {summary['idempotence_failures']} |",
        "",
        "## 分论文结果",
        "",
        "| 论文 | Blocks | Pages | 重排页 | 双栏 | 单栏 | 回退 | 幂等 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for paper in report["papers"]:
        methods = paper["page_methods"]
        lines.append(
            f"| {paper['paper_id']} | {paper['blocks']} | {paper['pages']} | "
            f"{paper['pages_reordered']} | {methods.get('two_column_geometry', 0)} | "
            f"{methods.get('single_column_geometry', 0)} | {paper['fallback_pages']} | "
            f"{'是' if paper['idempotent'] else '否'} |"
        )
    lines.extend(
        [
            "",
            "## 后续人工评测",
            "",
            "- 从四篇论文各选取至少 2 个复杂页面，人工标注 `expected_block_ids`。",
            "- 在此基础上计算相邻 block pair accuracy 和 page exact-order accuracy。",
            "- 当前结果只能证明排序稳定且不损坏结构，不能替代人工顺序准确率。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=PROJECT_ROOT / "output" / "docling_evaluation_v1",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=PROJECT_ROOT / "output" / "reading_order_v1.json",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evaluation" / "reading-order-v1.md",
    )
    args = parser.parse_args()
    report = evaluate(args.input_dir)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(args.report_output, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    failures = sum(
        report["summary"][key]
        for key in (
            "identity_failures",
            "page_membership_failures",
            "idempotence_failures",
        )
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
