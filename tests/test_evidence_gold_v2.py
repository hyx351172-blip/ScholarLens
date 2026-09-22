import json
import unittest
from collections import Counter
from pathlib import Path

from scripts.evaluate_evidence_retrieval import _validate_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_PATH = PROJECT_ROOT / "docs" / "evaluation" / "evidence-gold-v1.json"
V2_PATH = (
    PROJECT_ROOT / "docs" / "evaluation" / "evidence-gold-v2-heldout.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _gold_chunk_ids(dataset: dict) -> set[str]:
    return {
        evidence["chunk_id"]
        for case in dataset["cases"]
        for evidence_set in case.get("gold_evidence_sets", [])
        for evidence in evidence_set
    }


class EvidenceGoldV2Tests(unittest.TestCase):
    def test_heldout_dataset_has_planned_case_mix_and_valid_schema(self):
        dataset = _load(V2_PATH)

        _validate_dataset(dataset)

        self.assertEqual(dataset["dataset_id"], "scholarlens-evidence-gold-v2-heldout")
        self.assertEqual(dataset["annotation_status"], "human_verified")
        self.assertEqual(dataset["split"], "held_out")
        self.assertEqual(len(dataset["cases"]), 24)
        self.assertEqual(
            Counter(case["category"] for case in dataset["cases"]),
            Counter(
                {
                    "mechanism": 6,
                    "table": 4,
                    "figure": 3,
                    "formula": 3,
                    "cross_paper_comparison": 4,
                    "unanswerable": 4,
                }
            ),
        )
        self.assertEqual(
            sum(bool(case["answerable"]) for case in dataset["cases"]), 20
        )

    def test_heldout_questions_and_gold_chunks_do_not_overlap_v1(self):
        v1 = _load(V1_PATH)
        v2 = _load(V2_PATH)
        v1_questions = {case["question"].casefold().strip() for case in v1["cases"]}
        v2_questions = {case["question"].casefold().strip() for case in v2["cases"]}

        self.assertTrue(v1_questions.isdisjoint(v2_questions))
        self.assertTrue(_gold_chunk_ids(v1).isdisjoint(_gold_chunk_ids(v2)))

    def test_answerable_cases_use_papers_not_used_as_v1_gold_evidence(self):
        v1 = _load(V1_PATH)
        v2 = _load(V2_PATH)
        v1_files = {
            evidence["filename"]
            for case in v1["cases"]
            for evidence_set in case.get("gold_evidence_sets", [])
            for evidence in evidence_set
        }
        v2_files = {
            evidence["filename"]
            for case in v2["cases"]
            if case["answerable"]
            for evidence_set in case["gold_evidence_sets"]
            for evidence in evidence_set
        }

        self.assertTrue(v1_files.isdisjoint(v2_files))

    def test_rank_fusion_configuration_is_frozen_before_review(self):
        dataset = _load(V2_PATH)

        self.assertEqual(
            dataset["frozen_configuration"],
            {
                "candidate_k": 20,
                "top_k": 10,
                "rrf_k": 60,
                "dense_weight": 2.0,
                "reranker_weight": 1.0,
                "reranker_model": "qwen3-rerank",
            },
        )
        self.assertTrue(dataset["leakage_controls"]["no_parameter_tuning_on_this_split"])


if __name__ == "__main__":
    unittest.main()
