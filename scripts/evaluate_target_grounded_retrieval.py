"""Run explicit-plan development checks for filename-grounded retrieval.

This evaluator does not call a query-planning or answer-generation model. It
exercises the production ChatService catalog lookup, target resolution,
Milvus filename filter pushdown, RRF, and coverage selection against a small
development dataset.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.chat.kb_chat import ChatRequest, ChatService  # noqa: E402
from backend.chat.multi_query_retrieval import (  # noqa: E402
    RetrievalPlan,
    RetrievalSubquery,
)


def _validate_dataset(dataset: dict[str, Any]) -> None:
    if dataset.get("split") != "development":
        raise ValueError("target-grounding evaluator only accepts development data")
    cases = dataset.get("retrieval_cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset requires retrieval_cases")
    seen: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id in seen:
            raise ValueError(f"missing or duplicate retrieval case id: {case_id!r}")
        seen.add(case_id)
        subqueries = case.get("subqueries")
        expected = case.get("expected_filenames")
        if not isinstance(subqueries, list) or len(subqueries) != 2:
            raise ValueError(f"{case_id}: exactly two subqueries are required")
        if not isinstance(expected, list) or len(set(expected)) != 2:
            raise ValueError(f"{case_id}: exactly two expected filenames are required")


def _explicit_plan(case: dict[str, Any]) -> RetrievalPlan:
    return RetrievalPlan(
        mode="comparison",
        subqueries=tuple(
            RetrievalSubquery(
                query_id=str(item["id"]),
                target=str(item["target"]),
                query=str(item["query"]),
            )
            for item in case["subqueries"]
        ),
        planner_source="dataset_explicit_subqueries",
    )


async def _run_case(
    case: dict[str, Any],
    *,
    service: ChatService,
    collection: str,
    api_url: str,
    top_k: int,
) -> dict[str, Any]:
    plan = _explicit_plan(case)

    async def fixed_plan(*_args: Any, **_kwargs: Any) -> RetrievalPlan:
        return plan

    service.plan_retrieval = fixed_plan  # type: ignore[method-assign]
    started = time.perf_counter()
    execution = await service.retrieve_for_request(
        ChatRequest(
            query=str(case["question"]),
            collection_name=collection,
            llm_config={
                "api_url": "https://unused.invalid/v1",
                "api_key": "not-used",
                "model_name": "not-used",
            },
            top_k=top_k,
            score_threshold=0.1,
            use_multi_query=True,
            multi_query_config={
                "candidate_k_per_query": 10,
                "rrf_k": 60,
                "original_reserve": 2,
                "per_target_reserve": 2,
            },
            stream=False,
            return_source=True,
            milvus_api_url=api_url,
        )
    )
    expected = set(case["expected_filenames"])
    retrieved = {str(item.get("filename", "")) for item in execution.documents}
    return {
        "case_id": case["id"],
        "expected_filenames": sorted(expected),
        "retrieved_filenames": sorted(retrieved),
        "required_source_coverage": len(expected & retrieved) / len(expected),
        "latency_seconds": round(time.perf_counter() - started, 4),
        "trace": execution.trace,
        "hits": [
            {
                "rank": rank,
                "filename": item.get("filename"),
                "chunk_id": (item.get("metadata") or {}).get("chunk_id"),
                "matched_query_ids": item.get("matched_query_ids"),
            }
            for rank, item in enumerate(execution.documents, 1)
        ],
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    _validate_dataset(dataset)
    service = ChatService()
    results = []
    for case in dataset["retrieval_cases"]:
        result = await _run_case(
            case,
            service=service,
            collection=args.collection,
            api_url=args.api_url,
            top_k=args.top_k,
        )
        results.append(result)
        print(
            f"{result['case_id']}: coverage="
            f"{result['required_source_coverage']:.0%} "
            f"resolution={result['trace']['target_resolution_status']}"
        )
    complete_resolution_rate = sum(
        item["trace"]["target_resolution_status"] == "complete"
        for item in results
    ) / len(results)
    complete_source_rate = sum(
        item["required_source_coverage"] == 1.0 for item in results
    ) / len(results)
    return {
        "schema_version": "1.0",
        "experiment_id": "scholarlens-target-grounded-retrieval-dev-v1",
        "dataset_id": dataset["dataset_id"],
        "dataset_split": dataset["split"],
        "collection_id": args.collection,
        "configuration": {
            "top_k": args.top_k,
            "candidate_k_per_query": 10,
            "original_reserve": 2,
            "per_target_reserve": 2,
            "rrf_k": 60,
            "score_threshold": 0.1,
        },
        "summary": {
            "case_count": len(results),
            "complete_target_resolution_rate": complete_resolution_rate,
            "complete_required_source_rate": complete_source_rate,
        },
        "acceptance": {
            "passed": complete_resolution_rate == 1.0 and complete_source_rate == 1.0
        },
        "results": results,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    rows = [
        "| Case | Target resolution | Required sources | Latency |",
        "|---|---:|---:|---:|",
    ]
    for item in report["results"]:
        rows.append(
            "| {case} | {resolution} | {coverage:.0%} | {latency:.3f}s |".format(
                case=item["case_id"],
                resolution=item["trace"]["target_resolution_status"],
                coverage=item["required_source_coverage"],
                latency=item["latency_seconds"],
            )
        )
    summary = report["summary"]
    return "\n".join(
        [
            "# Target-grounded Retrieval Development Evaluation",
            "",
            f"- Dataset: `{report['dataset_id']}`",
            f"- Acceptance: **{'PASS' if report['acceptance']['passed'] else 'FAIL'}**",
            f"- Complete target resolution: {summary['complete_target_resolution_rate']:.2%}",
            f"- Complete required-source coverage: {summary['complete_required_source_rate']:.2%}",
            "",
            *rows,
            "",
            "This is a development evaluation and must not be presented as a fresh held-out result.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(_run(args))
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized)
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(_render_markdown(report), encoding="utf-8")
    return 0 if report["acceptance"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
