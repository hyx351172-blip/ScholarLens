import unittest
from unittest.mock import patch

from backend.chat.kb_chat import ChatService
from backend.chat.multi_query_retrieval import _query_rrf
from backend.chat.section_intent_retrieval import rerank_section_intent


def hit(chunk_index, score, text, *, section_path=None):
    return {
        "score": score,
        "chunk_text": text,
        "filename": "paper.pdf",
        "metadata": {
            "chunk_id": f"chunk-{chunk_index}",
            "chunk_index": chunk_index,
            "section_path": section_path or [],
            "text": text,
        },
    }


class SectionIntentRerankingTests(unittest.TestCase):
    def test_method_and_conclusion_sections_beat_dense_reference_noise(self):
        """AC-401.3/AC-401.4: section evidence outranks reference noise."""
        method = hit(
            7,
            0.18,
            "**3 Model Architecture** The Transformer uses an encoder and decoder.",
            section_path=["3 Model Architecture"],
        )
        conclusion = hit(
            37,
            0.20,
            "**7 Conclusion** We presented the Transformer and report state of the art results.",
            section_path=["7 Conclusion"],
        )
        noise = hit(
            43,
            0.34,
            "[24] Effective approaches to attention based neural machine translation, 2015.",
            section_path=["References"],
        )

        method_ranked = rerank_section_intent("论文的方法是什么", [noise, method, conclusion])
        conclusion_ranked = rerank_section_intent("论文的结论是什么", [noise, method, conclusion])

        self.assertEqual(method_ranked[0]["metadata"]["chunk_index"], 7)
        self.assertEqual(conclusion_ranked[0]["metadata"]["chunk_index"], 37)
        self.assertEqual(method_ranked[0]["retrieval_score"], 0.18)
        self.assertGreater(method_ranked[0]["section_boost"], 0)

    def test_neutral_question_preserves_dense_order(self):
        """AC-401.4: non-section questions retain normal dense ranking."""
        first = hit(1, 0.81, "first evidence")
        second = hit(2, 0.72, "second evidence")

        ranked = rerank_section_intent("What is the BLEU score?", [first, second])

        self.assertEqual(
            [item["metadata"]["chunk_index"] for item in ranked],
            [1, 2],
        )
        self.assertEqual(ranked[0]["score"], 0.81)

    def test_method_word_inside_reference_title_is_not_a_section_heading(self):
        """AC-401.4: a cited paper title must not impersonate Method."""
        method = hit(
            7,
            0.18,
            "**3** **Model Architecture** The Transformer uses self-attention.",
        )
        citation = hit(
            43,
            0.31,
            "Effective approaches to attention based neural machine translation, 2015.",
            section_path=["Attention Is All You Need"],
        )

        ranked = rerank_section_intent("论文的方法是什么", [citation, method])

        self.assertEqual(ranked[0]["metadata"]["chunk_index"], 7)
        self.assertEqual(ranked[1]["section_boost"], 0.0)


class RetrievalCandidatePoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieval_overfetches_then_returns_section_aware_top_k(self):
        """AC-401.3: candidate overfetch happens before Top-K truncation."""
        service = ChatService()
        captured_payload = None
        candidates = [
            hit(index, 0.45 - index * 0.005, f"dense candidate {index}")
            for index in range(35)
        ]
        candidates.append(
            hit(
                37,
                0.19,
                "**7 Conclusion** We presented the Transformer.",
                section_path=["7 Conclusion"],
            )
        )

        class FakeResponse:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return {"status": "success", "results": candidates}

        def fake_post(*_args, **kwargs):
            nonlocal captured_payload
            captured_payload = kwargs["json"]
            return FakeResponse()

        with patch("backend.chat.kb_chat.requests.post", side_effect=fake_post):
            documents = await service.retrieve_documents(
                "论文的结论是什么",
                "kb-test",
                "http://localhost:8000",
                top_k=10,
                score_threshold=0.1,
            )

        self.assertEqual(captured_payload["top_k"], 50)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["metadata"]["chunk_index"], 37)
        self.assertTrue(all(document["section_boost"] > 0 for document in documents))


class MultiQueryProvenanceTests(unittest.TestCase):
    def test_rrf_preserves_raw_dense_score_after_section_scoring(self):
        """AC-401.4: RRF keeps dense provenance, not the boosted score."""
        document = hit(7, 0.60, "**3 Model Architecture** evidence")
        document["retrieval_score"] = 0.18

        fused = _query_rrf({"original": [document]})

        self.assertEqual(fused[0]["retrieval_score"], 0.18)


if __name__ == "__main__":
    unittest.main()
