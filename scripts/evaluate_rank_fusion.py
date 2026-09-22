"""Evaluate Dense/Reranker reciprocal-rank fusion on the evidence Gold set."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

try:
    from scripts.evaluate_evidence_retrieval import (
        _post_json,
        _validate_dataset,
        _validate_gold_against_corpus,
    )
    from scripts.evaluate_reranker_ab import (
        DEFAULT_DASHSCOPE_RERANK_URL,
        PROJECT_ROOT,
        _acceptance_decision,
        _build_rerank_payload,
        _evaluate_arm,
        _gold_rank_map,
        _paired_outcomes,
        _parse_rerank_results,
        _post_rerank,
        _rerank_hits,
        _resolve_api_key,
        _summarize,
    )
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from evaluate_evidence_retrieval import (
        _post_json,
        _validate_dataset,
        _validate_gold_against_corpus,
    )
    from evaluate_reranker_ab import (
        DEFAULT_DASHSCOPE_RERANK_URL,
        PROJECT_ROOT,
        _acceptance_decision,
        _build_rerank_payload,
        _evaluate_arm,
        _gold_rank_map,
        _paired_outcomes,
        _parse_rerank_results,
        _post_rerank,
        _rerank_hits,
        _resolve_api_key,
        _summarize,
    )


FUSION_VARIANTS = (
    ("rrf_equal", 1.0, 1.0),
    ("rrf_dense_1_5x", 1.5, 1.0),
    ("rrf_dense_2x", 2.0, 1.0),
    ("rrf_dense_3x", 3.0, 1.0),
)


def _rank_by_chunk_id(
    hits: list[dict[str, Any]], label: str
) -> dict[str, tuple[int, dict[str, Any]]]:
    ranked: dict[str, tuple[int, dict[str, Any]]] = {}
    for rank, hit in enumerate(hits, 1):
        chunk_id = str((hit.get("metadata") or {}).get("chunk_id", ""))
        if not chunk_id:
            raise ValueError(f"{label} candidate at rank {rank} has no chunk id")
        if chunk_id in ranked:
            raise ValueError(f"{label} contains duplicate chunk id: {chunk_id}")
        ranked[chunk_id] = (rank, hit)
    return ranked


def _fuse_rrf(
    dense_hits: list[dict[str, Any]],
    reranked_hits: list[dict[str, Any]],
    *,
    rrf_k: int,
    dense_weight: float,
    reranker_weight: float,
) -> list[dict[str, Any]]:
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")
    if dense_weight <= 0 or reranker_weight <= 0:
        raise ValueError("RRF weights must be positive")

    dense = _rank_by_chunk_id(dense_hits, "dense")
    reranked = _rank_by_chunk_id(reranked_hits, "reranked")
    if set(dense) != set(reranked):
        missing_from_reranker = sorted(set(dense) - set(reranked))
        missing_from_dense = sorted(set(reranked) - set(dense))
        raise ValueError(
            "Dense and reranker candidate sets differ: "
            f"missing_from_reranker={missing_from_reranker}, "
            f"missing_from_dense={missing_from_dense}"
        )

    fused: list[dict[str, Any]] = []
    for chunk_id, (dense_rank, dense_hit) in dense.items():
        rerank_rank, rerank_hit = reranked[chunk_id]
        fusion_score = (
            dense_weight / (rrf_k + dense_rank)
            + reranker_weight / (rrf_k + rerank_rank)
        )
        item = dict(dense_hit)
        item["retrieval_score"] = float(dense_hit.get("score", 0.0))
        item["rerank_score"] = float(
            rerank_hit.get("rerank_score", rerank_hit.get("score", 0.0))
        )
        item["dense_rank"] = dense_rank
        item["rerank_rank"] = rerank_rank
        item["fusion_score"] = fusion_score
        item["score"] = fusion_score
        fused.append(item)

    return sorted(
        fused,
        key=lambda item: (
            -float(item["fusion_score"]),
            int(item["dense_rank"]),
            int(item["rerank_rank"]),
            str((item.get("metadata") or {}).get("chunk_id", "")),
        ),
    )


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--collection")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument(
        "--reranker-api-url",
        default=os.getenv("RERANKER_API_URL", DEFAULT_DASHSCOPE_RERANK_URL),
    )
    parser.add_argument(
        "--reranker-model",
        default=os.getenv("RERANKER_MODEL_NAME", "qwen3-rerank"),
    )
    parser.add_argument("--reranker-key-env", default="RERANKER_API_KEY")
    parser.add_argument(
        "--reranker-format",
        choices=("dashscope", "compatible"),
        default=os.getenv("RERANKER_REQUEST_FORMAT", "dashscope"),
    )
    parser.add_argument("--reranker-timeout", type=int, default=120)
    parser.add_argument("--min-mrr", type=float, default=0.75)
    parser.add_argument("--min-ndcg", type=float, default=0.82)
    parser.add_argument("--max-added-latency", type=float, default=1.0)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.top_k <= 0 or args.candidate_k < args.top_k:
        raise SystemExit("candidate-k must be greater than or equal to top-k")
    if args.rrf_k <= 0:
        raise SystemExit("rrf-k must be positive")

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    _validate_dataset(dataset)
    collection = args.collection or dataset.get("collection_id")
    if not collection:
        raise SystemExit("No collection id supplied")
    corpus_validation = (
        _validate_gold_against_corpus(dataset, args.corpus) if args.corpus else None
    )
    api_key, key_source = _resolve_api_key(args.reranker_key_env)

    results: list[dict[str, Any]] = []
    fusion_latencies: dict[str, list[float]] = {
        name: [] for name, _, _ in FUSION_VARIANTS
    }
    for case in dataset["cases"]:
        retrieve_started = time.perf_counter()
        response = _post_json(
            f"{args.api_url}/search",
            {
                "collection_name": collection,
                "query_text": case["question"],
                "top_k": args.candidate_k,
            },
        )
        candidates = response.get("results", [])
        retrieve_latency = time.perf_counter() - retrieve_started
        if len(candidates) < args.top_k:
            raise RuntimeError(
                f"{case['id']}: expected at least {args.top_k} candidates, "
                f"received {len(candidates)}"
            )

        rerank_started = time.perf_counter()
        rerank_response = _post_rerank(
            args.reranker_api_url,
            api_key,
            _build_rerank_payload(
                model=args.reranker_model,
                query=case["question"],
                documents=[str(hit.get("chunk_text", "")) for hit in candidates],
                top_n=args.candidate_k,
                request_format=args.reranker_format,
            ),
            timeout=args.reranker_timeout,
        )
        ranking = _parse_rerank_results(rerank_response, len(candidates))
        rerank_latency = time.perf_counter() - rerank_started
        reranked_candidates = _rerank_hits(candidates, ranking)

        case_result: dict[str, Any] = {
            "id": case["id"],
            "category": case["category"],
            "answerable": case["answerable"],
            "candidate_count": len(candidates),
            "gold_candidate_ranks": _gold_rank_map(case, candidates),
            "gold_reranked_candidate_ranks": _gold_rank_map(
                case, reranked_candidates
            ),
            "dense": _evaluate_arm(
                case, candidates[: args.top_k], retrieve_latency
            ),
            "reranked": _evaluate_arm(
                case,
                reranked_candidates[: args.top_k],
                retrieve_latency + rerank_latency,
            ),
            "rerank_latency_seconds": round(rerank_latency, 3),
        }

        for name, dense_weight, reranker_weight in FUSION_VARIANTS:
            fusion_started = time.perf_counter()
            fused_candidates = _fuse_rrf(
                candidates,
                reranked_candidates,
                rrf_k=args.rrf_k,
                dense_weight=dense_weight,
                reranker_weight=reranker_weight,
            )
            fusion_latency = time.perf_counter() - fusion_started
            fusion_latencies[name].append(fusion_latency)
            case_result[name] = _evaluate_arm(
                case,
                fused_candidates[: args.top_k],
                retrieve_latency + rerank_latency + fusion_latency,
            )
            case_result[f"{name}_gold_ranks"] = _gold_rank_map(
                case, fused_candidates
            )

        results.append(case_result)
        print(
            f"{case['id']} complete: retrieve={retrieve_latency:.3f}s "
            f"rerank={rerank_latency:.3f}s"
        )

    arm_names = ["dense", "reranked"] + [
        name for name, _, _ in FUSION_VARIANTS
    ]
    summaries = {arm: _summarize(results, arm) for arm in arm_names}
    dense_summary = summaries["dense"]
    acceptance: dict[str, dict[str, Any]] = {}
    for arm in arm_names[1:]:
        added_latency = (
            summaries[arm]["mean_latency_seconds"]
            - dense_summary["mean_latency_seconds"]
        )
        acceptance[arm] = _acceptance_decision(
            dense_summary,
            summaries[arm],
            added_latency_seconds=added_latency,
            min_mrr=args.min_mrr,
            min_ndcg=args.min_ndcg,
            max_added_latency_seconds=args.max_added_latency,
        )

    eligible = [
        name
        for name, decision in acceptance.items()
        if decision["decision"] == "go"
    ]
    recommended = (
        max(
            eligible,
            key=lambda name: (
                summaries[name]["evidence_set_mrr"],
                summaries[name]["mean_ndcg"],
                -summaries[name]["mean_latency_seconds"],
            ),
        )
        if eligible
        else None
    )

    report = {
        "schema_version": "1.0",
        "experiment_id": "scholarlens-rank-fusion-v1",
        "dataset_id": dataset["dataset_id"],
        "annotation_status": dataset["annotation_status"],
        "collection_id": collection,
        "corpus_validation": corpus_validation,
        "configuration": {
            "candidate_k": args.candidate_k,
            "top_k": args.top_k,
            "rrf_k": args.rrf_k,
            "reranker_model": args.reranker_model,
            "reranker_host": urlparse(args.reranker_api_url).netloc,
            "reranker_request_format": args.reranker_format,
            "api_key_source": key_source,
            "variants": {
                name: {
                    "dense_weight": dense_weight,
                    "reranker_weight": reranker_weight,
                }
                for name, dense_weight, reranker_weight in FUSION_VARIANTS
            },
        },
        "summary": summaries,
        "paired_outcomes": {
            arm: {
                "evidence_set_mrr": _paired_outcomes(
                    results, "evidence_set_reciprocal_rank"
                )
                if arm == "reranked"
                else _paired_outcomes_for_arms(
                    results, "dense", arm, "evidence_set_reciprocal_rank"
                ),
                "ndcg": _paired_outcomes(results, "ndcg")
                if arm == "reranked"
                else _paired_outcomes_for_arms(results, "dense", arm, "ndcg"),
            }
            for arm in arm_names[1:]
        },
        "mean_fusion_latency_seconds": {
            name: statistics.mean(values)
            for name, values in fusion_latencies.items()
        },
        "acceptance": acceptance,
        "selection": {
            "decision": (
                "go-for-held-out-validation" if recommended else "no-go"
            ),
            "recommended_variant": recommended,
            "eligible_variants": eligible,
            "warning": (
                "Variant selection used the v1 Gold set; validate the chosen "
                "configuration on new held-out questions before production."
            ),
        },
        "results": results,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": summaries,
                "acceptance": acceptance,
                "selection": report["selection"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _paired_outcomes_for_arms(
    results: list[dict[str, Any]], baseline: str, challenger: str, metric: str
) -> dict[str, int]:
    outcomes = {"wins": 0, "ties": 0, "losses": 0}
    for item in results:
        if not item["answerable"]:
            continue
        base_value = float(item[baseline][metric])
        challenger_value = float(item[challenger][metric])
        if challenger_value > base_value + 1e-12:
            outcomes["wins"] += 1
        elif challenger_value < base_value - 1e-12:
            outcomes["losses"] += 1
        else:
            outcomes["ties"] += 1
    return outcomes


if __name__ == "__main__":
    raise SystemExit(main())
