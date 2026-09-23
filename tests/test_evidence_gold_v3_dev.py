import json
import unittest
from pathlib import Path

from scripts.evaluate_evidence_retrieval import _validate_dataset
from scripts.evaluate_multi_query_coverage import _validate_query_plans


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evaluation"
    / "evidence-gold-v3-multi-query-dev.json"
)


class EvidenceGoldV3DevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    def test_dataset_is_explicitly_development_and_review_pending(self):
        self.assertEqual(self.dataset["split"], "development")
        self.assertTrue(self.dataset["annotation_status"].startswith("review_pending"))

    def test_all_cases_have_valid_two_target_query_plans(self):
        _validate_dataset(self.dataset)
        _validate_query_plans(self.dataset)

        self.assertEqual(len(self.dataset["cases"]), 6)
        for case in self.dataset["cases"]:
            self.assertEqual(case["category"], "cross_paper_comparison")
            self.assertEqual(len(case["retrieval_subqueries"]), 2)
            filenames = {
                evidence["filename"]
                for evidence in case["gold_evidence_sets"][0]
            }
            self.assertEqual(len(filenames), 2)

    def test_confirmed_alternatives_are_appended_without_replacing_original_gold(self):
        review = self.dataset["alternative_evidence_review"]
        self.assertEqual(review["status"], "human_confirmed")
        self.assertEqual(review["date"], "2026-09-23")

        expected_set_counts = {"MQ01": 3, "MQ02": 2, "MQ05": 3}
        for case in self.dataset["cases"]:
            evidence_sets = case["gold_evidence_sets"]
            self.assertEqual(
                len(evidence_sets), expected_set_counts.get(case["id"], 1)
            )
            normalized_sets = {
                tuple(sorted(item["chunk_id"] for item in evidence_set))
                for evidence_set in evidence_sets
            }
            self.assertEqual(len(normalized_sets), len(evidence_sets))
            for evidence_set in evidence_sets:
                self.assertEqual(
                    len({item["filename"] for item in evidence_set}), 2
                )


if __name__ == "__main__":
    unittest.main()
