import json
import unittest
from pathlib import Path

from scripts.build_claim_citation_heldout_v5 import (
    DATASET_PATH,
    REVIEW_PATH,
    _assert_executable,
    _load_prior_gold,
    _validate_heldout_dataset,
)
from scripts.evaluate_claim_citation_entailment import _validate_run_dataset


class ClaimCitationHeldoutV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    def test_real_chunks_are_hashed_and_do_not_overlap_prior_gold(self):
        # @covers AC-203.1
        validation = _validate_heldout_dataset(
            self.dataset,
            prior_gold=_load_prior_gold(),
        )

        self.assertEqual(validation["prior_gold_chunk_overlap"], [])
        self.assertEqual(validation["source_hash_mismatches"], [])
        self.assertEqual(validation["question_overlap"], [])

    def test_expected_claim_bindings_match_parser_output(self):
        # @covers AC-203.2
        validation = _validate_heldout_dataset(
            self.dataset,
            prior_gold=_load_prior_gold(),
        )

        self.assertEqual(validation["case_count"], 11)
        self.assertEqual(validation["claim_count"], 13)
        self.assertEqual(validation["binding_errors"], [])

    def test_dataset_covers_risk_scenarios_and_both_labels(self):
        # @covers AC-203.3
        validation = _validate_heldout_dataset(
            self.dataset,
            prior_gold=_load_prior_gold(),
        )

        self.assertEqual(validation["scenario_count"], 11)
        self.assertEqual(validation["supported_claims"], 5)
        self.assertEqual(validation["unsupported_claims"], 8)

    def test_pending_review_dataset_cannot_be_executed(self):
        # @covers AC-203.4
        self.assertEqual(self.dataset["annotation_status"], "pending_human_review")
        self.assertFalse(self.dataset["consumed"])
        self.assertTrue(self.dataset["do_not_execute_before_human_review"])
        with self.assertRaisesRegex(ValueError, "human review"):
            _assert_executable(self.dataset)
        with self.assertRaisesRegex(ValueError, "human review"):
            _validate_run_dataset(self.dataset)

    def test_owner_review_document_lists_every_case(self):
        # @covers AC-203.5
        review = REVIEW_PATH.read_text(encoding="utf-8")

        self.assertIn("Do not run this held-out split", review)
        self.assertEqual(review.count("## CCHV5-"), 11)
        self.assertGreaterEqual(review.count("- [ ]"), 11)


if __name__ == "__main__":
    unittest.main()
