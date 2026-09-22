import unittest

from scripts.evaluate_reranker_ab import (
    _acceptance_decision,
    _build_rerank_payload,
    _parse_rerank_results,
    _rerank_hits,
)


class RerankerABEvaluationTests(unittest.TestCase):
    def test_acceptance_requires_every_quality_and_latency_gate(self):
        decision = _acceptance_decision(
            dense={"strict_evidence_hit_rate": 1.0},
            reranked={
                "strict_evidence_hit_rate": 1.0,
                "evidence_set_mrr": 0.80,
                "mean_ndcg": 0.85,
            },
            added_latency_seconds=0.25,
            min_mrr=0.75,
            min_ndcg=0.82,
            max_added_latency_seconds=1.0,
        )

        self.assertEqual(decision["decision"], "go")
        self.assertTrue(all(decision["gates"].values()))

        regressed = _acceptance_decision(
            dense={"strict_evidence_hit_rate": 1.0},
            reranked={
                "strict_evidence_hit_rate": 0.9,
                "evidence_set_mrr": 0.80,
                "mean_ndcg": 0.85,
            },
            added_latency_seconds=0.25,
            min_mrr=0.75,
            min_ndcg=0.82,
            max_added_latency_seconds=1.0,
        )

        self.assertEqual(regressed["decision"], "no-go")
        self.assertFalse(regressed["gates"]["hit_rate_non_regression"])

    def test_builds_dashscope_gte_request_contract(self):
        payload = _build_rerank_payload(
            model="gte-rerank-v2",
            query="question",
            documents=["first", "second"],
            top_n=2,
        )

        self.assertEqual(payload["model"], "gte-rerank-v2")
        self.assertEqual(payload["input"]["query"], "question")
        self.assertEqual(payload["input"]["documents"], ["first", "second"])
        self.assertEqual(payload["parameters"]["top_n"], 2)
        self.assertFalse(payload["parameters"]["return_documents"])

    def test_parses_dashscope_nested_results(self):
        results = _parse_rerank_results(
            {
                "output": {
                    "results": [
                        {"index": 1, "relevance_score": 0.9},
                        {"index": 0, "relevance_score": 0.4},
                    ]
                }
            },
            document_count=2,
        )

        self.assertEqual(results, [(1, 0.9), (0, 0.4)])

    def test_parses_openai_compatible_top_level_results(self):
        results = _parse_rerank_results(
            {
                "results": [
                    {"index": 0, "relevance_score": 0.8},
                    {"index": 1, "score": 0.2},
                ]
            },
            document_count=2,
        )

        self.assertEqual(results, [(0, 0.8), (1, 0.2)])

    def test_rejects_duplicate_or_out_of_range_indices(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _parse_rerank_results(
                {
                    "results": [
                        {"index": 0, "relevance_score": 0.8},
                        {"index": 0, "relevance_score": 0.7},
                    ]
                },
                document_count=2,
            )

        with self.assertRaisesRegex(ValueError, "out of range"):
            _parse_rerank_results(
                {"results": [{"index": 2, "relevance_score": 0.8}]},
                document_count=2,
            )

    def test_rerank_preserves_dense_score_and_provenance(self):
        hits = [
            {
                "score": 0.75,
                "chunk_text": "first",
                "metadata": {"chunk_id": "chunk-a"},
            },
            {
                "score": 0.65,
                "chunk_text": "second",
                "metadata": {"chunk_id": "chunk-b"},
            },
        ]

        reranked = _rerank_hits(hits, [(1, 0.95), (0, 0.5)])

        self.assertEqual(reranked[0]["metadata"]["chunk_id"], "chunk-b")
        self.assertEqual(reranked[0]["retrieval_score"], 0.65)
        self.assertEqual(reranked[0]["rerank_score"], 0.95)
        self.assertEqual(reranked[0]["score"], 0.95)
        self.assertNotIn("rerank_score", hits[1])


if __name__ == "__main__":
    unittest.main()
