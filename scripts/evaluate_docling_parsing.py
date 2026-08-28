"""Run ScholarLens' parsing-only Docling evaluation on the fixed four-paper set."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pymupdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"
sys.path.insert(0, str(UNIFIED_DIR))

from parsers.docling_parser import (  # noqa: E402
    DoclingParser,
    _extract_metadata,
    save_parse_result,
)
from parsers.models import ContentBlock  # noqa: E402


PAPER_SPECS = [
    ("CharacterEval", "file_20260827_c11e9075_2024.acl-long.638.pdf"),
    ("GAAP", "file_20260827_a3b1a024_2604.19657v1.pdf"),
    ("MemLineage", "file_20260827_9e0dae27_2605.14421v1.pdf"),
    ("MAP-Graph", "file_20260827_d6b086f1_2608.10509v1.pdf"),
]

EXPECTED_AUTHORS = {
    "CharacterEval": [
        "Quan Tu", "Shilong Fan", "Zihang Tian", "Tianhao Shen",
        "Shuo Shang", "Xin Gao", "Rui Yan",
    ],
    "GAAP": [
        "Robert Stanley", "Avi Verma", "Konstantinos Kallas", "Sam Kumar",
        "Lillian Tsai",
    ],
    "MemLineage": ["Ciyan Ouyang", "Rui Hou"],
    "MAP-Graph": [
        "Yiqi Wang", "Zihao Yan", "Jiaqi Zhang", "Zhangkai Wu",
        "Mingkai Zheng", "Zequn Sun", "Yanming Zhu", "Taotao Cai",
    ],
}


def evaluate_paper(
    parser: DoclingParser,
    label: str,
    pdf_path: Path,
    output_root: Path,
) -> Dict[str, Any]:
    expected_pages = _pdf_page_count(pdf_path)
    paper_dir = output_root / label.lower().replace("-", "_")
    result = parser.parse(
        pdf_path,
        file_id=pdf_path.stem.split("_")[0] + "_" + pdf_path.stem.split("_")[2],
        original_filename=pdf_path.name,
    )
    artifact_paths = save_parse_result(paper_dir, result)
    document = result.document
    quality = document.quality
    tables = [block for block in document.blocks if block.type == "table"]
    non_empty_tables = [block for block in tables if block.text.strip()]
    markdown_tables = [
        block
        for block in non_empty_tables
        if sum(line.lstrip().startswith("|") for line in block.text.splitlines()) >= 2
    ]
    table_structure = _table_structure_metrics(block.text for block in tables)
    metadata_checks = {
        "title": bool(document.metadata.title),
        "authors": bool(document.metadata.authors),
        "abstract": bool(document.metadata.abstract),
        "year": bool(document.metadata.year),
        "paper_identifier": bool(document.metadata.doi or document.metadata.arxiv_id),
    }
    gates = {
        "parse_success": True,
        "page_count_match": quality.total_pages == expected_pages,
        "title_present": metadata_checks["title"],
        "abstract_present": metadata_checks["abstract"],
        "provenance_coverage_gte_95pct": quality.provenance_coverage >= 0.95,
        "no_empty_pages": not quality.empty_page_numbers,
        "tables_non_empty": not tables or len(non_empty_tables) == len(tables),
        "no_chunk_artifact": not (paper_dir / "chunks.json").exists(),
    }
    metrics = {
        "label": label,
        "source_pdf": str(pdf_path),
        "expected_pages": expected_pages,
        "parsed_pages": quality.parsed_pages,
        "reported_total_pages": quality.total_pages,
        "duration_seconds": quality.duration_seconds,
        "markdown_characters": len(result.markdown),
        "total_blocks": quality.total_blocks,
        "block_counts": quality.block_counts,
        "provenance_coverage": round(quality.provenance_coverage, 4),
        "empty_page_numbers": quality.empty_page_numbers,
        "empty_block_count": quality.empty_block_count,
        "table_count": len(tables),
        "non_empty_table_count": len(non_empty_tables),
        "markdown_table_count": len(markdown_tables),
        **table_structure,
        "metadata": {
            "title": document.metadata.title,
            "authors": document.metadata.authors,
            "abstract_preview": _preview(document.metadata.abstract),
            "year": document.metadata.year,
            "doi": document.metadata.doi,
            "arxiv_id": document.metadata.arxiv_id,
            "language": document.metadata.language,
            "field_coverage": round(sum(metadata_checks.values()) / len(metadata_checks), 2),
        },
        "table_samples": [
            {
                "page": block.page,
                "section_path": block.section_path,
                "preview": _preview(block.text, 260),
            }
            for block in tables[:3]
        ],
        "warnings": quality.warnings,
        "gates": gates,
        "gate_pass_rate": round(sum(gates.values()) / len(gates), 3),
        "artifact_paths": artifact_paths,
    }
    caption_denominator = max(
        1, metrics["table_count"] - metrics["figure_like_table_count"]
    )
    metrics["table_caption_binding_proxy"] = round(
        metrics["captioned_table_count"] / caption_denominator, 3
    )
    metrics["gates"]["table_caption_binding_proxy_gte_90pct"] = (
        metrics["table_caption_binding_proxy"] >= 0.9
    )
    metrics["gates"]["no_figure_like_table_blocks"] = (
        metrics["figure_like_table_count"] == 0
    )
    metrics["author_evaluation"] = _author_metrics(
        label, document.metadata.authors
    )
    metrics["gates"]["authors_exact_match"] = metrics["author_evaluation"]["exact_match"]
    metrics["gate_pass_rate"] = round(
        sum(metrics["gates"].values()) / len(metrics["gates"]), 3
    )
    (paper_dir / "evaluation.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metrics


def _pdf_page_count(path: Path) -> int:
    with pymupdf.open(path) as document:
        return document.page_count


def _preview(value: str | None, limit: int = 360) -> str | None:
    if not value:
        return None
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _table_structure_metrics(texts: Iterable[str]) -> Dict[str, int]:
    values = [text.strip() for text in texts]
    captioned = sum(bool(re.match(r"^Table\s+\d+\b", text, re.IGNORECASE)) for text in values)
    figure_like = sum(bool(re.match(r"^Figure\s+\d+\b", text, re.IGNORECASE)) for text in values)
    return {
        "captioned_table_count": captioned,
        "figure_like_table_count": figure_like,
        "uncaptioned_table_fragment_count": len(values) - captioned - figure_like,
    }


def _author_metrics(label: str, detected_authors: List[str]) -> Dict[str, Any]:
    expected = EXPECTED_AUTHORS[label]
    detected_map = {name.casefold(): name for name in detected_authors}
    expected_map = {name.casefold(): name for name in expected}
    correct = set(detected_map) & set(expected_map)
    precision = len(correct) / len(detected_map) if detected_map else 0.0
    recall = len(correct) / len(expected_map) if expected_map else 1.0
    return {
        "expected": expected,
        "detected": detected_authors,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "exact_match": set(detected_map) == set(expected_map),
    }


def enrich_reused_metrics(metrics: Dict[str, Any], paper_dir: Path) -> Dict[str, Any]:
    """Recompute report-only table audits without rerunning expensive parsing."""
    document = json.loads((paper_dir / "document.json").read_text(encoding="utf-8"))
    blocks = [ContentBlock(**block) for block in document.get("blocks", [])]
    markdown = (paper_dir / "content.md").read_text(encoding="utf-8")
    metadata = _extract_metadata(blocks, markdown, document.get("filename", ""))
    document["metadata"] = asdict(metadata)
    (paper_dir / "document.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    metadata_checks = {
        "title": bool(metadata.title),
        "authors": bool(metadata.authors),
        "abstract": bool(metadata.abstract),
        "year": bool(metadata.year),
        "paper_identifier": bool(metadata.doi or metadata.arxiv_id),
    }
    metrics["metadata"] = {
        "title": metadata.title,
        "authors": metadata.authors,
        "abstract_preview": _preview(metadata.abstract),
        "year": metadata.year,
        "doi": metadata.doi,
        "arxiv_id": metadata.arxiv_id,
        "language": metadata.language,
        "field_coverage": round(sum(metadata_checks.values()) / len(metadata_checks), 2),
    }
    table_texts = [
        block.get("text", "")
        for block in document.get("blocks", [])
        if block.get("type") == "table"
    ]
    metrics.update(_table_structure_metrics(table_texts))
    denominator = max(1, len(table_texts) - metrics["figure_like_table_count"])
    metrics["table_caption_binding_proxy"] = round(
        metrics["captioned_table_count"] / denominator, 3
    )
    metrics["gates"]["table_caption_binding_proxy_gte_90pct"] = (
        metrics["table_caption_binding_proxy"] >= 0.9
    )
    metrics["gates"]["no_figure_like_table_blocks"] = (
        metrics["figure_like_table_count"] == 0
    )
    metrics["author_evaluation"] = _author_metrics(metrics["label"], metadata.authors)
    metrics["gates"]["authors_exact_match"] = metrics["author_evaluation"]["exact_match"]
    metrics["gate_pass_rate"] = round(
        sum(metrics["gates"].values()) / len(metrics["gates"]), 3
    )
    return metrics


def aggregate(results: List[Dict[str, Any]], failures: List[Dict[str, str]]) -> Dict[str, Any]:
    successful = len(results)
    total = successful + len(failures)
    total_pages = sum(item["expected_pages"] for item in results)
    total_tables = sum(item["table_count"] for item in results)
    total_non_empty_tables = sum(item["non_empty_table_count"] for item in results)
    captioned_tables = sum(item["captioned_table_count"] for item in results)
    figure_like_tables = sum(item["figure_like_table_count"] for item in results)
    uncaptioned_fragments = sum(
        item["uncaptioned_table_fragment_count"] for item in results
    )
    return {
        "evaluation": "docling-parsing-v1",
        "scope": "PDF parsing only; no chunking, embedding, retrieval, or generation",
        "generated_at": datetime.now().astimezone().isoformat(),
        "papers_total": total,
        "papers_successful": successful,
        "parse_success_rate": round(successful / total, 3) if total else 0.0,
        "pages_total": total_pages,
        "page_count_match_rate": round(
            sum(item["gates"]["page_count_match"] for item in results) / successful, 3
        ) if successful else 0.0,
        "duration_seconds": round(sum(item["duration_seconds"] for item in results), 3),
        "total_blocks": sum(item["total_blocks"] for item in results),
        "total_tables": total_tables,
        "non_empty_table_rate": round(total_non_empty_tables / total_tables, 3)
        if total_tables
        else None,
        "captioned_table_count": captioned_tables,
        "captioned_table_block_rate": round(captioned_tables / total_tables, 3)
        if total_tables
        else None,
        "uncaptioned_table_fragment_count": uncaptioned_fragments,
        "figure_like_table_count": figure_like_tables,
        "mean_provenance_coverage": round(
            sum(item["provenance_coverage"] for item in results) / successful, 3
        ) if successful else 0.0,
        "title_detection_rate": round(
            sum(item["gates"]["title_present"] for item in results) / successful, 3
        ) if successful else 0.0,
        "abstract_detection_rate": round(
            sum(item["gates"]["abstract_present"] for item in results) / successful, 3
        ) if successful else 0.0,
        "author_exact_match_rate": round(
            sum(item["author_evaluation"]["exact_match"] for item in results)
            / successful,
            3,
        ) if successful else 0.0,
        "no_chunk_artifact_rate": round(
            sum(item["gates"]["no_chunk_artifact"] for item in results) / successful, 3
        ) if successful else 0.0,
        "failures": failures,
        "papers": results,
    }


def write_report(path: Path, report: Dict[str, Any]) -> None:
    lines = [
        "# Docling PDF 解析评测（v1）",
        "",
        f"> 生成时间：{report['generated_at']}",
        "",
        "## 范围",
        "",
        "本报告只评测 Docling 的 PDF 解析结果，不包含切分、Embedding、Milvus、检索或回答生成。",
        "",
        "## 总结",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 成功解析 | {report['papers_successful']}/{report['papers_total']} |",
        f"| 总页数 | {report['pages_total']} |",
        f"| 页数一致率 | {report['page_count_match_rate']:.1%} |",
        f"| 总结构块 | {report['total_blocks']} |",
        f"| 结构化表格 | {report['total_tables']} |",
        f"| 非空表格率 | {_percent(report['non_empty_table_rate'])} |",
        f"| 带 Table Caption 的表格块 | {report['captioned_table_count']}/{report['total_tables']} ({_percent(report['captioned_table_block_rate'])}) |",
        f"| 无 Caption / 疑似续表块 | {report['uncaptioned_table_fragment_count']} |",
        f"| Figure 误归为 Table | {report['figure_like_table_count']} |",
        f"| 平均页码+BBox 覆盖率 | {report['mean_provenance_coverage']:.1%} |",
        f"| 标题识别率 | {report['title_detection_rate']:.1%} |",
        f"| 摘要识别率 | {report['abstract_detection_rate']:.1%} |",
        f"| 作者列表精确匹配率 | {report['author_exact_match_rate']:.1%} |",
        f"| 无 Chunk 产物 | {report['no_chunk_artifact_rate']:.1%} |",
        f"| 总耗时 | {report['duration_seconds']:.1f}s |",
        "",
        "## 分论文结果",
        "",
        "| 论文 | 页数 | 耗时 | Blocks | Tables | Caption proxy | Figure→Table | Provenance | Gates |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["papers"]:
        lines.append(
            f"| {item['label']} | {item['parsed_pages']}/{item['expected_pages']} | "
            f"{item['duration_seconds']:.1f}s | {item['total_blocks']} | "
            f"{item['table_count']} | {item['table_caption_binding_proxy']:.1%} | "
            f"{item['figure_like_table_count']} | {item['provenance_coverage']:.1%} | "
            f"{item['gate_pass_rate']:.0%} |"
        )
    lines.extend(["", "## 元数据与人工抽查入口", ""])
    for item in report["papers"]:
        metadata = item["metadata"]
        lines.extend(
            [
                f"### {item['label']}",
                "",
                f"- 标题：{metadata['title'] or '未识别'}",
                f"- 作者：{', '.join(metadata['authors']) if metadata['authors'] else '未识别'}",
                f"- 摘要预览：{metadata['abstract_preview'] or '未识别'}",
                f"- 标识符：DOI={metadata['doi'] or '-'}；arXiv={metadata['arxiv_id'] or '-'}",
                f"- 空页：{item['empty_page_numbers'] or '无'}",
                f"- 警告：{'; '.join(item['warnings']) if item['warnings'] else '无'}",
                "",
                "表格样本：",
                "",
            ]
        )
        if item["table_samples"]:
            for sample in item["table_samples"]:
                lines.append(
                    f"- 第 {sample['page']} 页 / {' > '.join(sample['section_path']) or '无章节'}："
                    f"{sample['preview']}"
                )
        else:
            lines.append("- 未检测到表格块")
        lines.append("")
    lines.extend(
        [
            "## 人工页面核对",
            "",
            "- CharacterEval 第 9 页：源 PDF 中 Table 4 是同一 Caption 下的上下两个面板；"
            "Docling 输出为两个 table blocks，第二块没有 Caption，说明复杂表格仍存在碎片化。",
            "- MemLineage 第 14 页：源 PDF 左栏是 Figure 3 热力图；Docling 将其输出为 table block。"
            "内容可读，但语义类型和 Caption 关系不正确。",
            "- 因此 `非空表格率=100%` 只说明结构块有内容，不代表逻辑表格完整率或类型精度为 100%。",
            "",
            "## 与 baseline-v1 的关系",
            "",
            "baseline-v1 的 58 个“疑似表格相关 Chunk”是基于旧 Markdown/Chunk 信号的诊断值，"
            "不能直接当作真实表格数量。本报告统计的是 Docling 独立识别的结构化 `table` blocks。"
            "切分效果与 RAG 问答效果应在下一阶段分别评测。",
            "",
            "## 产物",
            "",
            "每篇论文目录包含 `content.md`、`document.json`、`docling-document.json`、"
            "`quality-report.json` 和 `evaluation.json`；不会生成 `chunks.json`。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def resolve_specs(upload_dir: Path, limit: int | None) -> Iterable[tuple[str, Path]]:
    specs = PAPER_SPECS[:limit] if limit else PAPER_SPECS
    for label, filename in specs:
        path = upload_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"评测 PDF 不存在: {path}")
        yield label, path


def main() -> int:
    parser_args = argparse.ArgumentParser()
    parser_args.add_argument(
        "--upload-dir",
        type=Path,
        default=PROJECT_ROOT / "output" / "uploads" / "2026" / "08" / "27",
    )
    parser_args.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "output" / "docling_evaluation_v1",
    )
    parser_args.add_argument("--limit", type=int, choices=range(1, 5))
    parser_args.add_argument(
        "--reuse-artifacts",
        action="store_true",
        help="Reuse existing document.json files and rebuild only evaluation metrics/report.",
    )
    args = parser_args.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    docling_parser = None if args.reuse_artifacts else DoclingParser(table_mode="accurate", do_ocr=False)
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []
    for label, pdf_path in resolve_specs(args.upload_dir, args.limit):
        print(f"[Docling] {label}: {pdf_path.name}", flush=True)
        try:
            paper_dir = args.output_dir / label.lower().replace("-", "_")
            if args.reuse_artifacts:
                result = json.loads(
                    (paper_dir / "evaluation.json").read_text(encoding="utf-8")
                )
                result = enrich_reused_metrics(result, paper_dir)
                (paper_dir / "evaluation.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            else:
                result = evaluate_paper(docling_parser, label, pdf_path, args.output_dir)
            results.append(result)
            print(
                f"  OK pages={result['parsed_pages']}/{result['expected_pages']} "
                f"blocks={result['total_blocks']} tables={result['table_count']} "
                f"time={result['duration_seconds']}s",
                flush=True,
            )
        except Exception as exc:  # preserve other paper results for diagnosis
            failures.append({"label": label, "pdf": str(pdf_path), "error": str(exc)})
            print(f"  FAILED: {exc}", flush=True)

    report = aggregate(results, failures)
    json_path = args.output_dir / "docling-parsing-v1.json"
    markdown_path = PROJECT_ROOT / "docs" / "evaluation" / "docling-parsing-v1.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(markdown_path, report)
    print(f"JSON: {json_path}")
    print(f"Report: {markdown_path}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
