import json
import unittest
from pathlib import Path

from scripts.evaluate_answer_citations import _build_judge_prompt
from scripts.evaluate_claim_citation_entailment import (
    _acceptance,
    _score_case,
    _summarize,
    _validate_dataset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "docs/evaluation/claim-citation-entailment-dev-v1.json"


class ClaimCitationEntailmentDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    def test_development_dataset_covers_required_scenarios(self):
        # @covers AC-202.4
        validation = _validate_dataset(self.dataset)

        self.assertEqual(validation["case_count"], 7)
        self.assertEqual(validation["claim_count"], 8)
        self.assertEqual(validation["scenario_count"], 7)

    def test_wrong_citation_cannot_see_correct_global_evidence(self):
        # @covers AC-202.2, AC-202.4
        case = next(
            item
            for item in self.dataset["cases"]
            if item["scenario"] == "wrong_citation_correct_evidence_elsewhere"
        )
        prompt = _build_judge_prompt(
            question=case["question"],
            answer=case["answer"],
            expected_answer=case["expected_answer"],
            required_concepts=case["required_concepts"],
            sources=case["sources"],
        )

        self.assertIn("BERT is pre-trained", prompt)
        self.assertNotIn("injects trainable low-rank", prompt)
        self.assertIn("Cited evidence for A1 only", prompt)

    def test_perfect_claim_predictions_pass_development_gate(self):
        # @covers AC-202.5
        scored = []
        for case in self.dataset["cases"]:
            judgement = {
                "claim_support": [
                    {
                        "id": item["id"],
                        "supported": item["supported"],
                        "reason": "fixture decision",
                    }
                    for item in case["expected_claims"]
                ]
            }
            scored.append(_score_case(case, judgement))

        summary = _summarize(scored)
        self.assertEqual(summary["claim_decision_accuracy"], 1.0)
        self.assertEqual(summary["unsupported_claim_recall"], 1.0)
        self.assertTrue(_acceptance(summary)["passed"])


if __name__ == "__main__":
    unittest.main()
