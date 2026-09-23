import json
import unittest
from pathlib import Path

from scripts.evaluate_evidence_retrieval import _validate_dataset
from scripts.evaluate_multi_query_coverage import _validate_query_plans


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = PROJECT_ROOT / "docs" / "evaluation"
V4_PATH = EVALUATION_DIR / "evidence-gold-v4-answer-citations-heldout.json"
PRIOR_PATHS = [
    EVALUATION_DIR / "evidence-gold-v1.json",
    EVALUATION_DIR / "evidence-gold-v2-heldout.json",
    EVALUATION_DIR / "evidence-gold-v3-multi-query-dev.json",
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _questions(dataset: dict) -> set[str]:
    return {case["question"].casefold().strip() for case in dataset["cases"]}


def _gold_chunk_ids(dataset: dict) -> set[str]:
    return {
        evidence["chunk_id"]
        for case in dataset["cases"]
        for evidence_set in case.get("gold_evidence_sets", [])
        for evidence in evidence_set
    }


class EvidenceGoldV4HeldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = _load(V4_PATH)
        cls.prior = [_load(path) for path in PRIOR_PATHS]

    def test_dataset_is_human_verified_and_consumed(self):
        self.assertEqual(
            self.dataset["dataset_id"],
            "scholarlens-evidence-gold-v4-answer-citations-heldout",
        )
        self.assertEqual(self.dataset["split"], "held_out")
        self.assertEqual(self.dataset["annotation_status"], "human_verified")
        self.assertTrue(self.dataset["consumed"])
        self.assertFalse(self.dataset["do_not_execute_before_human_review"])
        self.assertEqual(self.dataset["human_review"]["status"], "confirmed")
        self.assertEqual(self.dataset["consumption"]["outcome"], "no_go")
        self.assertFalse(self.dataset["consumption"]["acceptance_passed"])

    def test_cases_have_valid_cross_paper_query_plans(self):
        _validate_dataset(self.dataset)
        _validate_query_plans(self.dataset)

        self.assertEqual(len(self.dataset["cases"]), 8)
        for case in self.dataset["cases"]:
            self.assertEqual(case["category"], "cross_paper_comparison")
            self.assertTrue(case["answerable"])
            self.assertEqual(len(case["retrieval_subqueries"]), 2)
            self.assertEqual(len(case["gold_evidence_sets"]), 1)
            evidence_set = case["gold_evidence_sets"][0]
            self.assertEqual(len(evidence_set), 2)
            self.assertEqual(len({item["filename"] for item in evidence_set}), 2)

    def test_questions_and_gold_chunks_do_not_overlap_prior_datasets(self):
        prior_questions = set().union(*(_questions(item) for item in self.prior))
        prior_gold = set().union(*(_gold_chunk_ids(item) for item in self.prior))

        self.assertTrue(_questions(self.dataset).isdisjoint(prior_questions))
        self.assertTrue(_gold_chunk_ids(self.dataset).isdisjoint(prior_gold))

    def test_gold_chunks_are_unique_within_v4(self):
        all_references = [
            evidence["chunk_id"]
            for case in self.dataset["cases"]
            for evidence_set in case["gold_evidence_sets"]
            for evidence in evidence_set
        ]
        self.assertEqual(len(all_references), 16)
        self.assertEqual(len(set(all_references)), 16)

    def test_frozen_answer_configuration_and_scope_are_explicit(self):
        self.assertEqual(
            self.dataset["frozen_configuration"],
            {
                "model_name": "qwen3-vl-plus",
                "top_k": 10,
                "score_threshold": 0.1,
                "use_multi_query": True,
                "candidate_k_per_query": 10,
                "rrf_k": 60,
                "original_reserve": 4,
                "per_target_reserve": 2,
                "use_reranker": False,
                "temperature": 0.0,
                "max_answer_tokens": 1400,
            },
        )
        scope = self.dataset["heldout_scope"]
        self.assertEqual(scope["level"], "question_and_gold_chunk_combination")
        self.assertFalse(scope["paper_level_holdout"])
        self.assertTrue(
            self.dataset["leakage_controls"]["no_parameter_tuning_on_this_split"]
        )
        self.assertTrue(
            self.dataset["leakage_controls"]["single_execution_after_human_verification"]
        )


if __name__ == "__main__":
    unittest.main()
