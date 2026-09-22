"""Evaluate strict evidence retrieval against a human-reviewable gold set."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _post_json(url: str, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _gold_ids(case: dict[str, Any]) -> list[list[str]]:
    return [
        [str(item["chunk_id"]) for item in evidence_set]
        for evidence_set in case.get("gold_evidence_sets", [])
    ]


def _validate_dataset(dataset: dict[str, Any]) -> None:
    case_ids: set[str] = set()
    for case in dataset.get("cases", []):
        case_id = str(case.get("id", ""))
        if not case_id or case_id in case_ids:
            raise ValueError(f"Missing or duplicate case id: {case_id!r}")
        case_ids.add(case_id)
        evidence_sets = _gold_ids(case)
        if case.get("answerable") and not evidence_sets:
            raise ValueError(f"{case_id}: answerable case has no gold evidence")
        if not case.get("answerable") and evidence_sets:
            raise ValueError(f"{case_id}: unanswerable case must not have gold evidence")
        for evidence_set in evidence_sets:
            if not evidence_set or len(evidence_set) != len(set(evidence_set)):
                raise ValueError(f"{case_id}: empty or duplicate evidence set")


def _validate_gold_against_corpus(
    dataset: dict[str, Any], corpus: Path
) -> dict[str, Any]:
    """Rebuild chunks and ensure every gold reference still matches the corpus."""

    try:
        from scripts.reindex_structured_dataset import ChunkingConfig, _chunk_document
    except ModuleNotFoundError:  # Direct execution from the scripts directory.
        from reindex_structured_dataset import ChunkingConfig, _chunk_document

    paths = [corpus] if corpus.is_file() else sorted(corpus.rglob("document.json"))
    if not paths:
        raise ValueError(f"No document.json artifacts found under {corpus}")

    chunks_by_id: dict[str, tuple[dict[str, Any], str]] = {}
    duplicate_ids: list[str] = []
    config = ChunkingConfig(target_tokens=600, max_tokens=900)
    for path in paths:
        document, chunks = _chunk_document(path, config)
        for chunk in chunks:
            chunk_id = str(chunk["chunk_id"])
            if chunk_id in chunks_by_id:
                duplicate_ids.append(chunk_id)
            chunks_by_id[chunk_id] = (chunk, document.filename)

    missing_ids: list[str] = []
    metadata_mismatches: list[dict[str, Any]] = []
    reference_count = 0
    for case in dataset.get("cases", []):
        for evidence_set in case.get("gold_evidence_sets", []):
            for evidence in evidence_set:
                reference_count += 1
                chunk_id = str(evidence["chunk_id"])
                actual_entry = chunks_by_id.get(chunk_id)
                if actual_entry is None:
                    missing_ids.append(chunk_id)
                    continue
                actual, actual_filename = actual_entry
                expected_fields = {
                    "filename": evidence.get("filename"),
                    "page_start": evidence.get("page_start"),
                    "content_type": evidence.get("content_type"),
                    "section_path": evidence.get("section_path"),
                }
                actual_fields = {
                    "filename": actual_filename,
                    "page_start": actual.get("page_start"),
                    "content_type": actual.get("content_type"),
                    "section_path": actual.get("section_path"),
                }
                differences = {
                    field: {"expected": expected, "actual": actual_fields[field]}
                    for field, expected in expected_fields.items()
                    if expected is not None and expected != actual_fields[field]
                }
                if differences:
                    metadata_mismatches.append(
                        {
                            "case_id": case["id"],
                            "chunk_id": chunk_id,
                            "differences": differences,
                        }
                    )

    validation = {
        # Keep reports portable and safe for public repositories. The caller's
        # absolute workstation path is not part of the evaluation contract.
        "corpus": corpus.name,
        "document_count": len(paths),
        "chunk_count": len(chunks_by_id),
        "gold_reference_count": reference_count,
        "missing_ids": sorted(set(missing_ids)),
        "duplicate_chunk_ids": sorted(set(duplicate_ids)),
        "metadata_mismatches": metadata_mismatches,
    }
    if missing_ids or duplicate_ids or metadata_mismatches:
        raise ValueError(
            "Gold/corpus validation failed:\n"
            + json.dumps(validation, ensure_ascii=False, indent=2)
        )
    return validation


def _best_set_metrics(
    retrieved_ids: list[str], evidence_sets: list[list[str]]
) -> tuple[bool, float, float]:
    ranks = {chunk_id: rank for rank, chunk_id in enumerate(retrieved_ids, 1)}
    strict_hit = False
    best_recall = 0.0
    best_set_rr = 0.0
    for evidence_set in evidence_sets:
        present = [ranks[chunk_id] for chunk_id in evidence_set if chunk_id in ranks]
        best_recall = max(best_recall, len(present) / len(evidence_set))
        if len(present) == len(evidence_set):
            strict_hit = True
            best_set_rr = max(best_set_rr, 1.0 / max(present))
    return strict_hit, best_recall, best_set_rr


def _ndcg(retrieved_ids: list[str], evidence_sets: list[list[str]]) -> float:
    relevant = {chunk_id for evidence_set in evidence_sets for chunk_id in evidence_set}
    if not relevant:
        return 0.0
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(retrieved_ids, 1)
        if chunk_id in relevant
    )
    ideal_count = min(len(relevant), len(retrieved_ids))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / idcg if idcg else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--collection")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Optional document.json directory used to detect stale gold chunk references.",
    )
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    _validate_dataset(dataset)
    corpus_validation = (
        _validate_gold_against_corpus(dataset, args.corpus) if args.corpus else None
    )
    collection = args.collection or dataset.get("collection_id")
    if not collection:
        raise SystemExit("No collection id supplied")

    results: list[dict[str, Any]] = []
    for case in dataset["cases"]:
        started = time.perf_counter()
        response = _post_json(
            f"{args.api_url}/search",
            {
                "collection_name": collection,
                "query_text": case["question"],
                "top_k": args.top_k,
            },
        )
        hits = response.get("results", [])
        retrieved_ids = [
            str((hit.get("metadata") or {}).get("chunk_id", "")) for hit in hits
        ]
        evidence_sets = _gold_ids(case)
        strict_hit, best_recall, set_rr = _best_set_metrics(
            retrieved_ids, evidence_sets
        )
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "answerable": case["answerable"],
                "strict_evidence_hit": strict_hit if case["answerable"] else None,
                "best_evidence_set_recall": best_recall if case["answerable"] else None,
                "evidence_set_reciprocal_rank": set_rr if case["answerable"] else None,
                "ndcg": _ndcg(retrieved_ids, evidence_sets) if case["answerable"] else None,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "max_score": max((float(hit.get("score", 0.0)) for hit in hits), default=0.0),
                "hits": [
                    {
                        "rank": rank,
                        "chunk_id": (hit.get("metadata") or {}).get("chunk_id"),
                        "filename": hit.get("filename"),
                        "page_start": (hit.get("metadata") or {}).get("page_start"),
                        "content_type": (hit.get("metadata") or {}).get("content_type"),
                        "score": round(float(hit.get("score", 0.0)), 6),
                    }
                    for rank, hit in enumerate(hits, 1)
                ],
            }
        )
        print(f"{case['id']} complete")

    answerable = [item for item in results if item["answerable"]]
    unanswerable = [item for item in results if not item["answerable"]]
    latencies = [item["latency_seconds"] for item in results]
    report = {
        "schema_version": "1.0",
        "dataset_id": dataset["dataset_id"],
        "annotation_status": dataset["annotation_status"],
        "collection_id": collection,
        "top_k": args.top_k,
        "corpus_validation": corpus_validation,
        "summary": {
            "case_count": len(results),
            "answerable_cases": len(answerable),
            "unanswerable_cases": len(unanswerable),
            "strict_evidence_hit_rate": sum(
                bool(item["strict_evidence_hit"]) for item in answerable
            ) / len(answerable),
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
                item["id"]: item["max_score"] for item in unanswerable
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
