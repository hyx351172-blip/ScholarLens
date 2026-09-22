import unittest

from scripts.evaluate_rank_fusion import _fuse_rrf


def hit(chunk_id: str, score: float) -> dict:
    return {
        "score": score,
        "chunk_text": chunk_id,
        "metadata": {"chunk_id": chunk_id},
    }


class RankFusionEvaluationTests(unittest.TestCase):
    def test_dense_biased_rrf_preserves_scores_ranks_and_inputs(self):
        dense = [hit("a", 0.9), hit("b", 0.8), hit("c", 0.7), hit("d", 0.6)]
        reranked = [
            {**hit("d", 0.95), "retrieval_score": 0.6, "rerank_score": 0.95},
            {**hit("c", 0.85), "retrieval_score": 0.7, "rerank_score": 0.85},
            {**hit("b", 0.75), "retrieval_score": 0.8, "rerank_score": 0.75},
            {**hit("a", 0.65), "retrieval_score": 0.9, "rerank_score": 0.65},
        ]

        fused = _fuse_rrf(
            dense,
            reranked,
            rrf_k=60,
            dense_weight=2.0,
            reranker_weight=1.0,
        )

        self.assertEqual(fused[0]["metadata"]["chunk_id"], "a")
        self.assertEqual(fused[0]["dense_rank"], 1)
        self.assertEqual(fused[0]["rerank_rank"], 4)
        self.assertEqual(fused[0]["retrieval_score"], 0.9)
        self.assertEqual(fused[0]["rerank_score"], 0.65)
        self.assertGreater(fused[0]["fusion_score"], fused[-1]["fusion_score"])
        self.assertNotIn("fusion_score", dense[0])
        self.assertNotIn("fusion_score", reranked[-1])

    def test_fusion_rejects_candidate_set_mismatch(self):
        with self.assertRaisesRegex(ValueError, "candidate sets differ"):
            _fuse_rrf(
                [hit("a", 0.9), hit("b", 0.8)],
                [hit("a", 0.9), hit("c", 0.8)],
                rrf_k=60,
                dense_weight=1.0,
                reranker_weight=1.0,
            )

    def test_fusion_rejects_duplicate_chunk_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate chunk id"):
            _fuse_rrf(
                [hit("a", 0.9), hit("a", 0.8)],
                [hit("a", 0.9), hit("b", 0.8)],
                rrf_k=60,
                dense_weight=1.0,
                reranker_weight=1.0,
            )

    def test_fusion_validates_positive_parameters(self):
        with self.assertRaisesRegex(ValueError, "rrf_k"):
            _fuse_rrf(
                [hit("a", 0.9)],
                [hit("a", 0.9)],
                rrf_k=0,
                dense_weight=1.0,
                reranker_weight=1.0,
            )


if __name__ == "__main__":
    unittest.main()
