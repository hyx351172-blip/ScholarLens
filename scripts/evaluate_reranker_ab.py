"""Run a paired Dense-only vs Dense+Reranker evidence retrieval experiment."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

try:
    from scripts.evaluate_evidence_retrieval import (
        _best_set_metrics,
        _gold_ids,
        _ndcg,
        _post_json,
        _validate_dataset,
        _validate_gold_against_corpus,
    )
except ModuleNotFoundError:  # Direct execution: python scripts/evaluate_reranker_ab.py
    from evaluate_evidence_retrieval import (
        _best_set_metrics,
        _gold_ids,
        _ndcg,
        _post_json,
        _validate_dataset,
        _validate_gold_against_corpus,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DASHSCOPE_RERANK_URL = (
    "https://dashscope.aliyuncs.com/"
    "api/v1/services/rerank/text-rerank/text-rerank"
)


def _build_rerank_payload(
    model: str,
    query: str,
    documents: list[str],
    top_n: int,
    request_format: str = "dashscope",
) -> dict[str, Any]:
    if request_format == "compatible":
        return {
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
            "instruct": (
                "Given a scientific question, retrieve passages that provide "
                "direct evidence for the answer."
            ),
        }
    if request_format != "dashscope":
        raise ValueError(f"Unsupported reranker request format: {request_format}")
    return {
        "model": model,
        "input": {"query": query, "documents": documents},
        "parameters": {"return_documents": False, "top_n": top_n},
    }


def _parse_rerank_results(
    payload: dict[str, Any], document_count: int
) -> list[tuple[int, float]]:
    if payload.get("code"):
        raise ValueError(
            f"Reranker error {payload.get('code')}: {payload.get('message', '')}"
        )
    container = payload.get("output") if isinstance(payload.get("output"), dict) else payload
    raw_results = container.get("results") if isinstance(container, dict) else None
    if not isinstance(raw_results, list) or not raw_results:
        raise ValueError("Reranker response contains no results")

    parsed: list[tuple[int, float]] = []
    seen: set[int] = set()
    for item in raw_results:
        if not isinstance(item, dict) or "index" not in item:
            raise ValueError("Reranker result is missing index")
        index = int(item["index"])
        if index < 0 or index >= document_count:
            raise ValueError(f"Reranker index out of range: {index}")
        if index in seen:
            raise ValueError(f"Reranker returned duplicate index: {index}")
        score = item.get("relevance_score", item.get("score"))
        if score is None:
            raise ValueError(f"Reranker result {index} is missing a score")
        seen.add(index)
        parsed.append((index, float(score)))
    return sorted(parsed, key=lambda item: item[1], reverse=True)


def _rerank_hits(
    hits: list[dict[str, Any]], ranking: list[tuple[int, float]]
) -> list[dict[str, Any]]:
    reranked: list[dict[str, Any]] = []
    for index, score in ranking:
        hit = dict(hits[index])
        hit["retrieval_score"] = float(hit.get("score", 0.0))
        hit["rerank_score"] = score
        hit["score"] = score
        reranked.append(hit)
    return reranked


def _post_rerank(
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Reranker HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Reranker request failed: {exc.reason}") from exc


def _compact_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rank": rank,
            "chunk_id": (hit.get("metadata") or {}).get("chunk_id"),
            "filename": hit.get("filename"),
            "page_start": (hit.get("metadata") or {}).get("page_start"),
            "content_type": (hit.get("metadata") or {}).get("content_type"),
            "score": round(float(hit.get("score", 0.0)), 6),
            "retrieval_score": (
                round(float(hit["retrieval_score"]), 6)
                if "retrieval_score" in hit
                else None
            ),
            "rerank_score": (
                round(float(hit["rerank_score"]), 6)
                if "rerank_score" in hit
                else None
            ),
        }
        for rank, hit in enumerate(hits, 1)
    ]


def _gold_rank_map(
    case: dict[str, Any], hits: list[dict[str, Any]]
) -> dict[str, int | None]:
    ranks = {
        str((hit.get("metadata") or {}).get("chunk_id", "")): rank
        for rank, hit in enumerate(hits, 1)
    }
    gold_ids = {
        chunk_id for evidence_set in _gold_ids(case) for chunk_id in evidence_set
    }
    return {chunk_id: ranks.get(chunk_id) for chunk_id in sorted(gold_ids)}


def _evaluate_arm(
    case: dict[str, Any], hits: list[dict[str, Any]], latency_seconds: float
) -> dict[str, Any]:
    evidence_sets = _gold_ids(case)
    retrieved_ids = [
        str((hit.get("metadata") or {}).get("chunk_id", "")) for hit in hits
    ]
    strict_hit, best_recall, set_rr = _best_set_metrics(
        retrieved_ids, evidence_sets
    )
    answerable = bool(case["answerable"])
    return {
        "strict_evidence_hit": strict_hit if answerable else None,
        "best_evidence_set_recall": best_recall if answerable else None,
        "evidence_set_reciprocal_rank": set_rr if answerable else None,
        "ndcg": _ndcg(retrieved_ids, evidence_sets) if answerable else None,
        "latency_seconds": round(latency_seconds, 3),
        "max_score": max(
            (float(hit.get("score", 0.0)) for hit in hits), default=0.0
        ),
        "hits": _compact_hits(hits),
    }


def _summarize(results: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    selected = [item[arm] for item in results]
    answerable = [
        item[arm] for item in results if bool(item.get("answerable"))
    ]
    unanswerable = [
        (item["id"], item[arm])
        for item in results
        if not bool(item.get("answerable"))
    ]
    latencies = [float(item["latency_seconds"]) for item in selected]
    return {
        "strict_evidence_hit_rate": statistics.mean(
            bool(item["strict_evidence_hit"]) for item in answerable
        ),
        "mean_best_evidence_set_recall": statistics.mean(
            float(item["best_evidence_set_recall"]) for item in answerable
        ),
        "evidence_set_mrr": statistics.mean(
            float(item["evidence_set_reciprocal_rank"]) for item in answerable
        ),
        "mean_ndcg": statistics.mean(float(item["ndcg"]) for item in answerable),
        "mean_latency_seconds": statistics.mean(latencies),
        "median_latency_seconds": statistics.median(latencies),
        "unanswerable_max_scores": {
            case_id: item["max_score"] for case_id, item in unanswerable
        },
    }


def _paired_outcomes(
    results: list[dict[str, Any]], metric: str
) -> dict[str, int]:
    outcomes = {"wins": 0, "ties": 0, "losses": 0}
    for item in results:
        if not item["answerable"]:
            continue
        dense = float(item["dense"][metric])
        reranked = float(item["reranked"][metric])
        if reranked > dense + 1e-12:
            outcomes["wins"] += 1
        elif reranked < dense - 1e-12:
            outcomes["losses"] += 1
        else:
            outcomes["ties"] += 1
    return outcomes


def _acceptance_decision(
    dense: dict[str, Any],
    reranked: dict[str, Any],
    added_latency_seconds: float,
    min_mrr: float,
    min_ndcg: float,
    max_added_latency_seconds: float,
) -> dict[str, Any]:
    gates = {
        "strict_hit_rate_100_percent": (
            float(reranked["strict_evidence_hit_rate"]) >= 1.0 - 1e-12
        ),
        "hit_rate_non_regression": (
            float(reranked["strict_evidence_hit_rate"])
            >= float(dense["strict_evidence_hit_rate"]) - 1e-12
        ),
        "minimum_mrr": float(reranked["evidence_set_mrr"]) >= min_mrr,
        "minimum_ndcg": float(reranked["mean_ndcg"]) >= min_ndcg,
        "latency_budget": added_latency_seconds <= max_added_latency_seconds,
    }
    return {
        "decision": "go" if all(gates.values()) else "no-go",
        "thresholds": {
            "strict_evidence_hit_rate": 1.0,
            "minimum_mrr": min_mrr,
            "minimum_ndcg": min_ndcg,
            "maximum_added_latency_seconds": max_added_latency_seconds,
        },
        "gates": gates,
    }


def _resolve_api_key(primary_name: str) -> tuple[str, str]:
    for name in (primary_name, "DASHSCOPE_API_KEY", "API_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            return value, name
    raise SystemExit(
        f"No reranker API key found. Set {primary_name}, DASHSCOPE_API_KEY, or API_KEY."
    )


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--collection")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--reranker-api-url",
        default=os.getenv("RERANKER_API_URL", DEFAULT_DASHSCOPE_RERANK_URL),
    )
    parser.add_argument(
        "--reranker-model",
        default=os.getenv("RERANKER_MODEL_NAME", "qwen3-rerank"),
    )
    parser.add_argument(
        "--reranker-key-env",
        default="RERANKER_API_KEY",
        help="Environment variable containing the key; the key is never serialized.",
    )
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
    rerank_latencies: list[float] = []
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
                # Ask for the complete candidate ordering, then apply the
                # evaluation cutoff locally. This exposes gold evidence that
                # the reranker pushes just below Top-K.
                top_n=args.candidate_k,
                request_format=args.reranker_format,
            ),
            timeout=args.reranker_timeout,
        )
        ranking = _parse_rerank_results(rerank_response, len(candidates))
        rerank_latency = time.perf_counter() - rerank_started
        rerank_latencies.append(rerank_latency)
        reranked_candidates = _rerank_hits(candidates, ranking)
        reranked_hits = reranked_candidates[: args.top_k]

        results.append(
            {
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
                    case, reranked_hits, retrieve_latency + rerank_latency
                ),
                "rerank_latency_seconds": round(rerank_latency, 3),
            }
        )
        print(
            f"{case['id']} complete: retrieve={retrieve_latency:.3f}s "
            f"rerank={rerank_latency:.3f}s"
        )

    dense_summary = _summarize(results, "dense")
    reranked_summary = _summarize(results, "reranked")
    added_latency = (
        reranked_summary["mean_latency_seconds"]
        - dense_summary["mean_latency_seconds"]
    )
    acceptance = _acceptance_decision(
        dense_summary,
        reranked_summary,
        added_latency_seconds=added_latency,
        min_mrr=args.min_mrr,
        min_ndcg=args.min_ndcg,
        max_added_latency_seconds=args.max_added_latency,
    )
    report = {
        "schema_version": "1.0",
        "experiment_id": "scholarlens-reranker-ab-v1",
        "dataset_id": dataset["dataset_id"],
        "annotation_status": dataset["annotation_status"],
        "collection_id": collection,
        "corpus_validation": corpus_validation,
        "configuration": {
            "candidate_k": args.candidate_k,
            "top_k": args.top_k,
            "reranker_model": args.reranker_model,
            "reranker_host": urlparse(args.reranker_api_url).netloc,
            "reranker_request_format": args.reranker_format,
            "api_key_source": key_source,
        },
        "summary": {
            "dense": dense_summary,
            "reranked": reranked_summary,
            "delta": {
                "strict_evidence_hit_rate": (
                    reranked_summary["strict_evidence_hit_rate"]
                    - dense_summary["strict_evidence_hit_rate"]
                ),
                "evidence_set_mrr": (
                    reranked_summary["evidence_set_mrr"]
                    - dense_summary["evidence_set_mrr"]
                ),
                "mean_ndcg": (
                    reranked_summary["mean_ndcg"] - dense_summary["mean_ndcg"]
                ),
                "mean_latency_seconds": (
                    added_latency
                ),
            },
            "paired_evidence_set_mrr": _paired_outcomes(
                results, "evidence_set_reciprocal_rank"
            ),
            "paired_ndcg": _paired_outcomes(results, "ndcg"),
            "mean_rerank_latency_seconds": statistics.mean(rerank_latencies),
            "median_rerank_latency_seconds": statistics.median(rerank_latencies),
        },
        "acceptance": acceptance,
        "results": results,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(
        json.dumps(
            {"summary": report["summary"], "acceptance": acceptance},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
