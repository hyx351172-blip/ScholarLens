"""Evaluate multi-query retrieval with coverage-aware final selection.

This module deliberately evaluates query orchestration separately from an LLM
query planner.  Development datasets provide explicit retrieval subqueries, so
the experiment answers one question at a time: does independent retrieval per
comparison target fix the candidate-recall and final-coverage failures observed
for cross-paper questions?
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

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


def _chunk_id(hit: dict[str, Any]) -> str:
    return str((hit.get("metadata") or {}).get("chunk_id", ""))


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


def _query_rrf(
    ranked_hits_by_query: dict[str, list[dict[str, Any]]],
    *,
    rrf_k: int = 60,
) -> list[dict[str, Any]]:
    """Merge query result lists with reciprocal-rank fusion and provenance."""

    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")
    if not ranked_hits_by_query:
        return []

    fused_by_id: dict[str, dict[str, Any]] = {}
    for query_id, hits in ranked_hits_by_query.items():
        seen_in_query: set[str] = set()
        for rank, hit in enumerate(hits, 1):
            chunk_id = _chunk_id(hit)
            if not chunk_id:
                raise ValueError(f"{query_id} candidate at rank {rank} has no chunk id")
            if chunk_id in seen_in_query:
                raise ValueError(f"{query_id} contains duplicate chunk id: {chunk_id}")
            seen_in_query.add(chunk_id)

            if chunk_id not in fused_by_id:
                item = dict(hit)
                item["retrieval_score"] = float(hit.get("score", 0.0))
                item["matched_query_ids"] = []
                item["query_ranks"] = {}
                item["query_rrf_score"] = 0.0
                fused_by_id[chunk_id] = item
            item = fused_by_id[chunk_id]
            item["retrieval_score"] = max(
                float(item["retrieval_score"]), float(hit.get("score", 0.0))
            )
            item["matched_query_ids"].append(query_id)
            item["query_ranks"][query_id] = rank
            item["query_rrf_score"] += 1.0 / (rrf_k + rank)

    fused = list(fused_by_id.values())
    for item in fused:
        item["score"] = float(item["query_rrf_score"])
    return sorted(
        fused,
        key=lambda item: (
            -float(item["query_rrf_score"]),
            min(int(rank) for rank in item["query_ranks"].values()),
            _chunk_id(item),
        ),
    )


def _coverage_select(
    fused_hits: list[dict[str, Any]],
    required_query_ids: list[str],
    *,
    top_k: int,
    original_reserve: int = 0,
    per_target_reserve: int = 1,
) -> list[dict[str, Any]]:
    """Select Top-K with baseline safety and comparison-target coverage."""

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if len(required_query_ids) != len(set(required_query_ids)):
        raise ValueError("required query ids must be unique")
    if original_reserve < 0:
        raise ValueError("original_reserve cannot be negative")
    if per_target_reserve <= 0:
        raise ValueError("per_target_reserve must be positive")
    if original_reserve + per_target_reserve * len(required_query_ids) > top_k:
        raise ValueError(
            "top_k cannot be smaller than the configured reserve budget"
        )

    selected_ids: set[str] = set()
    selected: list[dict[str, Any]] = []

    original_candidates = sorted(
        (
            item
            for item in fused_hits
            if "original" in (item.get("query_ranks") or {})
        ),
        key=lambda item: (
            int(item["query_ranks"]["original"]),
            _chunk_id(item),
        ),
    )
    for candidate in original_candidates[:original_reserve]:
        selected.append(candidate)
        selected_ids.add(_chunk_id(candidate))

    for query_id in required_query_ids:
        target_candidates = sorted(
            (
                item
                for item in fused_hits
                if query_id in (item.get("query_ranks") or {})
            ),
            key=lambda item: (
                int(item["query_ranks"][query_id]),
                _chunk_id(item),
            ),
        )
        for candidate in target_candidates[:per_target_reserve]:
            chunk_id = _chunk_id(candidate)
            if chunk_id in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(chunk_id)

    for item in fused_hits:
        if len(selected) >= top_k:
            break
        chunk_id = _chunk_id(item)
        if chunk_id in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(chunk_id)

    fused_order = {_chunk_id(item): rank for rank, item in enumerate(fused_hits)}
    return sorted(selected, key=lambda item: fused_order[_chunk_id(item)])


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
        original_started = time.perf_counter()
        original_response = _post_json(
            f"{args.api_url}/search",
            {
                "collection_name": collection,
                "query_text": case["question"],
                "top_k": args.candidate_k,
            },
        )
        original_latency = time.perf_counter() - original_started
        original_hits = original_response.get("results", [])

        ranked_by_query = {"original": original_hits}
        query_latencies = {"original": round(original_latency, 3)}
        multi_started = time.perf_counter()
        for subquery in case.get("retrieval_subqueries", []):
            started = time.perf_counter()
            response = _post_json(
                f"{args.api_url}/search",
                {
                    "collection_name": collection,
                    "query_text": subquery["query"],
                    "top_k": args.candidate_k,
                },
            )
            query_id = str(subquery["id"])
            ranked_by_query[query_id] = response.get("results", [])
            query_latencies[query_id] = round(time.perf_counter() - started, 3)
        # The original query request is shared by both arms, so include it in
        # multi-query end-to-end latency even though its response was reused.
        multi_latency = original_latency + (time.perf_counter() - multi_started)

        fused = _query_rrf(ranked_by_query, rrf_k=args.rrf_k)
        required_query_ids = [
            str(item["id"]) for item in case.get("retrieval_subqueries", [])
        ]
        multi_hits = _coverage_select(
            fused,
            required_query_ids,
            top_k=args.top_k,
            original_reserve=args.original_reserve,
            per_target_reserve=args.per_target_reserve,
        )
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
