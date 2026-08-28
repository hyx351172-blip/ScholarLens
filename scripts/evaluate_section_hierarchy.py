"""Evaluate section hierarchy reconstruction on the four parsing fixtures."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"
sys.path.insert(0, str(UNIFIED_DIR))

from parsers.models import ContentBlock  # noqa: E402
from parsers.section_hierarchy_postprocessor import (  # noqa: E402
    SectionHierarchyPostProcessor,
)


PAPERS = ("charactereval", "gaap", "memlineage", "map_graph")
NUMBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+")
APPENDIX_RE = re.compile(r"^\s*(?:Appendix\s+)?([A-Z](?:\.\d+)*)[.):]?\s+")


def evaluate(input_dir: Path) -> Dict[str, Any]:
    processor = SectionHierarchyPostProcessor()
    papers: List[Dict[str, Any]] = []
    totals = Counter()

    for paper_id in PAPERS:
        document_path = input_dir / paper_id / "document.json"
        document = json.loads(document_path.read_text(encoding="utf-8"))
        source_blocks = [ContentBlock(**block) for block in document["blocks"]]
        result = processor.process(source_blocks)
        sections_by_number = {}
        numbered_sections = []
        for section in result.sections:
            match = NUMBER_RE.match(section.title)
            if match:
                number = match.group(1)
                sections_by_number[number] = section
                numbered_sections.append((number, section))

        subsection_count = 0
        correct_parent_count = 0
        parent_mismatches = []
        for number, section in numbered_sections:
            if "." not in number:
                continue
            subsection_count += 1
            parent_number = number.rsplit(".", 1)[0]
            parent = sections_by_number.get(parent_number)
            if parent and section.parent_id == parent.section_id:
                correct_parent_count += 1
            else:
                parent_mismatches.append(
                    {
                        "section": section.title,
                        "expected_parent_number": parent_number,
                        "actual_parent_id": section.parent_id,
                    }
                )

        eligible_blocks = 0
        covered_blocks = 0
        section_seen = False
        for block in result.blocks:
            if block.type == "title":
                continue
            if block.type == "heading" and block.relations.get(
                "generated_section_ids"
            ):
                section_seen = True
            if section_seen:
                eligible_blocks += 1
                if block.section_path:
                    covered_blocks += 1

        statuses = Counter(
            block.relations.get("section_postprocess_status")
            for block in result.blocks
            if block.type in {"heading", "title"}
        )
        level_counts = Counter(section.level for section in result.sections)
        title_count = sum(block.type == "title" for block in result.blocks)
        abstract_sections = [section for section in result.sections if section.kind == "abstract"]
        appendix_sections = [section for section in result.sections if section.kind == "appendix"]
        special_body_blocks = [
            block
            for block in result.blocks
            if block.type not in {"heading", "title"}
            and block.relations.get("section_kind") in {"abstract", "appendix"}
        ]
        special_body_bound = sum(
            bool(block.relations.get("containing_section_id"))
            for block in special_body_blocks
        )
        appendix_by_number = {}
        for section in appendix_sections:
            match = APPENDIX_RE.match(section.title)
            if match:
                appendix_by_number[match.group(1)] = section
        appendix_parent_mismatches = []
        for number, section in appendix_by_number.items():
            if "." not in number:
                continue
            parent = appendix_by_number.get(number.rsplit(".", 1)[0])
            if not parent or section.parent_id != parent.section_id:
                appendix_parent_mismatches.append(section.title)
        paper_result = {
            "paper_id": paper_id,
            "source_blocks": len(source_blocks),
            "output_blocks": len(result.blocks),
            "title_count": title_count,
            "sections": len(result.sections),
            "level_counts": dict(sorted(level_counts.items())),
            "parent_links": sum(
                section.parent_id is not None for section in result.sections
            ),
            "numbered_subsections": subsection_count,
            "correct_numbered_parents": correct_parent_count,
            "section_path_eligible_blocks": eligible_blocks,
            "section_path_covered_blocks": covered_blocks,
            "merged_heading_repairs": statuses["split_merged_heading"],
            "fallback_headings": statuses["hierarchy_fallback"],
            "warnings": result.warnings,
            "parent_mismatches": parent_mismatches,
            "abstract_sections": len(abstract_sections),
            "appendix_sections": len(appendix_sections),
            "special_body_blocks": len(special_body_blocks),
            "special_body_bound": special_body_bound,
            "appendix_parent_mismatches": appendix_parent_mismatches,
        }
        papers.append(paper_result)
        totals["papers"] += 1
        totals["titles"] += title_count
        totals["numbered_subsections"] += subsection_count
        totals["correct_numbered_parents"] += correct_parent_count
        totals["path_eligible"] += eligible_blocks
        totals["path_covered"] += covered_blocks
        totals["merged_repairs"] += statuses["split_merged_heading"]
        totals["fallback_headings"] += statuses["hierarchy_fallback"]
        totals["parent_mismatches"] += len(parent_mismatches)
        totals["abstract_sections"] += len(abstract_sections)
        totals["appendix_sections"] += len(appendix_sections)
        totals["special_body_blocks"] += len(special_body_blocks)
        totals["special_body_bound"] += special_body_bound
        totals["appendix_parent_mismatches"] += len(appendix_parent_mismatches)

    return {
        "version": "section-hierarchy-evaluation-v1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": (
            "structural consistency against heading numbering; unnumbered "
            "headings are not human-ground-truth accuracy"
        ),
        "summary": {
            "papers": totals["papers"],
            "papers_with_one_title": sum(
                paper["title_count"] == 1 for paper in papers
            ),
            "numbered_subsections": totals["numbered_subsections"],
            "numbered_parent_consistency": (
                totals["correct_numbered_parents"]
                / totals["numbered_subsections"]
                if totals["numbered_subsections"]
                else 1.0
            ),
            "section_path_coverage": (
                totals["path_covered"] / totals["path_eligible"]
                if totals["path_eligible"]
                else 1.0
            ),
            "merged_heading_repairs": totals["merged_repairs"],
            "fallback_headings_needing_review": totals["fallback_headings"],
            "parent_mismatch_count": totals["parent_mismatches"],
            "abstract_sections": totals["abstract_sections"],
            "appendix_sections": totals["appendix_sections"],
            "special_body_binding_coverage": (
                totals["special_body_bound"] / totals["special_body_blocks"]
                if totals["special_body_blocks"]
                else 1.0
            ),
            "appendix_parent_mismatch_count": totals["appendix_parent_mismatches"],
        },
        "papers": papers,
    }


def write_markdown(path: Path, report: Dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        "# SectionHierarchyPostProcessor 评测（v1）",
        "",
        f"> 生成时间：{report['generated_at']}",
        "",
        "## 评测边界",
        "",
        "本报告验证编号章节的结构一致性、合并标题修复和 section_path 覆盖率。",
        "无编号标题使用上下文回退，尚未建立人工层级 ground truth，因此不宣称其准确率为 100%。",
        "",
        "## 总结",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 单一论文标题 | {summary['papers_with_one_title']}/{summary['papers']} |",
        f"| 编号子章节 | {summary['numbered_subsections']} |",
        f"| 编号父节点一致率 | {summary['numbered_parent_consistency']:.1%} |",
        f"| Section path 覆盖率 | {summary['section_path_coverage']:.1%} |",
        f"| 合并标题修复 | {summary['merged_heading_repairs']} |",
        f"| 待人工复核无编号标题 | {summary['fallback_headings_needing_review']} |",
        f"| 编号父节点不一致 | {summary['parent_mismatch_count']} |",
        f"| Abstract 章节 | {summary['abstract_sections']} |",
        f"| Appendix 章节 | {summary['appendix_sections']} |",
        f"| 特殊章节正文绑定率 | {summary['special_body_binding_coverage']:.1%} |",
        f"| Appendix 字母层级不一致 | {summary['appendix_parent_mismatch_count']} |",
        "",
        "## 分论文结果",
        "",
        "| 论文 | 标题 | Sections | Level 分布 | 编号父节点 | Path 覆盖 | 合并修复 | 回退标题 |",
        "|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for paper in report["papers"]:
        levels = ", ".join(
            f"L{level}:{count}" for level, count in paper["level_counts"].items()
        )
        parent = (
            f"{paper['correct_numbered_parents']}/"
            f"{paper['numbered_subsections']}"
        )
        coverage = (
            paper["section_path_covered_blocks"]
            / paper["section_path_eligible_blocks"]
            if paper["section_path_eligible_blocks"]
            else 1.0
        )
        lines.append(
            f"| {paper['paper_id']} | {paper['title_count']} | "
            f"{paper['sections']} | {levels} | {parent} | {coverage:.1%} | "
            f"{paper['merged_heading_repairs']} | {paper['fallback_headings']} |"
        )
    lines.extend(["", "## 待人工复核", ""])
    fallback_rows = [
        (paper["paper_id"], warning)
        for paper in report["papers"]
        for warning in paper["warnings"]
        if "unnumbered heading" in warning
    ]
    if fallback_rows:
        for paper_id, warning in fallback_rows:
            lines.append(f"- `{paper_id}`：{warning}")
    else:
        lines.append("- 无。")
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
        default=PROJECT_ROOT / "output" / "section_hierarchy_v1.json",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evaluation" / "section-hierarchy-v1.md",
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
    return 0 if (
        report["summary"]["parent_mismatch_count"] == 0
        and report["summary"]["appendix_parent_mismatch_count"] == 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
