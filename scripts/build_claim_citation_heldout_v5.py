"""Build the frozen, human-reviewable claim-citation Held-out v5 draft."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_answer_citations import _build_claim_evidence_bundles  # noqa: E402

DATASET_PATH = (
    PROJECT_ROOT
    / "docs/evaluation/claim-citation-entailment-heldout-v5.json"
)
REVIEW_PATH = (
    PROJECT_ROOT
    / "docs/evaluation/claim-citation-entailment-heldout-v5-review.md"
)
COLLECTION_ID = "kb_1790061860190"
PRIOR_GOLD_PATHS = (
    PROJECT_ROOT / "docs/evaluation/evidence-gold-v1.json",
    PROJECT_ROOT / "docs/evaluation/evidence-gold-v2-heldout.json",
    PROJECT_ROOT / "docs/evaluation/evidence-gold-v3-multi-query-dev.json",
    PROJECT_ROOT / "docs/evaluation/evidence-gold-v4-answer-citations-heldout.json",
)

SOURCE_REFS = {
    "lora_update": {
        "filename": "2106.09685_lora.pdf",
        "chunk_id": "e9a0d3128767db616085dc0f4e6e455e672e89af823e8ed1282793682787395a:paragraph:block_000053:part_0001",
    },
    "flash_io": {
        "filename": "2205.14135_flashattention.pdf",
        "chunk_id": "ca7f9fda10b90fc05dd291a3accc85e9c1a4a860b99b31928dab03ed3fcb14e4:paragraph:block_000013:part_0001",
    },
    "mamba_selective": {
        "filename": "2312.00752_mamba.pdf",
        "chunk_id": "adf70ed1803c85b1899dec3e21f3af0b124411439e8654b840ea65f7b9f52b2e:paragraph:block_000010:part_0001",
    },
    "layout_objectives": {
        "filename": "2204.08387_layoutlmv3.pdf",
        "chunk_id": "bd5395610755a49e6419c406e651906e688e7a0cfe155b3c43566469dfd641fe:paragraph:block_000029:part_0001",
    },
    "neuralode_adjoint": {
        "filename": "1806.07366_neural-ordinary-differential-equations.pdf",
        "chunk_id": "435299cc42b75f9ad43d9aa246c96d3d7bdcc3297aa57f419bdc571b9c25137c:paragraph:block_000021:part_0001",
    },
    "attention_multihead": {
        "filename": "1706.03762_attention-is-all-you-need.pdf",
        "chunk_id": "bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697:paragraph:block_000042:part_0001",
    },
    "donut_pretrain": {
        "filename": "2111.15664_donut.pdf",
        "chunk_id": "ad9c20523c37f53fc6d31ccb4c63dcc7b916c7340d6bb16033c9924ce70c7668:paragraph:block_000039:part_0001",
    },
    "donut_json": {
        "filename": "2111.15664_donut.pdf",
        "chunk_id": "ad9c20523c37f53fc6d31ccb4c63dcc7b916c7340d6bb16033c9924ce70c7668:paragraph:block_000046:part_0001",
    },
}

CASE_SPECS = [
    {
        "id": "CCHV5-01",
        "scenario": "correct_single_real_evidence",
        "question": "How does LoRA parameterize a weight update during adaptation?",
        "expected_answer": "LoRA freezes the pretrained weight and represents its update as a low-rank product BA.",
        "required_concepts": ["frozen pretrained weight", "low-rank update BA"],
        "answer": "LoRA freezes the pretrained weight and represents its update as the low-rank product BA [S1].",
        "source_aliases": ["lora_update"],
        "labels": [
            {
                "supported": True,
                "rationale": "S1 explicitly states that W0 is frozen and the update is represented as BA.",
            }
        ],
    },
    {
        "id": "CCHV5-02",
        "scenario": "wrong_citation_correct_real_evidence_elsewhere",
        "question": "What makes Mamba selective and how is it computed efficiently?",
        "expected_answer": "Mamba makes SSM parameters input-dependent and uses a hardware-aware recurrent scan without materializing the expanded state.",
        "required_concepts": ["input-dependent SSM parameters", "hardware-aware recurrent scan"],
        "answer": "Mamba makes SSM parameters input-dependent and computes them with a hardware-aware recurrent scan [S1].",
        "source_aliases": ["flash_io", "mamba_selective"],
        "labels": [
            {
                "supported": False,
                "rationale": "The claim cites S1 about FlashAttention; the matching Mamba evidence exists only in uncited S2.",
            }
        ],
    },
    {
        "id": "CCHV5-03",
        "scenario": "grouped_citations_one_real_source_supports",
        "question": "Which pre-training objectives does LayoutLMv3 combine?",
        "expected_answer": "LayoutLMv3 combines MLM, MIM, and word-patch alignment.",
        "required_concepts": ["MLM", "MIM", "word-patch alignment"],
        "answer": "LayoutLMv3 jointly uses MLM, MIM, and word-patch alignment [S1, S2].",
        "source_aliases": ["lora_update", "layout_objectives"],
        "labels": [
            {
                "supported": True,
                "rationale": "S2 explicitly lists MLM, MIM, and WPA; grouped citation S1 is irrelevant but does not remove S2 support.",
            }
        ],
    },
    {
        "id": "CCHV5-04",
        "scenario": "uncited_claim_real_evidence_available",
        "question": "How does the neural ODE adjoint method compute gradients?",
        "expected_answer": "It solves an augmented ODE backward in time with low memory cost.",
        "required_concepts": ["adjoint sensitivity", "backward ODE solve"],
        "answer": "The neural ODE adjoint method computes gradients by solving an augmented ODE backward in time.",
        "source_aliases": ["neuralode_adjoint"],
        "labels": [
            {
                "supported": False,
                "rationale": "The statement is factually present in S1, but the claim contains no citation and therefore has no bound evidence.",
            }
        ],
    },
    {
        "id": "CCHV5-05",
        "scenario": "invalid_source_id_real_evidence_available",
        "question": "How are queries, keys, and values transformed in multi-head attention?",
        "expected_answer": "They are projected multiple times with different learned linear projections and processed in parallel.",
        "required_concepts": ["different learned projections", "parallel attention heads"],
        "answer": "Multi-head attention applies different learned projections to queries, keys, and values in parallel [S9].",
        "source_aliases": ["attention_multihead"],
        "labels": [
            {
                "supported": False,
                "rationale": "S9 is outside the one-source response, so the claim has no valid bound evidence.",
            }
        ],
    },
    {
        "id": "CCHV5-06",
        "scenario": "real_evidence_contradicts_claim",
        "question": "Does FlashAttention approximate attention and materialize the attention matrix in HBM?",
        "expected_answer": "No. It computes exact attention and avoids reading and writing the full attention matrix to HBM.",
        "required_concepts": ["exact attention", "avoid attention-matrix HBM traffic"],
        "answer": "FlashAttention is an approximate attention algorithm that materializes the full attention matrix in HBM [S1].",
        "source_aliases": ["flash_io"],
        "labels": [
            {
                "supported": False,
                "rationale": "S1 says FlashAttention is exact and aims to avoid attention-matrix HBM reads and writes.",
            }
        ],
    },
    {
        "id": "CCHV5-07",
        "scenario": "same_real_source_mixed_claims",
        "question": "What does multi-head attention do with its learned projections?",
        "expected_answer": "It applies multiple different learned projections in parallel, concatenates their outputs, and projects again.",
        "required_concepts": ["multiple projections", "parallel heads", "concatenation"],
        "answer": "Multi-head attention applies different learned projections in parallel [S1]. It uses one shared projection and a single head [S1].",
        "source_aliases": ["attention_multihead"],
        "labels": [
            {
                "supported": True,
                "rationale": "S1 explicitly describes h different learned projections whose attention operations run in parallel.",
            },
            {
                "supported": False,
                "rationale": "S1 describes multiple projections and heads, contradicting a single shared projection and head.",
            },
        ],
    },
    {
        "id": "CCHV5-08",
        "scenario": "same_real_source_supported_and_fabricated_detail",
        "question": "How is SynthDoG used for Donut pre-training?",
        "expected_answer": "It generates synthetic document images for Chinese, Japanese, Korean, and English, with 0.5 million samples per language.",
        "required_concepts": ["four languages", "0.5 million samples per language", "synthetic document generation"],
        "answer": "SynthDoG generated 0.5 million samples per language for Chinese, Japanese, Korean, and English [S1]. It uses only real scanned documents and no synthetic backgrounds [S1].",
        "source_aliases": ["donut_pretrain"],
        "labels": [
            {
                "supported": True,
                "rationale": "S1 states that 0.5M samples per language were generated for those four languages.",
            },
            {
                "supported": False,
                "rationale": "S1 describes synthetic rendering and sampled backgrounds rather than only real scanned documents.",
            },
        ],
    },
    {
        "id": "CCHV5-09",
        "scenario": "wrong_method_attribution",
        "question": "Does the neural ODE gradient method use LoRA-style low-rank weight updates?",
        "expected_answer": "No. Neural ODE uses the adjoint sensitivity method; low-rank frozen-weight adaptation belongs to LoRA.",
        "required_concepts": ["adjoint sensitivity for Neural ODE", "low-rank frozen-weight adaptation belongs to LoRA"],
        "answer": "Neural ODE freezes pretrained weights and injects trainable low-rank update matrices [S1].",
        "source_aliases": ["lora_update", "neuralode_adjoint"],
        "labels": [
            {
                "supported": False,
                "rationale": "S1 attributes the mechanism to LoRA, not Neural ODE; S2 describes the Neural ODE adjoint method.",
            }
        ],
    },
    {
        "id": "CCHV5-10",
        "scenario": "partially_supported_composite_claim",
        "question": "How does Mamba combine input-dependent selection with efficient computation?",
        "expected_answer": "It makes SSM parameters input-dependent and computes recurrently with a scan instead of convolution.",
        "required_concepts": ["input-dependent parameters", "scan instead of convolution"],
        "answer": "Mamba makes SSM parameters input-dependent but computes them by convolution rather than a recurrent scan [S1].",
        "source_aliases": ["mamba_selective"],
        "labels": [
            {
                "supported": False,
                "rationale": "S1 supports input dependence but says recurrent scan instead of convolution, so the full composite claim is not entailed.",
            }
        ],
    },
    {
        "id": "CCHV5-11",
        "scenario": "correct_downstream_output_contract",
        "question": "How does Donut formulate downstream document tasks?",
        "expected_answer": "It formulates downstream tasks as token generation that is converted to JSON.",
        "required_concepts": ["token generation", "JSON output"],
        "answer": "Donut formulates downstream document tasks as token generation that can be converted into JSON [S1].",
        "source_aliases": ["donut_json"],
        "labels": [
            {
                "supported": True,
                "rationale": "S1 explicitly describes downstream tasks as JSON prediction via generated token sequences.",
            }
        ],
    },
]

REQUIRED_SCENARIOS = {str(item["scenario"]) for item in CASE_SPECS}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", str(text).lower())


def _load_prior_gold() -> dict[str, set[str]]:
    chunk_ids: set[str] = set()
    questions: set[str] = set()
    for path in PRIOR_GOLD_PATHS:
        dataset = json.loads(path.read_text(encoding="utf-8"))
        for case in dataset.get("cases", []):
            question = _normalize(str(case.get("question", "")))
            if question:
                questions.add(question)
            for evidence_set in case.get("gold_evidence_sets", []):
                for evidence in evidence_set:
                    chunk_id = str(evidence.get("chunk_id", "")).strip()
                    if chunk_id:
                        chunk_ids.add(chunk_id)
    return {"chunk_ids": chunk_ids, "questions": questions}


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_source_catalog(api_base_url: str, collection_id: str) -> dict[str, dict[str, Any]]:
    refs_by_filename: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for alias, ref in SOURCE_REFS.items():
        refs_by_filename[str(ref["filename"])].append((alias, str(ref["chunk_id"])))
    catalog: dict[str, dict[str, Any]] = {}
    for filename, refs in refs_by_filename.items():
        payload = _post_json(
            f"{api_base_url.rstrip('/')}/search_by_filename",
            {
                "collection_name": collection_id,
                "filename": filename,
                "top_k": 500,
            },
        )
        by_chunk_id = {
            str((item.get("metadata") or {}).get("chunk_id", "")): item
            for item in payload.get("results", [])
        }
        for alias, chunk_id in refs:
            if chunk_id not in by_chunk_id:
                raise ValueError(f"missing corpus chunk for {alias}: {chunk_id}")
            catalog[alias] = by_chunk_id[chunk_id]
    return catalog


def _source_record(raw: dict[str, Any], source_id: str) -> dict[str, Any]:
    metadata = raw.get("metadata") or {}
    chunk_text = str(raw.get("chunk_text", ""))
    return {
        "source_id": source_id,
        "filename": str(raw.get("filename", "")),
        "chunk_text": chunk_text,
        "chunk_text_sha256": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
        "metadata": {
            "chunk_id": metadata.get("chunk_id"),
            "page_start": metadata.get("page_start"),
            "content_type": metadata.get("content_type"),
            "section_path": metadata.get("section_path") or [],
        },
    }


def _build_dataset(catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cases = []
    for spec in CASE_SPECS:
        sources = [
            _source_record(catalog[alias], f"S{index}")
            for index, alias in enumerate(spec["source_aliases"], 1)
        ]
        bundles = _build_claim_evidence_bundles(str(spec["answer"]), sources)
        labels = spec["labels"]
        if len(bundles) != len(labels):
            raise ValueError(f"{spec['id']}: parsed claim count does not match labels")
        expected_claims = []
        for bundle, label in zip(bundles, labels):
            expected_claims.append(
                {
                    "id": bundle["id"],
                    "claim": bundle["claim"],
                    "citation_numbers": bundle["citation_numbers"],
                    "evidence_source_ids": [
                        item["source_id"] for item in bundle["evidence"]
                    ],
                    "supported": bool(label["supported"]),
                    "rationale": str(label["rationale"]),
                }
            )
        cases.append(
            {
                key: spec[key]
                for key in (
                    "id",
                    "scenario",
                    "question",
                    "expected_answer",
                    "required_concepts",
                    "answer",
                )
            }
            | {"sources": sources, "expected_claims": expected_claims}
        )
    return {
        "schema_version": "1.0",
        "dataset_id": "scholarlens-claim-citation-entailment-heldout-v5",
        "split": "held_out",
        "benchmark_target": "claim_to_citation_entailment_judge",
        "annotation_status": "pending_human_review",
        "created_at": date.today().isoformat(),
        "human_review": {
            "status": "pending",
            "reviewer": None,
            "date": None,
            "scope": "all_questions_answers_claim_labels_rationales_and_exact_evidence",
        },
        "collection_id": COLLECTION_ID,
        "consumed": False,
        "consumption": None,
        "do_not_execute_before_human_review": True,
        "selection": {
            "source": "exact_chunks_read_directly_from_the_indexed_corpus",
            "semantic_retriever_used_to_select_evidence": False,
            "previous_gold_datasets_checked": [path.name for path in PRIOR_GOLD_PATHS],
        },
        "leakage_controls": {
            "prior_gold_chunk_overlap": False,
            "exact_question_overlap_v1_v2_v3_v4": False,
            "labels_hidden_from_judge_prompt": True,
            "single_execution_after_human_confirmation": True,
            "no_tuning_on_this_split": True,
        },
        "cases": cases,
    }


def _validate_heldout_dataset(
    dataset: dict[str, Any],
    *,
    prior_gold: dict[str, set[str]],
) -> dict[str, Any]:
    binding_errors: list[str] = []
    source_hash_mismatches: list[str] = []
    source_chunk_ids: set[str] = set()
    questions: set[str] = set()
    scenarios: set[str] = set()
    supported_claims = 0
    unsupported_claims = 0
    claim_count = 0
    case_ids: set[str] = set()
    for case in dataset.get("cases", []):
        case_id = str(case.get("id", ""))
        if not case_id or case_id in case_ids:
            binding_errors.append(f"duplicate or empty case id: {case_id!r}")
        case_ids.add(case_id)
        scenarios.add(str(case.get("scenario", "")))
        normalized_question = _normalize(str(case.get("question", "")))
        if normalized_question:
            questions.add(normalized_question)
        sources = case.get("sources") or []
        for index, source in enumerate(sources, 1):
            if source.get("source_id") != f"S{index}":
                binding_errors.append(f"{case_id}: source ids do not match display order")
            chunk_text = str(source.get("chunk_text", ""))
            actual_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            if actual_hash != source.get("chunk_text_sha256"):
                source_hash_mismatches.append(
                    str((source.get("metadata") or {}).get("chunk_id", ""))
                )
            chunk_id = str((source.get("metadata") or {}).get("chunk_id", ""))
            if chunk_id:
                source_chunk_ids.add(chunk_id)
        bundles = _build_claim_evidence_bundles(str(case.get("answer", "")), sources)
        expected_claims = case.get("expected_claims") or []
        if len(bundles) != len(expected_claims):
            binding_errors.append(f"{case_id}: parsed and expected claim counts differ")
            continue
        for bundle, expected in zip(bundles, expected_claims):
            actual_binding = {
                "id": bundle["id"],
                "claim": bundle["claim"],
                "citation_numbers": bundle["citation_numbers"],
                "evidence_source_ids": [
                    item["source_id"] for item in bundle["evidence"]
                ],
            }
            expected_binding = {
                key: expected.get(key)
                for key in (
                    "id",
                    "claim",
                    "citation_numbers",
                    "evidence_source_ids",
                )
            }
            if actual_binding != expected_binding:
                binding_errors.append(f"{case_id}/{bundle['id']}: binding mismatch")
            if expected.get("supported") is True:
                supported_claims += 1
            elif expected.get("supported") is False:
                unsupported_claims += 1
            else:
                binding_errors.append(f"{case_id}/{bundle['id']}: label is not boolean")
        claim_count += len(bundles)
    return {
        "dataset_id": dataset.get("dataset_id"),
        "case_count": len(dataset.get("cases", [])),
        "claim_count": claim_count,
        "scenario_count": len(scenarios),
        "missing_scenarios": sorted(REQUIRED_SCENARIOS - scenarios),
        "supported_claims": supported_claims,
        "unsupported_claims": unsupported_claims,
        "binding_errors": binding_errors,
        "source_hash_mismatches": sorted(set(source_hash_mismatches)),
        "prior_gold_chunk_overlap": sorted(
            source_chunk_ids & prior_gold["chunk_ids"]
        ),
        "question_overlap": sorted(questions & prior_gold["questions"]),
    }


def _assert_valid(validation: dict[str, Any]) -> None:
    failures = {
        key: validation[key]
        for key in (
            "missing_scenarios",
            "binding_errors",
            "source_hash_mismatches",
            "prior_gold_chunk_overlap",
            "question_overlap",
        )
        if validation[key]
    }
    if validation["supported_claims"] == 0 or validation["unsupported_claims"] == 0:
        failures["label_balance"] = "both labels are required"
    if failures:
        raise ValueError("held-out v5 validation failed: " + json.dumps(failures))


def _assert_executable(dataset: dict[str, Any]) -> None:
    review = dataset.get("human_review") or {}
    if (
        dataset.get("annotation_status") != "human_verified"
        or review.get("status") != "confirmed"
        or dataset.get("do_not_execute_before_human_review") is not False
    ):
        raise ValueError("held-out dataset requires confirmed human review before execution")
    if dataset.get("consumed") is not False:
        raise ValueError("held-out dataset has already been consumed")


def _excerpt(text: str, limit: int = 1000) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[:limit].rstrip() + "…"


def _render_review(dataset: dict[str, Any], validation: dict[str, Any]) -> str:
    lines = [
        "# Claim-to-citation Held-out v5 — Human Review",
        "",
        "> **Do not run this held-out split before every item is reviewed and confirmed.**",
        "",
        "## Dataset summary",
        "",
        f"- Cases: {validation['case_count']}",
        f"- Claims: {validation['claim_count']}",
        f"- Supported labels: {validation['supported_claims']}",
        f"- Unsupported labels: {validation['unsupported_claims']}",
        "- Prior Gold chunk overlap: 0",
        "- Exact prior-question overlap: 0",
        "- Current status: `pending_human_review` / `consumed=false`",
        "",
        "For each case, verify the question, candidate answer, claim boundary, citation binding, support label, rationale, and evidence excerpt.",
        "",
    ]
    for case in dataset["cases"]:
        lines.extend(
            [
                f"## {case['id']} — {case['scenario']}",
                "",
                "- [ ] Question and reference answer are correct.",
                "- [ ] Claim boundaries and citation bindings are correct.",
                "- [ ] Support labels and rationales agree with the cited evidence only.",
                "",
                f"**Question:** {case['question']}",
                "",
                f"**Reference answer:** {case['expected_answer']}",
                "",
                f"**Candidate answer:** {case['answer']}",
                "",
                "### Expected claim decisions",
                "",
                "| Claim | Bound evidence | Label | Rationale |",
                "|---|---|---|---|",
            ]
        )
        for claim in case["expected_claims"]:
            rationale = str(claim["rationale"]).replace("|", "\\|")
            claim_text = str(claim["claim"]).replace("|", "\\|")
            label = "supported" if claim["supported"] else "unsupported"
            evidence = ", ".join(claim["evidence_source_ids"]) or "none"
            lines.append(
                f"| {claim['id']}: {claim_text} | {evidence} | {label} | {rationale} |"
            )
        lines.extend(["", "### Evidence", ""])
        for source in case["sources"]:
            metadata = source["metadata"]
            section = " > ".join(metadata.get("section_path") or []) or "(no section)"
            lines.extend(
                [
                    f"**{source['source_id']} — {source['filename']}**, page {metadata.get('page_start')}, `{section}`",
                    "",
                    f"- Chunk: `{metadata.get('chunk_id')}`",
                    f"- SHA-256: `{source['chunk_text_sha256']}`",
                    "",
                    f"> {_excerpt(source['chunk_text'])}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Final owner confirmation",
            "",
            "- [ ] I reviewed all 11 cases and 13 claim labels.",
            "- [ ] I confirm that labels use only each claim's bound cited evidence.",
            "- [ ] I authorize changing the dataset to `human_verified` and executing it once.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--collection", default=COLLECTION_ID)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--review", type=Path, default=REVIEW_PATH)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    prior_gold = _load_prior_gold()
    if args.validate_only:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    else:
        if args.dataset.exists():
            existing = json.loads(args.dataset.read_text(encoding="utf-8"))
            if existing.get("annotation_status") == "human_verified" or existing.get("consumed"):
                raise ValueError("refusing to overwrite a reviewed or consumed held-out dataset")
        catalog = _fetch_source_catalog(args.api_base_url, args.collection)
        dataset = _build_dataset(catalog)
    validation = _validate_heldout_dataset(dataset, prior_gold=prior_gold)
    _assert_valid(validation)
    if not args.validate_only:
        args.dataset.parent.mkdir(parents=True, exist_ok=True)
        args.dataset.write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        args.review.write_text(_render_review(dataset, validation), encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
