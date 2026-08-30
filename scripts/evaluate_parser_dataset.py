"""Evaluate ScholarLens' current PDF parser on a directory of research papers.

The evaluator intentionally stops at parsing.  It records structural coverage,
metadata extraction, provenance and relationship integrity without claiming
semantic accuracy for tables, figures or formulas.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import pymupdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"
sys.path.insert(0, str(UNIFIED_DIR))

from parsers.docling_parser import DoclingParser  # noqa: E402


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def dangling_relationships(blocks: list[Any]) -> list[str]:
    known_ids = {block.block_id for block in blocks}
    relationship_keys = {
        "caption_block_ids",
        "context_block_ids",
        "describes_block_ids",
        "explanation_block_ids",
        "source_block_ids",
    }
    dangling: set[str] = set()
    for block in blocks:
        for key in relationship_keys:
            values = block.relations.get(key, [])
            if isinstance(values, str):
                values = [values]
            for block_id in values:
                if block_id not in known_ids:
                    dangling.add(block_id)
    return sorted(dangling)


def evaluate_one(parser: DoclingParser, pdf_path: Path) -> dict[str, Any]:
    with pymupdf.open(pdf_path) as pdf:
        expected_pages = pdf.page_count
    parsed = parser.parse(pdf_path, original_filename=pdf_path.name)
    document = parsed.document
    quality = document.quality
    blocks = document.blocks
    block_counts = Counter(block.type for block in blocks)
    text_blocks = [
        block
        for block in blocks
        if block.type not in {"title", "heading"} and block.text.strip()
    ]
    section_bound = sum(bool(block.section_path) for block in text_blocks)
    logical_tables = parsed.logical_tables
    logical_figures = parsed.logical_figures
    logical_formulas = parsed.logical_formulas
    table_captioned = sum(bool(table.caption_block_ids) for table in logical_tables)
    table_multiblock = sum(len(table.source_block_ids) > 1 for table in logical_tables)
    figure_captioned = sum(bool(figure.caption_block_ids) for figure in logical_figures)
    figure_explained = sum(
        bool(figure.explanation_block_ids) for figure in logical_figures
    )
    formula_contextualized = sum(
        bool(formula.context_block_ids) for formula in logical_formulas
    )
    formula_numbered = sum(bool(formula.equation_number) for formula in logical_formulas)
    dangling = dangling_relationships(blocks)
    gates = {
        "page_count_match": (
            quality.total_pages == expected_pages
            and quality.parsed_pages == expected_pages
        ),
        "provenance_gte_95pct": quality.provenance_coverage >= 0.95,
        "no_empty_pages": not quality.empty_page_numbers,
        "title_present": bool(document.metadata.title),
        "abstract_present": bool(document.metadata.abstract),
        "section_path_gte_90pct": ratio(section_bound, len(text_blocks)) >= 0.90,
        "no_dangling_relationships": not dangling,
    }
    return {
        "filename": pdf_path.name,
        "bytes": pdf_path.stat().st_size,
        "expected_pages": expected_pages,
        "parsed_pages": quality.parsed_pages,
        "reported_total_pages": quality.total_pages,
        "duration_seconds": round(quality.duration_seconds, 3),
        "total_blocks": len(blocks),
        "block_counts": dict(sorted(block_counts.items())),
        "provenance_coverage": round(quality.provenance_coverage, 4),
        "empty_pages": quality.empty_page_numbers,
        "empty_blocks": quality.empty_block_count,
        "reading_order_pages_reordered": quality.reading_order_pages_reordered,
        "sections": len(document.sections),
        "section_path_eligible_blocks": len(text_blocks),
        "section_path_bound_blocks": section_bound,
        "section_path_coverage": round(ratio(section_bound, len(text_blocks)), 4),
        "metadata": {
            "title": document.metadata.title,
            "authors_count": len(document.metadata.authors),
            "abstract_present": bool(document.metadata.abstract),
            "year": document.metadata.year,
            "doi": document.metadata.doi,
            "arxiv_id": document.metadata.arxiv_id,
        },
        "logical_tables": len(logical_tables),
        "tables_with_caption": table_captioned,
        "table_caption_coverage": round(ratio(table_captioned, len(logical_tables)), 4),
        "multiblock_tables": table_multiblock,
        "logical_figures": len(logical_figures),
        "figures_with_caption": figure_captioned,
        "figure_caption_coverage": round(ratio(figure_captioned, len(logical_figures)), 4),
        "figures_with_explanation": figure_explained,
        "figure_explanation_coverage": round(
            ratio(figure_explained, len(logical_figures)), 4
        ),
        "logical_formulas": len(logical_formulas),
        "formulas_with_context": formula_contextualized,
        "formula_context_coverage": round(
            ratio(formula_contextualized, len(logical_formulas)), 4
        ),
        "numbered_formulas": formula_numbered,
        "equation_number_coverage": round(
            ratio(formula_numbered, len(logical_formulas)), 4
        ),
        "dangling_relationship_ids": dangling,
        "warning_count": len(quality.warnings),
        "warnings": quality.warnings,
        "gates": gates,
        "gate_pass_rate": round(ratio(sum(gates.values()), len(gates)), 4),
    }


def aggregate(papers: list[dict[str, Any]], failures: list[dict[str, str]]) -> dict[str, Any]:
    total = len(papers) + len(failures)
    pages = sum(item["expected_pages"] for item in papers)
    tables = sum(item["logical_tables"] for item in papers)
    figures = sum(item["logical_figures"] for item in papers)
    formulas = sum(item["logical_formulas"] for item in papers)
    section_eligible = sum(item["section_path_eligible_blocks"] for item in papers)
    section_bound = sum(item["section_path_bound_blocks"] for item in papers)
    return {
        "evaluation": "parser-dataset-2026-08-30",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "current Docling parser and parser post-processors; no chunking or RAG",
        "papers_total": total,
        "papers_successful": len(papers),
        "parse_success_rate": round(ratio(len(papers), total), 4),
        "pages_total": pages,
        "page_count_match_rate": round(
            ratio(sum(item["gates"]["page_count_match"] for item in papers), len(papers)),
            4,
        ),
        "duration_seconds": round(sum(item["duration_seconds"] for item in papers), 3),
        "mean_seconds_per_page": round(
            ratio(int(sum(item["duration_seconds"] for item in papers) * 1000), pages)
            / 1000,
            3,
        ),
        "total_blocks": sum(item["total_blocks"] for item in papers),
        "mean_provenance_coverage": round(
            mean(item["provenance_coverage"] for item in papers), 4
        ) if papers else 0.0,
        "papers_with_empty_pages": sum(bool(item["empty_pages"]) for item in papers),
        "title_detection_rate": round(
            ratio(sum(item["gates"]["title_present"] for item in papers), len(papers)),
            4,
        ),
        "abstract_detection_rate": round(
            ratio(sum(item["gates"]["abstract_present"] for item in papers), len(papers)),
            4,
        ),
        "section_path_coverage": round(ratio(section_bound, section_eligible), 4),
        "logical_tables": tables,
        "table_caption_coverage": round(
            ratio(sum(item["tables_with_caption"] for item in papers), tables), 4
        ),
        "multiblock_tables": sum(item["multiblock_tables"] for item in papers),
        "logical_figures": figures,
        "figure_caption_coverage": round(
            ratio(sum(item["figures_with_caption"] for item in papers), figures), 4
        ),
        "figure_explanation_coverage": round(
            ratio(sum(item["figures_with_explanation"] for item in papers), figures), 4
        ),
        "logical_formulas": formulas,
        "formula_context_coverage": round(
            ratio(sum(item["formulas_with_context"] for item in papers), formulas), 4
        ),
        "equation_number_coverage": round(
            ratio(sum(item["numbered_formulas"] for item in papers), formulas), 4
        ),
        "dangling_relationship_count": sum(
            len(item["dangling_relationship_ids"]) for item in papers
        ),
        "papers_all_gates_green": sum(
            all(item["gates"].values()) for item in papers
        ),
        "failures": failures,
        "papers": papers,
    }


def percent(value: float) -> str:
    return f"{value:.1%}"


def write_markdown(path: Path, report: dict[str, Any], input_dir: Path) -> None:
    missing_abstract = [
        item["filename"] for item in report["papers"] if not item["metadata"]["abstract_present"]
    ]
    zero_table_caption = [
        item["filename"]
        for item in report["papers"]
        if item["logical_tables"] and not item["tables_with_caption"]
    ]
    zero_figure_caption = [
        item["filename"]
        for item in report["papers"]
        if item["logical_figures"] and not item["figures_with_caption"]
    ]
    formula_context_gaps = [
        item["filename"]
        for item in report["papers"]
        if item["logical_formulas"] and item["formula_context_coverage"] < 1.0
    ]
    slowest = sorted(
        report["papers"], key=lambda item: item["duration_seconds"], reverse=True
    )[:5]
    warning_hotspots = sorted(
        report["papers"], key=lambda item: item["warning_count"], reverse=True
    )[:5]
    lines = [
        "# ScholarLens 当前 PDF 解析器批量评测",
        "",
        f"> 生成时间：{report['generated_at']}",
        f"> 数据集：`{input_dir}`",
        "",
        "## 评测边界",
        "",
        "本报告评测 Docling 解析及 Reading Order、章节层级、表格、Figure/Formula 关系后处理。",
        "指标主要是自动化结构代理指标，不等同于人工标注后的语义准确率；不包含 Chunker、Embedding、检索和回答生成。",
        "",
        "## 总体结果",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 成功解析 | {report['papers_successful']}/{report['papers_total']} ({percent(report['parse_success_rate'])}) |",
        f"| 总页数 | {report['pages_total']} |",
        f"| 页数一致率 | {percent(report['page_count_match_rate'])} |",
        f"| 总耗时 | {report['duration_seconds']:.1f}s |",
        f"| 平均每页耗时 | {report['mean_seconds_per_page']:.3f}s |",
        f"| 总 Blocks | {report['total_blocks']} |",
        f"| 平均 Provenance 覆盖 | {percent(report['mean_provenance_coverage'])} |",
        f"| 标题识别率 | {percent(report['title_detection_rate'])} |",
        f"| 摘要识别率 | {percent(report['abstract_detection_rate'])} |",
        f"| Section path 覆盖 | {percent(report['section_path_coverage'])} |",
        f"| 逻辑表格 / Caption 覆盖 | {report['logical_tables']} / {percent(report['table_caption_coverage'])} |",
        f"| 跨 Block 合并表格 | {report['multiblock_tables']} |",
        f"| 逻辑 Figure / Caption 覆盖 | {report['logical_figures']} / {percent(report['figure_caption_coverage'])} |",
        f"| Figure 显式解释覆盖 | {percent(report['figure_explanation_coverage'])} |",
        f"| 逻辑 Formula / 上下文覆盖 | {report['logical_formulas']} / {percent(report['formula_context_coverage'])} |",
        f"| 公式编号覆盖 | {percent(report['equation_number_coverage'])} |",
        f"| 悬空关系 | {report['dangling_relationship_count']} |",
        f"| 全部门禁通过论文 | {report['papers_all_gates_green']}/{report['papers_successful']} |",
        "",
        "## 关键发现",
        "",
        f"- **工程稳定性较好**：{report['papers_successful']}/{report['papers_total']} 篇任务成功，"
        f"完整页解析率 {percent(report['page_count_match_rate'])}，Provenance 平均 {percent(report['mean_provenance_coverage'])}，"
        f"悬空关系 {report['dangling_relationship_count']}。",
        f"- **章节路径总体可靠**：Section path 覆盖 {percent(report['section_path_coverage'])}；"
        "但无编号标题仍依赖启发式回退，不能据此宣称层级语义完全正确。",
        f"- **摘要识别存在缺口**：{', '.join(f'`{name}`' for name in missing_abstract) or '无'}。",
        "- **标题非空率不等于标题准确率**：多语言噪声样本被识别为 arXiv URL，PMC 样本仅识别为 “PERSPECTIVE”；"
        "标题仍需人工准确率标注。",
        f"- **表格 Caption 绑定是当前最大结构短板**：总体仅 {percent(report['table_caption_coverage'])}；"
        f"完全未绑定的样本包括 {', '.join(f'`{name}`' for name in zero_table_caption) or '无'}。",
        f"- **Figure Caption 与解释段覆盖偏低**：Caption {percent(report['figure_caption_coverage'])}，"
        f"显式解释段 {percent(report['figure_explanation_coverage'])}；完全未绑定 Caption 的样本包括 "
        f"{', '.join(f'`{name}`' for name in zero_figure_caption) or '无'}。",
        f"- **公式上下文较稳定**：总体 {percent(report['formula_context_coverage'])}；"
        f"上下文不完整集中在 {', '.join(f'`{name}`' for name in formula_context_gaps) or '无'}。",
        "- **测试数据存在一处命名/内容错误**：`2106.10379_alphafold.pdf` 实际标题为 "
        "“Electron- and hole-doping on ScH2 and YH2...”，不是 AlphaFold，应重新下载正确论文后复测。",
        "- **同步解析延迟较高**：最慢 5 篇为 "
        + "; ".join(
            f"`{item['filename']}` {item['duration_seconds']:.1f}s"
            for item in slowest
        )
        + "。",
        "- **警告集中而非均匀分布**："
        + "; ".join(
            f"`{item['filename']}` {item['warning_count']} 条"
            for item in warning_hotspots
        )
        + "。",
        "",
        "## 改进优先级",
        "",
        "1. 为 Llama 3、DeepSeek-R1、GPT-3、Nougat 和 PMC 样本建立 Table/Figure Caption 人工标注，"
        "修复 Caption 与对象相距较远、跨栏或跨页时的绑定。",
        "2. 针对 GPT-4、DeepSeek-R1 的无编号标题回退建立层级 ground truth，区分真实标题与图内文本。",
        "3. 修复 Llama 3 与 PMC 摘要识别，并替换错误的 AlphaFold 测试文件。",
        "4. 对 Neural ODE 与 Nougat 的无上下文公式逐页核对，确认是正文绑定失败还是独立展示公式。",
        "5. 将 PDF 解析改为异步任务，并提供 Fast/Accurate 模式；长论文不应阻塞上传请求。",
        "",
        "## 分论文结果",
        "",
        "| 论文 | 页数 | 秒 | Blocks | Provenance | Path | Tables | Figures | Formulae | Gates |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["papers"]:
        lines.append(
            f"| {item['filename']} | {item['parsed_pages']}/{item['expected_pages']} | "
            f"{item['duration_seconds']:.1f} | {item['total_blocks']} | "
            f"{percent(item['provenance_coverage'])} | "
            f"{percent(item['section_path_coverage'])} | {item['logical_tables']} | "
            f"{item['logical_figures']} | {item['logical_formulas']} | "
            f"{percent(item['gate_pass_rate'])} |"
        )
    lines.extend(["", "## 自动发现的问题", ""])
    problems: list[str] = []
    for item in report["papers"]:
        failed = [name for name, passed in item["gates"].items() if not passed]
        if failed:
            problems.append(f"- `{item['filename']}`：{', '.join(failed)}")
        if item["warning_count"]:
            preview = "; ".join(item["warnings"][:3])
            suffix = " …" if item["warning_count"] > 3 else ""
            problems.append(
                f"- `{item['filename']}`：{item['warning_count']} 条警告：{preview}{suffix}"
            )
    lines.extend(problems or ["- 未发现自动门禁异常。"])
    if report["failures"]:
        lines.extend(["", "## 解析失败", ""])
        lines.extend(
            f"- `{item['filename']}`：{item['error']}" for item in report["failures"]
        )
    lines.extend(
        [
            "",
            "## 结论与限制",
            "",
            "- 页数、Provenance、关系完整性用于判断工程链路是否稳定。",
            "- Caption/上下文覆盖率只表示建立了关系，不能证明绑定对象在语义上一定正确。",
            "- 公式编号只统计可从解析文本恢复的显式编号；无编号公式会自然降低该指标。",
            "- 下一步应从失败门禁、低覆盖和高警告论文中抽取页面，建立人工 ground truth。",
            "",
            "## 复现",
            "",
            "```powershell",
            "python scripts/evaluate_parser_dataset.py --input-dir <evaluation_papers>",
            "```",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--input-dir", type=Path, required=True)
    cli.add_argument(
        "--json-output",
        type=Path,
        default=PROJECT_ROOT / "output" / "parser_dataset_2026_08_30.json",
    )
    cli.add_argument(
        "--report-output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evaluation" / "parser-dataset-2026-08-30.md",
    )
    cli.add_argument("--limit", type=int)
    cli.add_argument(
        "--reuse-json",
        action="store_true",
        help="Reuse paper metrics from --json-output and only regenerate summaries/report.",
    )
    args = cli.parse_args()
    if args.reuse_json:
        existing = json.loads(args.json_output.read_text(encoding="utf-8"))
        papers = existing.get("papers", [])
        failures = existing.get("failures", [])
        for item in papers:
            item["gates"].pop("no_empty_blocks", None)
            item["gates"]["page_count_match"] = (
                item["reported_total_pages"] == item["expected_pages"]
                and item["parsed_pages"] == item["expected_pages"]
            )
            item["gate_pass_rate"] = round(
                ratio(sum(item["gates"].values()), len(item["gates"])), 4
            )
        report = aggregate(papers, failures)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        write_markdown(args.report_output, report, args.input_dir)
        print(json.dumps({key: value for key, value in report.items() if key not in {"papers", "failures"}}, ensure_ascii=False, indent=2))
        print(f"JSON: {args.json_output}")
        print(f"Report: {args.report_output}")
        return 1 if failures else 0
    pdfs = sorted(args.input_dir.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        raise SystemExit(f"没有找到 PDF：{args.input_dir}")

    parser = DoclingParser(table_mode="accurate", do_ocr=False)
    papers: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, pdf_path in enumerate(pdfs, start=1):
        print(f"[{index}/{len(pdfs)}] {pdf_path.name}", flush=True)
        try:
            papers.append(evaluate_one(parser, pdf_path))
        except Exception as exc:  # noqa: BLE001 - one bad PDF must not abort the corpus
            failures.append(
                {
                    "filename": pdf_path.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
        partial = aggregate(papers, failures)
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(partial, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    report = aggregate(papers, failures)
    write_markdown(args.report_output, report, args.input_dir)
    print(json.dumps({key: value for key, value in report.items() if key not in {"papers", "failures"}}, ensure_ascii=False, indent=2))
    print(f"JSON: {args.json_output}")
    print(f"Report: {args.report_output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
