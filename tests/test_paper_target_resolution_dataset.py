import json
import unittest
from pathlib import Path

from backend.chat.multi_query_retrieval import resolve_target_filename


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evaluation"
    / "paper-target-resolution-dev-v1.json"
)


class PaperTargetResolutionDatasetTests(unittest.TestCase):
    """AC-201.5: development aliases, exclusions, and live plans stay valid."""

    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    def test_dataset_is_development_only_and_excludes_known_bad_files(self):
        self.assertEqual(self.dataset["split"], "development")
        excluded = {
            item["filename"] for item in self.dataset["excluded_corpus_files"]
        }
        self.assertTrue(excluded)
        self.assertTrue(excluded.isdisjoint(self.dataset["corpus_filenames"]))

    def test_every_target_matches_its_expected_resolution(self):
        filenames = self.dataset["corpus_filenames"]
        self.assertEqual(len(self.dataset["cases"]), 18)
        for case in self.dataset["cases"]:
            with self.subTest(case=case["id"]):
                resolution = resolve_target_filename(case["target"], filenames)
                expected_status = case.get("expected_status", "resolved")
                self.assertEqual(resolution.status, expected_status)
                self.assertEqual(resolution.filename, case["expected_filename"])

    def test_live_retrieval_cases_have_two_distinct_resolvable_targets(self):
        filenames = self.dataset["corpus_filenames"]
        self.assertEqual(len(self.dataset["retrieval_cases"]), 3)
        for case in self.dataset["retrieval_cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(len(case["subqueries"]), 2)
                self.assertEqual(len(set(case["expected_filenames"])), 2)
                resolved = {
                    resolve_target_filename(item["target"], filenames).filename
                    for item in case["subqueries"]
                }
                self.assertEqual(resolved, set(case["expected_filenames"]))


if __name__ == "__main__":
    unittest.main()
