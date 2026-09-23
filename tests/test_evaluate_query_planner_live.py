import unittest

from backend.chat.multi_query_retrieval import parse_query_plan, single_query_plan
from scripts.evaluate_query_planner_live import (
    _acceptance_decision,
    _evidence_metrics_from_ids,
    _match_expected_targets,
    _normalize_target,
    _summarize,
)


class LivePlannerEvaluationTests(unittest.TestCase):
    def test_normalize_target_ignores_case_space_and_punctuation(self):
        self.assertEqual(_normalize_target("GPT-3"), "gpt3")
        self.assertEqual(_normalize_target("Layout LM v3"), "layoutlmv3")

    def test_expected_targets_match_distinct_generated_queries(self):
        plan = parse_query_plan(
            """{
              "intent": "comparison",
              "subqueries": [
                {"id": "paper-a", "target": "BERT", "query": "What objectives pretrain BERT?"},
                {"id": "paper-b", "target": "GPT-3", "query": "How does GPT-3 learn in context?"}
              ]
            }""",
            "Compare BERT and GPT-3",
        )
        matches, missing = _match_expected_targets(["bert", "gpt3"], plan)
        self.assertEqual(matches, {"bert": "paper-a", "gpt3": "paper-b"})
        self.assertEqual(missing, [])

    def test_expected_target_match_does_not_reuse_one_subquery(self):
        plan = parse_query_plan(
            """{
              "intent": "comparison",
              "subqueries": [
                {"id": "combined", "target": "BERT GPT-3", "query": "Explain both systems"},
                {"id": "other", "target": "language models", "query": "Explain transfer"}
              ]
            }""",
            "Compare BERT and GPT-3",
        )
        matches, missing = _match_expected_targets(["bert", "gpt3"], plan)
        self.assertEqual(len(matches), 1)
        self.assertEqual(len(missing), 1)

    def test_summary_counts_fallbacks_and_retrieval_quality(self):
        base = {
            "expected_target_ids": ["bert", "gpt3"],
            "target_matches": {"bert": "bert", "gpt3": "gpt3"},
            "missing_target_ids": [],
            "target_cardinality_valid": True,
            "valid_plan": True,
            "plan": {"fallback_reason": None},
            "planner_latency_seconds": 1.0,
            "retrieval_latency_seconds": 2.0,
            "end_to_end_latency_seconds": 3.0,
            "retrieval": {
                "strict_evidence_hit": True,
                "best_evidence_set_recall": 1.0,
                "evidence_set_reciprocal_rank": 0.5,
                "ndcg": 0.75,
            },
        }
        fallback = {
            **base,
            "valid_plan": False,
            "target_matches": {},
            "missing_target_ids": ["bert", "gpt3"],
            "plan": {"fallback_reason": "planner_timeout"},
            "retrieval": {
                **base["retrieval"],
                "strict_evidence_hit": False,
                "best_evidence_set_recall": 0.5,
            },
        }
        summary = _summarize([base, fallback])
        self.assertEqual(summary["valid_plan_rate"], 0.5)
        self.assertEqual(summary["complete_target_rate"], 0.5)
        self.assertEqual(summary["strict_evidence_hit_rate"], 0.5)
        self.assertEqual(summary["fallback_reasons"], {"planner_timeout": 1})

    def test_acceptance_requires_every_threshold(self):
        summary = {
            "valid_plan_rate": 1.0,
            "complete_target_rate": 1.0,
            "strict_evidence_hit_rate": 5 / 6,
            "mean_planner_latency_seconds": 2.0,
        }
        accepted = _acceptance_decision(
            summary,
            min_valid_plan_rate=1.0,
            min_complete_target_rate=1.0,
            min_strict_hit_rate=0.83,
            max_mean_planner_latency=12.0,
        )
        self.assertTrue(accepted["passed"])
        rejected = _acceptance_decision(
            {**summary, "complete_target_rate": 0.9},
            min_valid_plan_rate=1.0,
            min_complete_target_rate=1.0,
            min_strict_hit_rate=0.83,
            max_mean_planner_latency=12.0,
        )
        self.assertFalse(rejected["passed"])

    def test_persisted_ids_can_match_a_human_confirmed_alternative_set(self):
        metrics = _evidence_metrics_from_ids(
            ["doc-a:alternative", "doc-b:gold"],
            [
                ["doc-a:original", "doc-b:gold"],
                ["doc-a:alternative", "doc-b:gold"],
            ],
        )

        self.assertTrue(metrics["strict_evidence_hit"])
        self.assertEqual(metrics["best_evidence_set_recall"], 1.0)

    def test_single_plan_has_no_target_matches(self):
        matches, missing = _match_expected_targets(
            ["bert", "gpt3"], single_query_plan("planner_timeout")
        )
        self.assertEqual(matches, {})
        self.assertEqual(missing, ["bert", "gpt3"])


if __name__ == "__main__":
    unittest.main()
