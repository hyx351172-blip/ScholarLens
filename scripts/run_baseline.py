"""Run the ScholarLens v1 retrieval and answer baseline against local services."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

COLLECTION = os.getenv("BASELINE_COLLECTION", "kb_1787804989594")
CHAT_URL = os.getenv("CHAT_URL", "http://localhost:8501/chat")

CASES = [
    {"id": "Q01", "type": "fact", "question": "CharacterEval 数据集包含多少段多轮对话、多少个样本和多少个角色？", "expected_files": ["2024.acl-long.638.pdf"]},
    {"id": "Q02", "type": "understanding", "question": "CharacterEval 主要从哪些维度评估角色扮演对话智能体？", "expected_files": ["2024.acl-long.638.pdf"]},
    {"id": "Q03", "type": "fact", "question": "GAAP 的全称是什么，它要保护的核心对象是什么？", "expected_files": ["2604.19657v1.pdf"]},
    {"id": "Q04", "type": "understanding", "question": "GAAP 如何在不信任 AI 模型和用户提示的情况下提供确定性的机密性保证？", "expected_files": ["2604.19657v1.pdf"]},
    {"id": "Q05", "type": "fact", "question": "MemLineage 为每条智能体记忆附加了哪两类信息？", "expected_files": ["2605.14421v1.pdf"]},
    {"id": "Q06", "type": "understanding", "question": "MemLineage 的 sensitive-action gate 在什么情况下会拒绝执行敏感动作？", "expected_files": ["2605.14421v1.pdf"]},
    {"id": "Q07", "type": "fact", "question": "MAP-Graph 解决共享记忆中的什么安全问题？", "expected_files": ["2608.10509v1.pdf"]},
    {"id": "Q08", "type": "understanding", "question": "MAP-Graph 为什么要区分硬授权和分级信任？", "expected_files": ["2608.10509v1.pdf"]},
    {"id": "Q09", "type": "comparison", "question": "比较 MemLineage 与 MAP-Graph：两者分别面向什么记忆场景，又如何利用 provenance 或 lineage？", "expected_files": ["2605.14421v1.pdf", "2608.10509v1.pdf"]},
    {"id": "Q10", "type": "unanswerable", "question": "这四篇论文分别报告了多少 GPU 小时和训练耗电量？请给出精确数字。", "expected_files": []},
]


def post_json(url: str, payload: dict, timeout: int = 180) -> dict:
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


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    api_key = os.getenv("API_KEY")
    api_url = os.getenv("MODEL_URL")
    model_name = os.getenv("MODEL_NAME")
    if not all((api_key, api_url, model_name)):
        print("Missing API_KEY, MODEL_URL, or MODEL_NAME in .env", file=sys.stderr)
        return 2

    selected_ids = {
        item.strip()
        for item in os.getenv("BASELINE_CASE_IDS", "").split(",")
        if item.strip()
    }
    selected_cases = [case for case in CASES if not selected_ids or case["id"] in selected_ids]

    results = []
    for case in selected_cases:
        started = time.perf_counter()
        response = post_json(
            CHAT_URL,
            {
                "query": case["question"],
                "collection_name": COLLECTION,
                "llm_config": {"api_url": api_url, "api_key": api_key, "model_name": model_name, "temperature": 0.0, "max_tokens": 1200},
                "top_k": 10,
                "score_threshold": 0.3,
                "use_reranker": False,
                "stream": False,
                "return_source": True,
                "history": [],
            },
        )
        sources = response.get("sources") or []
        retrieved_files = list(dict.fromkeys(source.get("filename") for source in sources))
        expected = set(case["expected_files"])
        retrieval_hit = expected.issubset(set(retrieved_files)) if expected else None
        results.append({
            **case,
            "retrieval_hit": retrieval_hit,
            "retrieved_files": retrieved_files,
            "top_sources": [{"filename": source.get("filename"), "page": (source.get("metadata") or {}).get("page_start"), "chunk_index": (source.get("metadata") or {}).get("chunk_index"), "score": round(source.get("score", 0.0), 6)} for source in sources[:5]],
            "answer": response.get("answer", ""),
            "metadata": response.get("metadata", {}),
            "client_elapsed": round(time.perf_counter() - started, 3),
        })
        print(f"{case['id']} complete", file=sys.stderr)

    print(json.dumps({"collection": COLLECTION, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
