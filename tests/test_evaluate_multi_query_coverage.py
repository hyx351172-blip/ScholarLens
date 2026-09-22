import unittest

from scripts.evaluate_multi_query_coverage import (
    _coverage_select,
    _query_rrf,
    _validate_query_plans,
)


def _hit(chunk_id: str, score: float = 0.5) -> dict:
    return {
        "score": score,
        "chunk_text": f"text for {chunk_id}",
        "metadata": {"chunk_id": chunk_id},
    }


class MultiQueryCoverageTests(unittest.TestCase):
    def test_query_rrf_deduplicates_and_records_query_provenance(self):
        fused = _query_rrf(
            {
                "original": [_hit("shared"), _hit("only-original")],
                "paper-a": [_hit("only-a"), _hit("shared")],
            },
            rrf_k=60,
        )

        self.assertEqual([item["metadata"]["chunk_id"] for item in fused], [
            "shared",
            "only-a",
            "only-original",
        ])
        self.assertEqual(fused[0]["matched_query_ids"], ["original", "paper-a"])
        self.assertEqual(fused[0]["query_ranks"], {"original": 1, "paper-a": 2})

    def test_coverage_selector_reserves_one_candidate_for_each_target(self):
        fused = [
            {
                **_hit("dominant-1"),
                "matched_query_ids": ["original", "paper-a"],
                "query_ranks": {"original": 1, "paper-a": 1},
                "query_rrf_score": 0.30,
            },
            {
                **_hit("dominant-2"),
                "matched_query_ids": ["paper-a"],
                "query_ranks": {"paper-a": 2},
                "query_rrf_score": 0.20,
            },
            {
                **_hit("complementary"),
                "matched_query_ids": ["paper-b"],
                "query_ranks": {"paper-b": 1},
                "query_rrf_score": 0.10,
            },
        ]

        selected = _coverage_select(fused, ["paper-a", "paper-b"], top_k=2)

        self.assertEqual(
            {item["metadata"]["chunk_id"] for item in selected},
            {"dominant-1", "complementary"},
        )

    def test_one_chunk_can_cover_more_than_one_target(self):
        fused = [
            {
                **_hit("shared"),
                "matched_query_ids": ["paper-a", "paper-b"],
                "query_ranks": {"paper-a": 1, "paper-b": 1},
                "query_rrf_score": 0.30,
            },
            {
                **_hit("next"),
                "matched_query_ids": ["original"],
                "query_ranks": {"original": 1},
                "query_rrf_score": 0.20,
            },
        ]

        selected = _coverage_select(fused, ["paper-a", "paper-b"], top_k=2)

        self.assertEqual(
            [item["metadata"]["chunk_id"] for item in selected],
            ["shared", "next"],
        )

    def test_original_reserve_preserves_baseline_evidence(self):
        fused = [
            {
                **_hit("shared-target-hit"),
                "matched_query_ids": ["paper-a", "paper-b"],
                "query_ranks": {"paper-a": 1, "paper-b": 1},
                "query_rrf_score": 0.30,
            },
            {
                **_hit("baseline-evidence"),
                "matched_query_ids": ["original"],
                "query_ranks": {"original": 1},
                "query_rrf_score": 0.10,
            },
        ]

        selected = _coverage_select(
            fused,
            ["paper-a", "paper-b"],
            top_k=3,
            original_reserve=1,
        )

        self.assertEqual(
            {item["metadata"]["chunk_id"] for item in selected},
            {"shared-target-hit", "baseline-evidence"},
        )

    def test_per_target_reserve_keeps_top_two_from_each_target(self):
        fused = [
            {
                **_hit("a-1"),
                "matched_query_ids": ["paper-a"],
                "query_ranks": {"paper-a": 1},
                "query_rrf_score": 0.40,
            },
            {
                **_hit("b-1"),
                "matched_query_ids": ["paper-b"],
                "query_ranks": {"paper-b": 1},
                "query_rrf_score": 0.30,
            },
            {
                **_hit("a-2"),
                "matched_query_ids": ["paper-a"],
                "query_ranks": {"paper-a": 2},
                "query_rrf_score": 0.20,
            },
            {
                **_hit("b-2"),
                "matched_query_ids": ["paper-b"],
                "query_ranks": {"paper-b": 2},
                "query_rrf_score": 0.10,
            },
        ]

        selected = _coverage_select(
            fused,
            ["paper-a", "paper-b"],
            top_k=4,
            per_target_reserve=2,
        )

        self.assertEqual(
            {item["metadata"]["chunk_id"] for item in selected},
            {"a-1", "a-2", "b-1", "b-2"},
        )

    def test_query_plan_requires_unique_nonempty_target_queries(self):
        dataset = {
            "cases": [
                {
                    "id": "MQ-X",
                    "category": "cross_paper_comparison",
                    "answerable": True,
                    "retrieval_subqueries": [
                        {"id": "paper-a", "query": "first"},
                        {"id": "paper-a", "query": "second"},
                    ],
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "unique"):
            _validate_query_plans(dataset)


if __name__ == "__main__":
    unittest.main()
