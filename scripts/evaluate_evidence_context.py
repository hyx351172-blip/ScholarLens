"""Evaluate figure/formula context binding on the four parsing fixtures."""

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

from parsers.evidence_context_postprocessor import EvidenceContextPostProcessor  # noqa: E402
from parsers.models import ContentBlock  # noqa: E402
from parsers.section_hierarchy_postprocessor import SectionHierarchyPostProcessor  # noqa: E402
from parsers.table_postprocessor import TablePostProcessor  # noqa: E402


PAPERS = ("charactereval", "gaap", "memlineage", "map_graph")


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def evaluate(input_dir: Path) -> Dict[str, Any]:
    section_processor = SectionHierarchyPostProcessor()
    table_processor = TablePostProcessor()
    evidence_processor = EvidenceContextPostProcessor()
    papers: List[Dict[str, Any]] = []
    totals: Counter[str] = Counter()

    for paper_id in PAPERS:
        document_path = input_dir / paper_id / "document.json"
        document = json.loads(document_path.read_text(encoding="utf-8"))
        blocks = [ContentBlock(**block) for block in document["blocks"]]
        section_result = section_processor.process(blocks)
        table_result = table_processor.process(section_result.blocks)
        result = evidence_processor.process(table_result.blocks)

        figures_with_caption = sum(bool(item.caption_block_ids) for item in result.figures)
        figures_with_explanation = sum(
            bool(item.explanation_block_ids) for item in result.figures
        )
        formulas_with_context = sum(bool(item.context_block_ids) for item in result.formulas)
        numbered_formulas = sum(bool(item.equation_number) for item in result.formulas)
        dangling_relation_ids = _dangling_relation_ids(result.blocks)
        paper = {
            "paper_id": paper_id,
            "figures": len(result.figures),
            "figures_with_caption": figures_with_caption,
            "figures_with_explicit_explanation": figures_with_explanation,
            "formulas": len(result.formulas),
            "formulas_with_context": formulas_with_context,
            "numbered_formulas": numbered_formulas,
            "dangling_relation_ids": dangling_relation_ids,
            "warnings": result.warnings,
        }
        papers.append(paper)
        for key in (
            "figures",
            "figures_with_caption",
            "figures_with_explicit_explanation",
            "formulas",
            "formulas_with_context",
            "numbered_formulas",
        ):
            totals[key] += paper[key]
        totals["dangling_relation_ids"] += len(dangling_relation_ids)

    summary = dict(totals)
    summary["figure_caption_coverage"] = _rate(
        totals["figures_with_caption"], totals["figures"]
    )
    summary["figure_explanation_coverage"] = _rate(
        totals["figures_with_explicit_explanation"], totals["figures"]
    )
    summary["formula_context_coverage"] = _rate(
        totals["formulas_with_context"], totals["formulas"]
    )
    summary["equation_number_coverage"] = _rate(
        totals["numbered_formulas"], totals["formulas"]
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "evaluation_scope": "relationship coverage on existing parser artifacts",
        "summary": summary,
        "papers": papers,
        "limitations": [
            "This is structural coverage, not human-labelled semantic accuracy.",
            "Existing document.json files predate formula orig fallback; equation-number coverage must be rechecked after fresh parsing.",
        ],
    }


def _dangling_relation_ids(blocks: List[ContentBlock]) -> List[str]:
    known = {block.block_id for block in blocks}
    relation_keys = {
        "caption_block_ids",
        "explanation_block_ids",
        "context_block_ids",
        "describes_block_ids",
    }
    dangling = set()
    for block in blocks:
        for key in relation_keys:
            for block_id in block.relations.get(key, []):
                if block_id not in known:
                    dangling.add(block_id)
    return sorted(dangling)


def write_markdown(path: Path, report: Dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        "# Figure / Formula Context Binding Evaluation v1",
        "",
        f"生成时间：{report['generated_at']}",
        "",
        "## 汇总",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| Figure Caption 覆盖 | {summary['figures_with_caption']}/{summary['figures']} ({summary['figure_caption_coverage']:.1%}) |",
        f"| Figure 显式解释段覆盖 | {summary['figures_with_explicit_explanation']}/{summary['figures']} ({summary['figure_explanation_coverage']:.1%}) |",
        f"| Formula 上下文覆盖 | {summary['formulas_with_context']}/{summary['formulas']} ({summary['formula_context_coverage']:.1%}) |",
        f"| 公式编号覆盖 | {summary['numbered_formulas']}/{summary['formulas']} ({summary['equation_number_coverage']:.1%}) |",
        f"| 悬空 Block 关系 | {summary['dangling_relation_ids']} |",
        "",
        "## 分论文结果",
        "",
        "| 论文 | Figure Caption | Figure 解释段 | Formula 上下文 | 公式编号 | 悬空关系 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for paper in report["papers"]:
        lines.append(
            f"| {paper['paper_id']} | {paper['figures_with_caption']}/{paper['figures']} | "
            f"{paper['figures_with_explicit_explanation']}/{paper['figures']} | "
            f"{paper['formulas_with_context']}/{paper['formulas']} | "
            f"{paper['numbered_formulas']}/{paper['formulas']} | "
            f"{len(paper['dangling_relation_ids'])} |"
        )
    lines.extend(
        [
            "",
            "## 口径与限制",
            "",
            "- Caption 绑定采用同页、最近距离和显式 Figure 编号约束。",
            "- Figure 解释段只统计显式提及 Figure/Fig 编号的正文，避免把普通相邻段误标为解释。",
            "- Formula 上下文采用同章节内前后最近正文，并在标题或另一公式处停止。",
            "- 本报告衡量结构关系覆盖率，不等同于人工标注后的语义准确率。",
            "- 旧评测产物生成于公式 `orig` 回退实现之前，公式编号需在重新解析四篇论文后复测。",
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
        default=PROJECT_ROOT / "output" / "evidence_context_v1.json",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evaluation" / "evidence-context-v1.md",
    )
    args = parser.parse_args()
    report = evaluate(args.input_dir)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(args.report_output, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"JSON: {args.json_output}")
    print(f"Report: {args.report_output}")
    return 0 if report["summary"]["dangling_relation_ids"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
