import unittest

from scripts.evaluate_evidence_retrieval import (
    _best_set_metrics,
    _ndcg,
    _validate_dataset,
)


class EvidenceRetrievalEvaluationTests(unittest.TestCase):
    def test_complete_multi_chunk_set_uses_last_required_rank(self):
        strict_hit, recall, reciprocal_rank = _best_set_metrics(
            ["noise", "evidence-a", "evidence-b"],
            [["evidence-a", "evidence-b"]],
        )

        self.assertTrue(strict_hit)
        self.assertEqual(recall, 1.0)
        self.assertAlmostEqual(reciprocal_rank, 1 / 3)

    def test_partial_multi_chunk_set_does_not_count_as_strict_hit(self):
        strict_hit, recall, reciprocal_rank = _best_set_metrics(
            ["evidence-a", "noise"],
            [["evidence-a", "evidence-b"]],
        )

        self.assertFalse(strict_hit)
        self.assertEqual(recall, 0.5)
        self.assertEqual(reciprocal_rank, 0.0)

    def test_perfect_ranking_has_ndcg_one(self):
        self.assertEqual(_ndcg(["a", "b", "noise"], [["a", "b"]]), 1.0)

    def test_unanswerable_case_cannot_contain_gold_evidence(self):
        dataset = {
            "cases": [
                {
                    "id": "EV-X",
                    "answerable": False,
                    "gold_evidence_sets": [[{"chunk_id": "unexpected"}]],
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "must not have gold evidence"):
            _validate_dataset(dataset)


if __name__ == "__main__":
    unittest.main()
