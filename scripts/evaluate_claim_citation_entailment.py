"""Validate and run the claim-to-citation entailment development benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_answer_citations import (  # noqa: E402
    _build_claim_evidence_bundles,
    _judge_answer,
)

REQUIRED_SCENARIOS = {
    "correct_single_citation",
    "wrong_citation_correct_evidence_elsewhere",
    "grouped_citation_one_source_supports",
    "uncited_factual_claim",
    "invalid_citation_only",
    "cited_evidence_contradicts_claim",
    "same_source_supports_one_claim_only",
}


def _validate_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    if dataset.get("split") not in {"development", "held_out"}:
        raise ValueError("claim entailment dataset must use development or held_out split")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset requires a non-empty cases array")
    case_ids: set[str] = set()
    scenarios: set[str] = set()
    claim_count = 0
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each dataset case must be an object")
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id in case_ids:
            raise ValueError("dataset case ids must be non-empty and unique")
        case_ids.add(case_id)
        scenarios.add(str(case.get("scenario", "")))
        sources = case.get("sources")
        if not isinstance(sources, list):
            raise ValueError(f"{case_id}: sources must be an array")
        for index, source in enumerate(sources, 1):
            if not isinstance(source, dict) or source.get("source_id") != f"S{index}":
                raise ValueError(f"{case_id}: source ids must match display order")
            if not str(source.get("chunk_text", "")).strip():
                raise ValueError(f"{case_id}: every source requires chunk_text")
        bundles = _build_claim_evidence_bundles(str(case.get("answer", "")), sources)
        expected = case.get("expected_claims")
        if not isinstance(expected, list) or len(expected) != len(bundles):
            raise ValueError(f"{case_id}: expected_claims must match parsed claims")
        for expected_item, bundle in zip(expected, bundles):
            if not isinstance(expected_item, dict):
                raise ValueError(f"{case_id}: expected claims must be objects")
            if expected_item.get("id") != bundle["id"]:
                raise ValueError(f"{case_id}: expected claim ids must match parsed order")
            if expected_item.get("citation_numbers") != bundle["citation_numbers"]:
                raise ValueError(f"{case_id}: expected citation numbers do not match answer")
            evidence_source_ids = [
                str(item.get("source_id", "")) for item in bundle["evidence"]
            ]
            if expected_item.get("evidence_source_ids") != evidence_source_ids:
                raise ValueError(f"{case_id}: expected evidence binding is incorrect")
            if not isinstance(expected_item.get("supported"), bool):
                raise ValueError(f"{case_id}: supported must be boolean")
        claim_count += len(bundles)
    missing_scenarios = REQUIRED_SCENARIOS - scenarios
    if missing_scenarios:
        raise ValueError(
            "dataset is missing required scenarios: "
            + ", ".join(sorted(missing_scenarios))
        )
    return {
        "dataset_id": dataset.get("dataset_id"),
        "case_count": len(cases),
        "claim_count": claim_count,
        "scenario_count": len(scenarios),
    }


def _validate_run_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    if dataset.get("split") == "held_out":
        from scripts.build_claim_citation_heldout_v5 import _assert_executable

        _assert_executable(dataset)
    return _validate_dataset(dataset)


def _score_case(case: dict[str, Any], judgement: dict[str, Any]) -> dict[str, Any]:
    expected = {
        str(item["id"]): bool(item["supported"])
        for item in case["expected_claims"]
    }
    predicted = {
        str(item["id"]): bool(item["supported"])
        for item in judgement["claim_support"]
    }
    if set(expected) != set(predicted):
        raise ValueError(f"{case['id']}: predicted claim ids do not match dataset")
    claims = [
        {
            "id": claim_id,
            "expected_supported": expected[claim_id],
            "predicted_supported": predicted[claim_id],
            "correct": expected[claim_id] == predicted[claim_id],
        }
        for claim_id in expected
    ]
    return {
        "case_id": case["id"],
        "scenario": case["scenario"],
        "claims": claims,
        "exact_match": all(item["correct"] for item in claims),
    }


def _summarize(scored_cases: list[dict[str, Any]]) -> dict[str, Any]:
    claims = [claim for case in scored_cases for claim in case["claims"]]
    if not claims:
        raise ValueError("at least one scored claim is required")
    unsupported = [item for item in claims if not item["expected_supported"]]
    supported = [item for item in claims if item["expected_supported"]]
    return {
        "case_count": len(scored_cases),
        "claim_count": len(claims),
        "claim_decision_accuracy": statistics.mean(item["correct"] for item in claims),
        "case_exact_match_rate": statistics.mean(
            item["exact_match"] for item in scored_cases
        ),
        "unsupported_claim_recall": (
            statistics.mean(not item["predicted_supported"] for item in unsupported)
            if unsupported
            else 1.0
        ),
        "supported_claim_recall": (
            statistics.mean(item["predicted_supported"] for item in supported)
            if supported
            else 1.0
        ),
    }


def _acceptance(summary: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "claim_decision_accuracy": (summary["claim_decision_accuracy"], 1.0),
        "case_exact_match_rate": (summary["case_exact_match_rate"], 1.0),
        "unsupported_claim_recall": (summary["unsupported_claim_recall"], 1.0),
        "supported_claim_recall": (summary["supported_claim_recall"], 1.0),
    }
    rendered = {
        name: {"actual": actual, "operator": ">=", "threshold": threshold, "passed": actual >= threshold}
        for name, (actual, threshold) in checks.items()
    }
    return {"passed": all(item["passed"] for item in rendered.values()), "checks": rendered}


async def _run_live(
    dataset: dict[str, Any],
    *,
    client: AsyncOpenAI,
    model_name: str,
) -> dict[str, Any]:
    results = []
    scored_cases = []
    for case in dataset["cases"]:
        judgement = await _judge_answer(
            client=client,
            model_name=model_name,
            question=str(case["question"]),
            answer=str(case["answer"]),
            expected_answer=str(case["expected_answer"]),
            required_concepts=[str(item) for item in case["required_concepts"]],
            sources=case["sources"],
        )
        score = _score_case(case, judgement)
        scored_cases.append(score)
        results.append(
            {
                **score,
                "claim_evidence": [
                    {
                        "id": item["id"],
                        "citation_numbers": item["citation_numbers"],
                        "valid_citation_numbers": item["valid_citation_numbers"],
                        "invalid_citation_numbers": item["invalid_citation_numbers"],
                        "evidence_source_ids": [
                            source.get("source_id") for source in item["evidence"]
                        ],
                    }
                    for item in _build_claim_evidence_bundles(
                        str(case["answer"]), case["sources"]
                    )
                ],
                "judgement": judgement,
            }
        )
        print(f"{case['id']}: {'PASS' if score['exact_match'] else 'FAIL'}")
    summary = _summarize(scored_cases)
    return {
        "schema_version": "1.0",
        "experiment_id": "scholarlens-claim-citation-entailment-dev-v1",
        "dataset_id": dataset["dataset_id"],
        "dataset_split": dataset["split"],
        "configuration": {
            "model_name": model_name,
            "judge": "same_model_structured_development_judge",
        },
        "summary": summary,
        "acceptance": _acceptance(summary),
        "results": results,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = [
        f"| {item['case_id']} | {item['scenario']} | {'PASS' if item['exact_match'] else 'FAIL'} |"
        for item in report["results"]
    ]
    return "\n".join(
        [
            "# Claim-to-citation Entailment Development Evaluation",
            "",
            f"- Dataset: `{report['dataset_id']}`",
            f"- Model: `{report['configuration']['model_name']}`",
            f"- Acceptance: **{'PASS' if report['acceptance']['passed'] else 'FAIL'}**",
            "",
            "## Summary",
            "",
            f"- Claim decision accuracy: {summary['claim_decision_accuracy']:.2%}",
            f"- Case exact-match rate: {summary['case_exact_match_rate']:.2%}",
            f"- Unsupported-claim recall: {summary['unsupported_claim_recall']:.2%}",
            f"- Supported-claim recall: {summary['supported_claim_recall']:.2%}",
            "",
            "## Cases",
            "",
            "| Case | Scenario | Result |",
            "|---|---|---|",
            *rows,
            "",
            "## Scope",
            "",
            "This is a synthetic development contract set, not a held-out release benchmark.",
            "Each claim is evaluated only against the source snippets addressed by its own citations.",
            "",
        ]
    )


def _write_report(report: dict[str, Any], output: Path | None, markdown_output: Path | None) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_output:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(_render_markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dataset",
        nargs="?",
        type=Path,
        default=PROJECT_ROOT / "docs/evaluation/claim-citation-entailment-dev-v1.json",
    )
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--model-api-url")
    parser.add_argument("--model-name")
    parser.add_argument("--api-key-env", default="API_KEY")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    validation = _validate_run_dataset(dataset)
    if args.validate_only:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return 0

    load_dotenv(args.env_file, override=False)
    api_key = os.getenv(args.api_key_env, "").strip()
    model_api_url = args.model_api_url or os.getenv("MODEL_URL", "").strip()
    model_name = args.model_name or os.getenv("MODEL_NAME", "").strip()
    if not api_key or not model_api_url or not model_name:
        parser.error("API_KEY, MODEL_URL, and MODEL_NAME must be configured")
    client = AsyncOpenAI(api_key=api_key, base_url=model_api_url)
    report = asyncio.run(_run_live(dataset, client=client, model_name=model_name))
    report["configuration"]["model_host"] = urlparse(model_api_url).netloc
    report["configuration"]["api_key_source"] = args.api_key_env
    report["dataset_validation"] = validation
    _write_report(report, args.output, args.markdown_output)
    print(json.dumps({"summary": report["summary"], "acceptance": report["acceptance"]}, indent=2))
    return 0 if report["acceptance"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
