"""Evaluate the production LLM query planner against the v3 development set.

The report deliberately excludes API keys and raw provider error payloads.  It
checks both planner structure/target preservation and the downstream evidence
retrieval produced by the generated plan.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.chat.multi_query_retrieval import (  # noqa: E402
    RetrievalPlan,
    create_query_plan,
    execute_retrieval_plan,
)
from scripts.evaluate_evidence_retrieval import (  # noqa: E402
    _best_set_metrics,
    _gold_ids,
    _ndcg,
    _post_json,
    _validate_dataset,
    _validate_gold_against_corpus,
)
from scripts.evaluate_multi_query_coverage import _validate_query_plans  # noqa: E402


def _normalize_target(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _match_expected_targets(
    expected_ids: list[str],
    plan: RetrievalPlan,
) -> tuple[dict[str, str], list[str]]:
    """Match expected target ids to distinct generated subqueries."""

    generated = {
        item.query_id: _normalize_target(
            f"{item.query_id} {item.target} {item.query}"
        )
        for item in plan.subqueries
    }
    matches: dict[str, str] = {}
    used_query_ids: set[str] = set()
    for expected_id in expected_ids:
        needle = _normalize_target(expected_id)
        for query_id, haystack in generated.items():
            if query_id not in used_query_ids and needle and needle in haystack:
                matches[expected_id] = query_id
                used_query_ids.add(query_id)
                break
    missing = [item for item in expected_ids if item not in matches]
    return matches, missing


def _evidence_metrics(
    hits: list[dict[str, Any]],
    evidence_sets: list[list[str]],
) -> dict[str, Any]:
    retrieved_ids = [
        str((hit.get("metadata") or {}).get("chunk_id", "")) for hit in hits
    ]
    return _evidence_metrics_from_ids(retrieved_ids, evidence_sets)


def _evidence_metrics_from_ids(
    retrieved_ids: list[str],
    evidence_sets: list[list[str]],
) -> dict[str, Any]:
    """Score persisted retrieval IDs without rerunning a model or vector store."""

    strict_hit, recall, reciprocal_rank = _best_set_metrics(
        retrieved_ids, evidence_sets
    )
    return {
        "strict_evidence_hit": strict_hit,
        "best_evidence_set_recall": recall,
        "evidence_set_reciprocal_rank": reciprocal_rank,
        "ndcg": _ndcg(retrieved_ids, evidence_sets),
        "retrieved_chunk_ids": retrieved_ids,
    }


def _replay_report(
    dataset: dict[str, Any],
    previous_report: dict[str, Any],
    *,
    source_path: Path,
    min_valid_plan_rate: float,
    min_complete_target_rate: float,
    min_strict_hit_rate: float,
    max_mean_planner_latency: float,
) -> dict[str, Any]:
    """Re-score one persisted live run after a human-reviewed Gold change."""

    cases_by_id = {str(case["id"]): case for case in dataset["cases"]}
    previous_results = previous_report.get("results")
    if not isinstance(previous_results, list) or not previous_results:
        raise ValueError("replay report contains no persisted results")

    results: list[dict[str, Any]] = []
    for previous in previous_results:
        case_id = str(previous.get("case_id", ""))
        case = cases_by_id.get(case_id)
        if not case:
            raise ValueError(f"replay result references unknown case: {case_id}")
        retrieved_ids = list(
            (previous.get("retrieval") or {}).get("retrieved_chunk_ids") or []
        )
        if not retrieved_ids:
            raise ValueError(f"replay result has no retrieved chunks: {case_id}")
        replayed = dict(previous)
        replayed["retrieval"] = _evidence_metrics_from_ids(
            [str(item) for item in retrieved_ids], _gold_ids(case)
        )
        replayed["evaluation_mode"] = "persisted_retrieval_replay"
        results.append(replayed)

    expected_case_ids = set(cases_by_id)
    observed_case_ids = {str(item["case_id"]) for item in results}
    if observed_case_ids != expected_case_ids:
        raise ValueError("replay report does not cover every dataset case exactly")

    summary = _summarize(results)
    acceptance = _acceptance_decision(
        summary,
        min_valid_plan_rate=min_valid_plan_rate,
        min_complete_target_rate=min_complete_target_rate,
        min_strict_hit_rate=min_strict_hit_rate,
        max_mean_planner_latency=max_mean_planner_latency,
    )
    configuration = dict(previous_report.get("configuration") or {})
    configuration["evaluation_mode"] = "persisted_retrieval_replay"
    configuration["source_report"] = source_path.name
    return {
        "schema_version": "1.0",
        "experiment_id": "scholarlens-live-query-planner-v1-gold-replay",
        "dataset_id": dataset["dataset_id"],
        "dataset_split": dataset.get("split"),
        "annotation_status": dataset.get("annotation_status"),
        "collection_id": previous_report.get("collection_id"),
        "corpus_validation": previous_report.get("corpus_validation"),
        "configuration": configuration,
        "summary": summary,
        "acceptance": acceptance,
        "results": results,
        "limitations": [
            "Re-scores persisted retrieval IDs; it does not call the planner or vector store again.",
            "A fresh live rerun is still required after local Milvus is restored.",
        ],
    }


def _acceptance_decision(
    summary: dict[str, Any],
    *,
    min_valid_plan_rate: float,
    min_complete_target_rate: float,
    min_strict_hit_rate: float,
    max_mean_planner_latency: float,
) -> dict[str, Any]:
    checks = {
        "valid_plan_rate": {
            "actual": summary["valid_plan_rate"],
            "operator": ">=",
            "threshold": min_valid_plan_rate,
        },
        "complete_target_rate": {
            "actual": summary["complete_target_rate"],
            "operator": ">=",
            "threshold": min_complete_target_rate,
        },
        "strict_evidence_hit_rate": {
            "actual": summary["strict_evidence_hit_rate"],
            "operator": ">=",
            "threshold": min_strict_hit_rate,
        },
        "mean_planner_latency_seconds": {
            "actual": summary["mean_planner_latency_seconds"],
            "operator": "<=",
            "threshold": max_mean_planner_latency,
        },
    }
    checks["valid_plan_rate"]["passed"] = (
        checks["valid_plan_rate"]["actual"] >= min_valid_plan_rate
    )
    checks["complete_target_rate"]["passed"] = (
        checks["complete_target_rate"]["actual"] >= min_complete_target_rate
    )
    checks["strict_evidence_hit_rate"]["passed"] = (
        checks["strict_evidence_hit_rate"]["actual"] >= min_strict_hit_rate
    )
    checks["mean_planner_latency_seconds"]["passed"] = (
        checks["mean_planner_latency_seconds"]["actual"]
        <= max_mean_planner_latency
    )
    return {
        "passed": all(bool(item["passed"]) for item in checks.values()),
        "checks": checks,
    }


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("at least one planner result is required")
    expected_target_count = sum(len(item["expected_target_ids"]) for item in results)
    matched_target_count = sum(len(item["target_matches"]) for item in results)
    fallback_reasons = Counter(
        str(item["plan"].get("fallback_reason"))
        for item in results
        if item["plan"].get("fallback_reason")
    )
    return {
        "run_count": len(results),
        "valid_plan_rate": sum(bool(item["valid_plan"]) for item in results)
        / len(results),
        "target_coverage_rate": matched_target_count / expected_target_count,
        "complete_target_rate": sum(
            not item["missing_target_ids"] for item in results
        )
        / len(results),
        "strict_evidence_hit_rate": sum(
            bool(item["retrieval"]["strict_evidence_hit"]) for item in results
        )
        / len(results),
        "mean_best_evidence_set_recall": statistics.mean(
            float(item["retrieval"]["best_evidence_set_recall"])
            for item in results
        ),
        "evidence_set_mrr": statistics.mean(
            float(item["retrieval"]["evidence_set_reciprocal_rank"])
            for item in results
        ),
        "mean_ndcg": statistics.mean(
            float(item["retrieval"]["ndcg"]) for item in results
        ),
        "mean_planner_latency_seconds": statistics.mean(
            float(item["planner_latency_seconds"]) for item in results
        ),
        "median_planner_latency_seconds": statistics.median(
            float(item["planner_latency_seconds"]) for item in results
        ),
        "mean_retrieval_latency_seconds": statistics.mean(
            float(item["retrieval_latency_seconds"]) for item in results
        ),
        "mean_end_to_end_latency_seconds": statistics.mean(
            float(item["end_to_end_latency_seconds"]) for item in results
        ),
        "fallback_reasons": dict(sorted(fallback_reasons.items())),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    acceptance = report["acceptance"]
    evaluation_mode = report["configuration"].get("evaluation_mode", "live")
    scope_statement = (
        "This is a persisted-retrieval replay after a human-reviewed Gold change; "
        "it is not a fresh provider or vector-store run."
        if evaluation_mode == "persisted_retrieval_replay"
        else "This is a development-set live-provider check."
    )
    rows = []
    for result in report["results"]:
        rows.append(
            "| {case_id} | {mode} | {targets} | {hit} | {planner:.3f}s | {total:.3f}s |".format(
                case_id=result["case_id"],
                mode=result["plan"]["mode"],
                targets="yes" if not result["missing_target_ids"] else "no",
                hit="yes" if result["retrieval"]["strict_evidence_hit"] else "no",
                planner=result["planner_latency_seconds"],
                total=result["end_to_end_latency_seconds"],
            )
        )
    return "\n".join(
        [
            "# Live Query Planner Evaluation",
            "",
            f"- Dataset: `{report['dataset_id']}`",
            f"- Model: `{report['configuration']['model_name']}`",
            f"- Evaluation mode: `{evaluation_mode}`",
            f"- Runs: {summary['run_count']}",
            f"- Acceptance: **{'PASS' if acceptance['passed'] else 'FAIL'}**",
            "",
            "## Summary",
            "",
            f"- Valid plan rate: {summary['valid_plan_rate']:.2%}",
            f"- Complete target rate: {summary['complete_target_rate']:.2%}",
            f"- Strict evidence Hit@10: {summary['strict_evidence_hit_rate']:.2%}",
            f"- Mean evidence recall: {summary['mean_best_evidence_set_recall']:.2%}",
            f"- Evidence-set MRR: {summary['evidence_set_mrr']:.4f}",
            f"- Mean nDCG: {summary['mean_ndcg']:.4f}",
            f"- Mean planner latency: {summary['mean_planner_latency_seconds']:.3f}s",
            f"- Mean retrieval latency: {summary['mean_retrieval_latency_seconds']:.3f}s",
            f"- Mean end-to-end latency: {summary['mean_end_to_end_latency_seconds']:.3f}s",
            "",
            "## Cases",
            "",
            "| Case | Plan mode | All targets | Strict evidence hit | Planner | Total |",
            "|---|---|---:|---:|---:|---:|",
            *rows,
            "",
            "## Scope",
            "",
            scope_statement,
            "It does not replace the fresh held-out gate.",
            "API keys and raw provider error payloads are not stored in this report.",
            *(f"- {item}" for item in report.get("limitations", [])),
            "",
        ]
    )


async def _evaluate_case(
    case: dict[str, Any],
    *,
    run_number: int,
    client: AsyncOpenAI,
    model_name: str,
    planner_timeout: float,
    max_subqueries: int,
    search_api_url: str,
    collection: str,
    candidate_k: int,
    top_k: int,
    rrf_k: int,
    original_reserve: int,
    per_target_reserve: int,
) -> dict[str, Any]:
    async def generate(messages: list[dict[str, str]]) -> str:
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0,
            max_tokens=600,
            stream=False,
        )
        return str(response.choices[0].message.content or "")

    started = time.perf_counter()
    planner_started = time.perf_counter()
    plan = await create_query_plan(
        str(case["question"]),
        generate,
        timeout_seconds=planner_timeout,
        max_subqueries=max_subqueries,
    )
    planner_latency = time.perf_counter() - planner_started

    expected_target_ids = [
        str(item["id"]) for item in case.get("retrieval_subqueries", [])
    ]
    target_matches, missing_targets = _match_expected_targets(
        expected_target_ids, plan
    )
    target_cardinality_valid = len(plan.subqueries) == len(expected_target_ids)

    async def retrieve(query: str) -> list[dict[str, Any]]:
        response = await asyncio.to_thread(
            _post_json,
            f"{search_api_url.rstrip('/')}/search",
            {
                "collection_name": collection,
                "query_text": query,
                "top_k": candidate_k,
            },
        )
        return response.get("results", [])

    retrieval_started = time.perf_counter()
    execution = await execute_retrieval_plan(
        original_query=str(case["question"]),
        plan=plan,
        retrieve=retrieve,
        top_k=top_k,
        rrf_k=rrf_k,
        original_reserve=original_reserve,
        per_target_reserve=per_target_reserve,
    )
    retrieval_latency = time.perf_counter() - retrieval_started
    evidence_metrics = _evidence_metrics(execution.documents, _gold_ids(case))

    return {
        "case_id": str(case["id"]),
        "run_number": run_number,
        "question": str(case["question"]),
        "valid_plan": (
            plan.is_multi_query
            and plan.fallback_reason is None
            and target_cardinality_valid
            and not missing_targets
        ),
        "target_cardinality_valid": target_cardinality_valid,
        "expected_target_ids": expected_target_ids,
        "target_matches": target_matches,
        "missing_target_ids": missing_targets,
        "plan": plan.to_dict(),
        "planner_latency_seconds": round(planner_latency, 4),
        "retrieval_latency_seconds": round(retrieval_latency, 4),
        "end_to_end_latency_seconds": round(time.perf_counter() - started, 4),
        "retrieval_mode": execution.trace["mode"],
        "retrieval_fallback_reason": execution.trace.get("fallback_reason"),
        "retrieval": evidence_metrics,
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    _validate_dataset(dataset)
    _validate_query_plans(dataset)
    collection = args.collection or dataset.get("collection_id")
    if not collection:
        raise ValueError("no collection id supplied")

    if args.replay_report:
        previous_report = json.loads(
            args.replay_report.read_text(encoding="utf-8")
        )
        return _replay_report(
            dataset,
            previous_report,
            source_path=args.replay_report,
            min_valid_plan_rate=args.min_valid_plan_rate,
            min_complete_target_rate=args.min_complete_target_rate,
            min_strict_hit_rate=args.min_strict_hit_rate,
            max_mean_planner_latency=args.max_mean_planner_latency,
        )

    api_key = os.getenv(args.api_key_env, "").strip()
    if not api_key:
        raise ValueError(
            f"{args.api_key_env} is missing; configure it in the selected .env file"
        )
    if not args.model_api_url or not args.model_name:
        raise ValueError("MODEL_URL and MODEL_NAME must be configured")

    corpus_validation = (
        _validate_gold_against_corpus(dataset, args.corpus)
        if args.corpus
        else None
    )
    client = AsyncOpenAI(api_key=api_key, base_url=args.model_api_url)
    results: list[dict[str, Any]] = []
    for run_number in range(1, args.runs_per_case + 1):
        for case in dataset["cases"]:
            result = await _evaluate_case(
                case,
                run_number=run_number,
                client=client,
                model_name=args.model_name,
                planner_timeout=args.planner_timeout,
                max_subqueries=args.max_subqueries,
                search_api_url=args.search_api_url,
                collection=str(collection),
                candidate_k=args.candidate_k,
                top_k=args.top_k,
                rrf_k=args.rrf_k,
                original_reserve=args.original_reserve,
                per_target_reserve=args.per_target_reserve,
            )
            results.append(result)
            print(
                f"{result['case_id']} run {run_number}: "
                f"plan={result['plan']['mode']} "
                f"targets={'ok' if not result['missing_target_ids'] else 'missing'} "
                f"hit={result['retrieval']['strict_evidence_hit']}"
            )

    summary = _summarize(results)
    acceptance = _acceptance_decision(
        summary,
        min_valid_plan_rate=args.min_valid_plan_rate,
        min_complete_target_rate=args.min_complete_target_rate,
        min_strict_hit_rate=args.min_strict_hit_rate,
        max_mean_planner_latency=args.max_mean_planner_latency,
    )
    return {
        "schema_version": "1.0",
        "experiment_id": "scholarlens-live-query-planner-v1",
        "dataset_id": dataset["dataset_id"],
        "dataset_split": dataset.get("split"),
        "annotation_status": dataset.get("annotation_status"),
        "collection_id": collection,
        "corpus_validation": corpus_validation,
        "configuration": {
            "model_name": args.model_name,
            "model_host": urlparse(args.model_api_url).netloc,
            "api_key_source": args.api_key_env,
            "runs_per_case": args.runs_per_case,
            "planner_timeout_seconds": args.planner_timeout,
            "candidate_k_per_query": args.candidate_k,
            "top_k": args.top_k,
            "rrf_k": args.rrf_k,
            "original_reserve": args.original_reserve,
            "per_target_reserve": args.per_target_reserve,
        },
        "summary": summary,
        "acceptance": acceptance,
        "results": results,
    }


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--replay-report",
        type=Path,
        help="Re-score persisted retrieved chunk IDs without external calls.",
    )
    parser.add_argument("--model-api-url", default=os.getenv("MODEL_URL", ""))
    parser.add_argument("--model-name", default=os.getenv("MODEL_NAME", ""))
    parser.add_argument("--api-key-env", default="API_KEY")
    parser.add_argument("--planner-timeout", type=float, default=12.0)
    parser.add_argument("--max-subqueries", type=int, default=3)
    parser.add_argument("--runs-per-case", type=int, default=1)
    parser.add_argument("--search-api-url", default="http://localhost:8000")
    parser.add_argument("--collection")
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--original-reserve", type=int, default=4)
    parser.add_argument("--per-target-reserve", type=int, default=2)
    parser.add_argument("--min-valid-plan-rate", type=float, default=1.0)
    parser.add_argument("--min-complete-target-rate", type=float, default=1.0)
    parser.add_argument("--min-strict-hit-rate", type=float, default=0.83)
    parser.add_argument("--max-mean-planner-latency", type=float, default=12.0)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    if args.env_file:
        load_dotenv(args.env_file, override=True)
        args.model_api_url = os.getenv("MODEL_URL", args.model_api_url)
        args.model_name = os.getenv("MODEL_NAME", args.model_name)
    if args.runs_per_case <= 0:
        parser.error("runs-per-case must be positive")
    if args.top_k <= 0 or args.candidate_k < args.top_k:
        parser.error("candidate-k must be greater than or equal to top-k")
    if args.max_subqueries not in (2, 3):
        parser.error("max-subqueries must be two or three")

    try:
        report = asyncio.run(_run(args))
    except ValueError as exc:
        parser.error(str(exc))
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "acceptance": report["acceptance"]}, ensure_ascii=False, indent=2))
    return 0 if report["acceptance"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
