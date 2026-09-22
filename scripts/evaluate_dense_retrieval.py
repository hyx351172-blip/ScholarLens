"""Run a document-level dense-retrieval smoke baseline for Chunker v2."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


CASES = [
    {
        "id": "R01",
        "question": "What mechanism lets the Transformer model sequence dependencies without recurrence or convolution?",
        "expected_files": ["1706.03762_attention-is-all-you-need.pdf"],
    },
    {
        "id": "R02",
        "question": "What two unsupervised prediction tasks are used to pre-train BERT?",
        "expected_files": ["1810.04805_bert.pdf"],
    },
    {
        "id": "R03",
        "question": "How does LoRA adapt a pretrained model while keeping the original model weights frozen?",
        "expected_files": ["2106.09685_lora.pdf"],
    },
    {
        "id": "R04",
        "question": "How does CLIP use natural language supervision for zero-shot visual recognition?",
        "expected_files": ["2103.00020_clip.pdf"],
    },
    {
        "id": "R05",
        "question": "What IO bottleneck does FlashAttention address and why is its attention computation exact?",
        "expected_files": ["2205.14135_flashattention.pdf"],
    },
    {
        "id": "R06",
        "question": "Why does Mamba have linear sequence complexity and what is selective about its state space model?",
        "expected_files": ["2312.00752_mamba.pdf"],
    },
    {
        "id": "R07",
        "question": "What tokenizer-free OCR architecture does Donut use?",
        "expected_files": ["2111.15664_donut.pdf"],
    },
    {
        "id": "R08",
        "question": "What is Nougat designed to convert scientific PDF documents into?",
        "expected_files": ["2308.13418_nougat.pdf"],
    },
    {
        "id": "R09",
        "question": "What unified text and image masking objectives are used by LayoutLMv3 for document AI?",
        "expected_files": ["2204.08387_layoutlmv3.pdf"],
    },
    {
        "id": "R10",
        "question": "Compare BERT bidirectional pretraining with GPT-3 in-context few-shot learning.",
        "expected_files": [
            "1810.04805_bert.pdf",
            "2005.14165_language-models-are-few-shot-learners.pdf",
        ],
    },
]


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


def _first_rank(filenames: list[str], expected: str) -> int | None:
    for rank, filename in enumerate(filenames, 1):
        if filename == expected:
            return rank
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("collection")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for case in CASES:
        started = time.perf_counter()
        response = _post_json(
            f"{args.api_url}/search",
            {
                "collection_name": args.collection,
                "query_text": case["question"],
                "top_k": args.top_k,
            },
        )
        hits = response.get("results", [])
        filenames = [str(hit.get("filename")) for hit in hits]
        first_ranks = {
            expected: _first_rank(filenames, expected)
            for expected in case["expected_files"]
        }
        results.append(
            {
                **case,
                "all_expected_at_10": all(rank is not None for rank in first_ranks.values()),
                "any_expected_at_1": any(rank == 1 for rank in first_ranks.values()),
                "first_ranks": first_ranks,
                "reciprocal_rank": max(
                    (1.0 / rank for rank in first_ranks.values() if rank is not None),
                    default=0.0,
                ),
                "latency_seconds": round(time.perf_counter() - started, 3),
                "top_hits": [
                    {
                        "rank": rank,
                        "filename": hit.get("filename"),
                        "score": round(float(hit.get("score", 0.0)), 6),
                        "chunk_id": (hit.get("metadata") or {}).get("chunk_id"),
                        "content_type": (hit.get("metadata") or {}).get("content_type"),
                        "page_start": (hit.get("metadata") or {}).get("page_start"),
                        "section_path": (hit.get("metadata") or {}).get("section_path"),
                    }
                    for rank, hit in enumerate(hits, 1)
                ],
            }
        )
        print(f"{case['id']} complete")

    latencies = [item["latency_seconds"] for item in results]
    report = {
        "schema_version": "1.0",
        "scope": "document-level dense retrieval smoke test; not strict evidence recall",
        "collection_id": args.collection,
        "top_k": args.top_k,
        "summary": {
            "case_count": len(results),
            "recall_at_10": sum(item["all_expected_at_10"] for item in results) / len(results),
            "hit_at_1": sum(item["any_expected_at_1"] for item in results) / len(results),
            "mrr": sum(item["reciprocal_rank"] for item in results) / len(results),
            "mean_latency_seconds": statistics.mean(latencies),
            "median_latency_seconds": statistics.median(latencies),
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
