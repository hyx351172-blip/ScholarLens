import json
import copy
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

    def test_consumed_dataset_is_frozen_and_lifecycle_guards_work(self):
        # @covers AC-203.4
        self.assertEqual(self.dataset["annotation_status"], "human_verified")
        self.assertTrue(self.dataset["consumed"])
        self.assertFalse(self.dataset["do_not_execute_before_human_review"])
        with self.assertRaisesRegex(ValueError, "already been consumed"):
            _assert_executable(self.dataset)
        with self.assertRaisesRegex(ValueError, "already been consumed"):
            _validate_run_dataset(self.dataset)

        before_consumption = copy.deepcopy(self.dataset)
        before_consumption["consumed"] = False
        before_consumption["consumption"] = None
        _assert_executable(before_consumption)
        self.assertEqual(_validate_run_dataset(before_consumption)["case_count"], 11)

        pending_review = copy.deepcopy(before_consumption)
        pending_review["annotation_status"] = "pending_human_review"
        pending_review["human_review"]["status"] = "pending"
        pending_review["do_not_execute_before_human_review"] = True
        with self.assertRaisesRegex(ValueError, "human review"):
            _assert_executable(pending_review)

    def test_owner_review_document_lists_every_case(self):
        # @covers AC-203.5
        review = REVIEW_PATH.read_text(encoding="utf-8")

        self.assertIn("Do not run this held-out split", review)
        self.assertEqual(review.count("## CCHV5-"), 11)
        self.assertGreaterEqual(review.count("- [x]"), 11)
        self.assertIn("consumed=true", review)
        self.assertIn("result **GO**", review)


if __name__ == "__main__":
    unittest.main()
