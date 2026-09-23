"""Evaluate multi-query retrieval with coverage-aware final selection.

This module deliberately evaluates query orchestration separately from an LLM
query planner.  Development datasets provide explicit retrieval subqueries, so
the experiment answers one question at a time: does independent retrieval per
comparison target fix the candidate-recall and final-coverage failures observed
for cross-paper questions?
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.chat.multi_query_retrieval import (  # noqa: E402
    RetrievalPlan,
    RetrievalSubquery,
    _chunk_id,
    _coverage_select,
    _query_rrf,
    execute_retrieval_plan,
)

try:
    from scripts.evaluate_evidence_retrieval import (
        _best_set_metrics,
        _gold_ids,
        _ndcg,
        _post_json,
        _validate_dataset,
        _validate_gold_against_corpus,
    )
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from evaluate_evidence_retrieval import (
        _best_set_metrics,
        _gold_ids,
        _ndcg,
        _post_json,
        _validate_dataset,
        _validate_gold_against_corpus,
    )

def _validate_query_plans(dataset: dict[str, Any]) -> None:
    """Validate explicit development-time retrieval plans."""

    for case in dataset.get("cases", []):
        if case.get("category") != "cross_paper_comparison":
            continue
        subqueries = case.get("retrieval_subqueries")
        if not isinstance(subqueries, list) or len(subqueries) < 2:
            raise ValueError(
                f"{case.get('id')}: cross-paper case requires at least two "
                "retrieval_subqueries"
            )
        ids = [str(item.get("id", "")).strip() for item in subqueries]
        queries = [str(item.get("query", "")).strip() for item in subqueries]
        if any(not query_id or query_id == "original" for query_id in ids):
            raise ValueError(
                f"{case.get('id')}: subquery ids must be nonempty and cannot be 'original'"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(f"{case.get('id')}: subquery ids must be unique")
        if any(not query for query in queries):
            raise ValueError(f"{case.get('id')}: subquery text must be nonempty")

def _arm_result(
    hits: list[dict[str, Any]],
    evidence_sets: list[list[str]],
    *,
    answerable: bool,
    latency_seconds: float,
) -> dict[str, Any]:
    retrieved_ids = [_chunk_id(hit) for hit in hits]
    strict_hit, recall, reciprocal_rank = _best_set_metrics(
        retrieved_ids, evidence_sets
    )
    return {
        "strict_evidence_hit": strict_hit if answerable else None,
        "best_evidence_set_recall": recall if answerable else None,
        "evidence_set_reciprocal_rank": reciprocal_rank if answerable else None,
        "ndcg": _ndcg(retrieved_ids, evidence_sets) if answerable else None,
        "latency_seconds": round(latency_seconds, 3),
        "hits": [
            {
                "rank": rank,
                "chunk_id": _chunk_id(hit),
                "filename": hit.get("filename"),
                "page_start": (hit.get("metadata") or {}).get("page_start"),
                "content_type": (hit.get("metadata") or {}).get("content_type"),
                "score": round(float(hit.get("score", 0.0)), 8),
                "matched_query_ids": hit.get("matched_query_ids"),
                "query_ranks": hit.get("query_ranks"),
            }
            for rank, hit in enumerate(hits, 1)
        ],
    }


def _summarize(results: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    answerable = [item for item in results if item["answerable"]]
    latencies = [float(item[arm]["latency_seconds"]) for item in results]
    return {
        "strict_evidence_hit_rate": sum(
            bool(item[arm]["strict_evidence_hit"]) for item in answerable
        )
        / len(answerable),
        "mean_best_evidence_set_recall": statistics.mean(
            float(item[arm]["best_evidence_set_recall"]) for item in answerable
        ),
        "evidence_set_mrr": statistics.mean(
            float(item[arm]["evidence_set_reciprocal_rank"])
            for item in answerable
        ),
        "mean_ndcg": statistics.mean(
            float(item[arm]["ndcg"]) for item in answerable
        ),
        "mean_latency_seconds": statistics.mean(latencies),
        "median_latency_seconds": statistics.median(latencies),
    }


async def _run_case_retrieval(
    case: dict[str, Any],
    *,
    api_url: str,
    collection: str,
    candidate_k: int,
    top_k: int,
    rrf_k: int,
    original_reserve: int,
    per_target_reserve: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float, float, dict[str, float]]:
    """Run the same parallel orchestration used by the chat service."""

    subqueries = tuple(
        RetrievalSubquery(
            query_id=str(item["id"]),
            target=str(item.get("target", item["id"])),
            query=str(item["query"]),
        )
        for item in case.get("retrieval_subqueries", [])
    )
    plan = RetrievalPlan(
        mode="comparison",
        subqueries=subqueries,
        planner_source="dataset_explicit_subqueries",
    )
    baseline_started = time.perf_counter()
    baseline_response = await asyncio.to_thread(
        _post_json,
        f"{api_url}/search",
        {
            "collection_name": collection,
            "query_text": case["question"],
            "top_k": candidate_k,
        },
    )
    baseline_latency = time.perf_counter() - baseline_started
    baseline_hits = baseline_response.get("results", [])

    async def retrieve(query: str) -> list[dict[str, Any]]:
        response = await asyncio.to_thread(
            _post_json,
            f"{api_url}/search",
            {
                "collection_name": collection,
                "query_text": query,
                "top_k": candidate_k,
            },
        )
        return response.get("results", [])

    started = time.perf_counter()
    execution = await execute_retrieval_plan(
        original_query=case["question"],
        plan=plan,
        retrieve=retrieve,
        top_k=top_k,
        rrf_k=rrf_k,
        original_reserve=original_reserve,
        per_target_reserve=per_target_reserve,
    )
    parallel_latency = time.perf_counter() - started
    query_latencies = {
        str(item["id"]): float(item["latency_seconds"])
        for item in execution.trace["queries"]
    }
    return (
        baseline_hits,
        execution.documents,
        baseline_latency,
        parallel_latency,
        query_latencies,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--collection")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument(
        "--original-reserve",
        type=int,
        default=4,
        help="Keep this many leading original-query hits before target coverage fill.",
    )
    parser.add_argument(
        "--per-target-reserve",
        type=int,
        default=2,
        help="Keep this many leading hits from each comparison-target query.",
    )
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.top_k <= 0 or args.candidate_k < args.top_k:
        parser.error("candidate-k must be greater than or equal to top-k")
    if args.rrf_k <= 0:
        parser.error("rrf-k must be positive")
    if args.original_reserve < 0:
        parser.error("original-reserve cannot be negative")
    if args.per_target_reserve <= 0:
        parser.error("per-target-reserve must be positive")

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    _validate_dataset(dataset)
    _validate_query_plans(dataset)
    corpus_validation = (
        _validate_gold_against_corpus(dataset, args.corpus) if args.corpus else None
    )
    collection = args.collection or dataset.get("collection_id")
    if not collection:
        raise SystemExit("No collection id supplied")

    results: list[dict[str, Any]] = []
    for case in dataset["cases"]:
        (
            original_hits,
            multi_hits,
            original_latency,
            multi_latency,
            query_latencies,
        ) = asyncio.run(
            _run_case_retrieval(
                case,
                api_url=args.api_url,
                collection=collection,
                candidate_k=args.candidate_k,
                top_k=args.top_k,
                rrf_k=args.rrf_k,
                original_reserve=args.original_reserve,
                per_target_reserve=args.per_target_reserve,
            )
        )
        required_query_ids = [
            str(item["id"]) for item in case.get("retrieval_subqueries", [])
        ]
        evidence_sets = _gold_ids(case)
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "question": case["question"],
                "answerable": case["answerable"],
                "required_query_ids": required_query_ids,
                "query_latencies_seconds": query_latencies,
                "baseline_dense": _arm_result(
                    original_hits[: args.top_k],
                    evidence_sets,
                    answerable=case["answerable"],
                    latency_seconds=original_latency,
                ),
                "multi_query_coverage": _arm_result(
                    multi_hits,
                    evidence_sets,
                    answerable=case["answerable"],
                    latency_seconds=multi_latency,
                ),
            }
        )
        print(f"{case['id']} complete")

    baseline = _summarize(results, "baseline_dense")
    multi_query = _summarize(results, "multi_query_coverage")
    strict_outcomes = {"wins": 0, "ties": 0, "losses": 0}
    for item in results:
        before = bool(item["baseline_dense"]["strict_evidence_hit"])
        after = bool(item["multi_query_coverage"]["strict_evidence_hit"])
        if after and not before:
            strict_outcomes["wins"] += 1
        elif before and not after:
            strict_outcomes["losses"] += 1
        else:
            strict_outcomes["ties"] += 1

    report = {
        "schema_version": "1.0",
        "dataset_id": dataset["dataset_id"],
        "annotation_status": dataset["annotation_status"],
        "collection_id": collection,
        "configuration": {
            "candidate_k_per_query": args.candidate_k,
            "top_k": args.top_k,
            "query_rrf_k": args.rrf_k,
            "original_query_reserve": args.original_reserve,
            "per_target_reserve": args.per_target_reserve,
            "planner": "dataset_explicit_subqueries",
            "query_execution": "parallel",
            "selector": "original_reserve_then_per_target_reserve_then_global_fill",
        },
        "corpus_validation": corpus_validation,
        "summary": {
            "case_count": len(results),
            "baseline_dense": baseline,
            "multi_query_coverage": multi_query,
            "strict_evidence_outcomes": strict_outcomes,
            "delta": {
                "strict_evidence_hit_rate": (
                    multi_query["strict_evidence_hit_rate"]
                    - baseline["strict_evidence_hit_rate"]
                ),
                "evidence_set_mrr": (
                    multi_query["evidence_set_mrr"]
                    - baseline["evidence_set_mrr"]
                ),
                "mean_ndcg": multi_query["mean_ndcg"] - baseline["mean_ndcg"],
                "mean_latency_seconds": (
                    multi_query["mean_latency_seconds"]
                    - baseline["mean_latency_seconds"]
                ),
            },
        },
        "results": results,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
