import asyncio
import threading
import time
import unittest
from unittest.mock import patch

from backend.chat.kb_chat import ChatRequest, ChatService
from backend.chat.multi_query_retrieval import RetrievalExecution, parse_query_plan


def _request(**updates):
    payload = {
        "query": "Compare Paper A and Paper B",
        "collection_name": "kb-test",
        "llm_config": {
            "api_url": "https://example.invalid/v1",
            "api_key": "test-only",
            "model_name": "test-model",
        },
        "stream": False,
    }
    payload.update(updates)
    return ChatRequest(**payload)


class ChatRequestMultiQueryTests(unittest.TestCase):
    def test_multi_query_is_disabled_by_default(self):
        request = _request()

        self.assertFalse(request.use_multi_query)
        self.assertEqual(request.multi_query_config.original_reserve, 4)
        self.assertEqual(request.multi_query_config.per_target_reserve, 2)


class ChatServiceMultiQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_enabled_request_uses_plan_and_returns_trace(self):
        service = ChatService()
        plan = parse_query_plan(
            '{"intent":"comparison","subqueries":['
            '{"id":"a","target":"Paper A","query":"Question A"},'
            '{"id":"b","target":"Paper B","query":"Question B"}]}' ,
            "Compare Paper A and Paper B",
        )

        async def fake_plan(*_args, **_kwargs):
            return plan

        async def fake_retrieve(query, **_kwargs):
            chunk_id = query.lower().replace(" ", "-")
            return [
                {
                    "score": 0.8,
                    "chunk_text": query,
                    "filename": f"{chunk_id}.pdf",
                    "metadata": {"chunk_id": chunk_id},
                }
            ]

        service.plan_retrieval = fake_plan
        service.retrieve_documents = fake_retrieve
        request = _request(
            use_multi_query=True,
            top_k=3,
            multi_query_config={
                "original_reserve": 1,
                "per_target_reserve": 1,
                "candidate_k_per_query": 3,
            },
        )

        execution = await service.retrieve_for_request(request)

        self.assertEqual(execution.trace["mode"], "multi_query")
        self.assertEqual(len(execution.documents), 3)

    async def test_http_retrieval_does_not_block_parallel_queries(self):
        service = ChatService()
        active = 0
        max_active = 0
        lock = threading.Lock()

        class FakeResponse:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return {"status": "success", "results": []}

        def fake_post(*_args, **_kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return FakeResponse()

        with patch("backend.chat.kb_chat.requests.post", side_effect=fake_post):
            await asyncio.gather(
                service.retrieve_documents("A", "kb", "http://localhost:8000"),
                service.retrieve_documents("B", "kb", "http://localhost:8000"),
            )

        self.assertEqual(max_active, 2)

    async def test_non_stream_response_exposes_retrieval_trace_and_provenance(self):
        service = ChatService()
        document = {
            "score": 0.03,
            "retrieval_score": 0.8,
            "query_rrf_score": 0.03,
            "matched_query_ids": ["original", "paper-a"],
            "query_ranks": {"original": 2, "paper-a": 1},
            "chunk_text": "evidence",
            "filename": "paper-a.pdf",
            "metadata": {"chunk_id": "chunk-a"},
        }
        trace = {"mode": "multi_query", "final_count": 1}

        async def fake_retrieve_for_request(_request):
            return RetrievalExecution(documents=[document], trace=trace)

        async def fake_answer(_messages, _config):
            return "grounded answer"

        service.retrieve_for_request = fake_retrieve_for_request
        service.call_llm_non_stream = fake_answer

        response = await service.chat_non_stream(_request(return_source=True))

        self.assertEqual(response.metadata["retrieval_trace"], trace)
        self.assertEqual(response.sources[0].matched_query_ids, ["original", "paper-a"])
        self.assertEqual(response.sources[0].query_ranks["paper-a"], 1)

    async def test_multi_query_reranker_cannot_truncate_coverage_context(self):
        service = ChatService()
        captured_top_n = None
        documents = [
            {
                "score": 0.5,
                "chunk_text": str(index),
                "filename": f"paper-{index}.pdf",
                "metadata": {"chunk_id": str(index)},
            }
            for index in range(3)
        ]

        async def fake_rerank(query, documents, reranker_config):
            nonlocal captured_top_n
            self.assertEqual(query, "Compare Paper A and Paper B")
            captured_top_n = reranker_config.top_n
            return documents

        service.rerank_documents = fake_rerank
        request = _request(
            use_reranker=True,
            reranker_config={
                "api_url": "https://example.invalid",
                "api_key": "test-only",
                "model_name": "test-reranker",
                "top_n": 1,
            },
        )

        reranked = await service.rerank_for_request(
            request,
            documents,
            {"mode": "multi_query"},
        )

        self.assertEqual(captured_top_n, 3)
        self.assertEqual(len(reranked), 3)


if __name__ == "__main__":
    unittest.main()
