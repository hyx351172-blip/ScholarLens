"""No live Milvus, Embedding, generation or .env loading in these tests."""
import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.chat.kb_chat import ChatRequest, ChatService, SourceDocument, RerankerConfig
from backend.chat.multi_query_retrieval import _query_rrf
from tests.test_hybrid_search import document

MODULE_DIR = Path(__file__).resolve().parents[1] / 'backend/Database/milvus_server'
with patch('pymilvus.connections.connect'), patch('dotenv.load_dotenv', return_value=False), \
        patch.object(sys, 'path', [str(MODULE_DIR), *sys.path]), contextlib.redirect_stdout(io.StringIO()):
    spec = importlib.util.spec_from_file_location('hybrid_milvus_api_test', MODULE_DIR / 'milvus_api.py')
    milvus = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(milvus)


def row(cid, text):
    value = document(cid, text)
    value['metadata'] = '{"chunk_id": "' + cid + '"}'
    return value


class MilvusHybridTests(unittest.TestCase):
    def setUp(self):
        self.service = milvus.MilvusRAGService.__new__(milvus.MilvusRAGService)
        self.service.generate_embedding = Mock(return_value=[.1, .2])
        self.collection = Mock()
        self.iterator = Mock()
        self.collection.query_iterator.return_value = self.iterator
        self.collection.search.return_value = [[Mock(id='a', score=.8, entity={
            'chunk_text': 'semantic', 'filename': 'paper.pdf', 'file_id': 'paper.pdf',
            'metadata': '{"chunk_id":"a"}', 'created_at': ''})]]
        self.utility_patch = patch.object(milvus.utility, 'has_collection', return_value=True)
        self.collection_patch = patch.object(milvus, 'Collection', return_value=self.collection)
        self.utility_patch.start()
        self.collection_patch.start()
        self.addCleanup(self.utility_patch.stop)
        self.addCleanup(self.collection_patch.stop)

    # AC-5101
    def test_default_dense_does_not_scan_or_change_score(self):
        result = self.service.search_by_text('kb', 'term')
        self.assertEqual(result[0]['score'], .8)
        self.collection.query_iterator.assert_not_called()
        self.assertEqual(milvus.SearchRequest(collection_name='kb', query_text='term').retrieval_mode, 'dense')
        for kwargs in [{'retrieval_mode': 'bad'}, {'hybrid_candidate_k': 0}, {'top_k': 0}]:
            with self.assertRaises(ValidationError):
                milvus.SearchRequest(collection_name='kb', query_text='term', **kwargs)

    # AC-5104 / AC-5103
    def test_independent_scoped_bm25_and_dense_filter(self):
        self.iterator.next.side_effect = [[row('a', 'semantic'), row('b', 'rarekey')], []]
        result = self.service.search_by_text('kb', 'rarekey', top_k=2,
            filter_expr='file_id == "paper.pdf"', retrieval_mode='hybrid',
            hybrid_candidate_k=3, dense_score_threshold=.9)
        self.assertEqual([d['id'] for d in result], ['b'])
        self.assertIsNone(result[0]['dense_score'])
        self.assertEqual(self.collection.query_iterator.call_args.kwargs['expr'], 'file_id == "paper.pdf"')
        self.assertEqual(self.collection.search.call_args.kwargs['expr'], 'file_id == "paper.pdf"')
        self.assertEqual(self.collection.search.call_args.kwargs['limit'], 3)
        self.assertEqual(self.collection.search.call_args.kwargs['consistency_level'], 'Strong')
        self.iterator.close.assert_called_once()

    def test_empty_scope_no_embedding_and_no_stale_upload_delete_cache(self):
        self.iterator.next.side_effect = [[row('b', 'rarekey')], [], []]
        first = self.service.search_by_text('kb', 'rarekey', retrieval_mode='hybrid')
        second = self.service.search_by_text('kb', 'rarekey', retrieval_mode='hybrid')
        self.assertTrue(first)
        self.assertEqual(second, [])
        self.assertEqual(self.service.generate_embedding.call_count, 1)
        self.assertEqual(self.iterator.close.call_count, 2)

    def test_iterator_error_and_corpus_limit_fail_without_paid_call(self):
        self.iterator.next.side_effect = RuntimeError('iterator unavailable')
        with self.assertRaises(HTTPException):
            self.service.search_by_text('kb', 'rarekey', retrieval_mode='hybrid')
        self.iterator.close.assert_called_once()
        self.service.generate_embedding.assert_not_called()
        self.iterator.reset_mock()
        self.iterator.next.side_effect = [[row('a', 'a'), row('b', 'b')]]
        with patch.object(milvus, 'HYBRID_MAX_CHUNKS', 1), self.assertRaises(HTTPException) as error:
            self.service.search_by_text('kb', 'term', retrieval_mode='hybrid')
        self.assertEqual(error.exception.status_code, 413)
        self.iterator.close.assert_called_once()
        self.service.generate_embedding.assert_not_called()

    def test_missing_collection_preserves_404(self):
        with patch.object(milvus.utility, 'has_collection', return_value=False), \
                self.assertRaises(HTTPException) as error:
            self.service.search_by_text('missing', 'term', retrieval_mode='hybrid')
        self.assertEqual(error.exception.status_code, 404)
        self.service.generate_embedding.assert_not_called()

    def test_scan_timeout_and_text_limit_close_before_embedding(self):
        self.iterator.next.side_effect = [[row('a', 'rarekey')], []]
        with patch.object(milvus, 'HYBRID_MAX_TEXT_BYTES', 1), self.assertRaises(HTTPException) as error:
            self.service.search_by_text('kb', 'rarekey', retrieval_mode='hybrid')
        self.assertEqual(error.exception.status_code, 413)
        self.iterator.close.assert_called_once()
        self.iterator.reset_mock()
        with patch.object(milvus.time, 'monotonic', side_effect=[0, 16]), self.assertRaises(HTTPException) as error:
            self.service.search_by_text('kb', 'rarekey', retrieval_mode='hybrid')
        self.assertEqual(error.exception.status_code, 503)
        self.iterator.close.assert_called_once()
        self.service.generate_embedding.assert_not_called()

    def test_hybrid_k_is_bounded_but_dense_large_k_is_compatible(self):
        self.assertEqual(milvus.SearchRequest(collection_name='kb', query_text='q', top_k=1000).top_k, 1000)
        with self.assertRaises(HTTPException) as error:
            self.service.search_by_text('kb', 'q', top_k=501, retrieval_mode='hybrid')
        self.assertEqual(error.exception.status_code, 422)
        self.service.generate_embedding.assert_not_called()

    def test_live_dense_row_not_in_snapshot_is_discarded(self):
        self.iterator.next.side_effect = [[row('b', 'rarekey')], []]
        result = self.service.search_by_text('kb', 'rarekey', retrieval_mode='hybrid')
        self.assertEqual([d['id'] for d in result], ['b'])


class ChatHybridTests(unittest.IsolatedAsyncioTestCase):
    # AC-5101 / AC-5105
    def request(self, **kwargs):
        return ChatRequest(query='rarekey', collection_name='kb', stream=False,
            llm_config=dict(api_url='https://example.invalid', api_key='test', model_name='test'), **kwargs)

    async def test_low_rrf_survives_cosine_threshold_and_dense_payload_unchanged(self):
        hit = document('b', 'rarekey', score=1/61, score_type='hybrid_rrf',
                       retrieval_mode='hybrid', hybrid_rrf_score=1/61,
                       dense_score=None, bm25_score=3, branch_ranks={'bm25': 1})
        response = Mock(status_code=200)
        response.json.return_value = {'status': 'success', 'results': [hit]}
        with patch('backend.chat.kb_chat.requests.post', return_value=response) as post:
            docs = await ChatService().retrieve_documents('rarekey', 'kb', 'http://example.invalid',
                top_k=2, retrieval_mode='hybrid', score_threshold=.9)
            self.assertEqual(len(docs), 1)
            self.assertEqual(post.call_args.kwargs['json']['dense_score_threshold'], .9)
            self.assertEqual(post.call_args.kwargs['json']['retrieval_mode'], 'hybrid')
            await ChatService().retrieve_documents('rarekey', 'kb', 'http://example.invalid')
            self.assertNotIn('retrieval_mode', post.call_args.kwargs['json'])
        self.assertEqual(self.request().retrieval_mode, 'dense')

    async def test_hybrid_wrong_contract_fails_closed(self):
        response = Mock(status_code=200)
        response.json.return_value = {'status': 'success', 'results': [document('a', 'a', score=.8)]}
        with patch('backend.chat.kb_chat.requests.post', return_value=response), self.assertRaises(HTTPException):
            await ChatService().retrieve_documents('term', 'kb', 'http://example.invalid', retrieval_mode='hybrid')

    async def test_mode_reaches_scoped_retrieval(self):
        service = ChatService()
        with patch.object(service, 'list_collection_documents', new=AsyncMock(return_value=[])), \
             patch.object(service, 'retrieve_documents', new=AsyncMock(return_value=[])) as retrieve:
            execution = await service.retrieve_for_request(self.request(retrieval_mode='hybrid'))
        self.assertEqual(retrieve.call_args.kwargs['retrieval_mode'], 'hybrid')
        self.assertEqual(execution.trace['retrieval_mode'], 'hybrid')

    def test_query_fusion_and_source_keep_hybrid_provenance(self):
        hit = document('b', 'rarekey', score=1/61, score_type='hybrid_rrf',
                       retrieval_mode='hybrid', hybrid_rrf_score=1/61, dense_score=None,
                       bm25_score=3, branch_ranks={'bm25': 1})
        fused = _query_rrf({'original': [hit], 'q1': [hit]})
        self.assertEqual(fused[0]['hybrid_rrf_score'], 1/61)
        self.assertEqual(fused[0]['score_type'], 'query_rrf')
        source = SourceDocument(**fused[0]).model_dump()
        self.assertEqual(source['bm25_score'], 3)
        self.assertEqual(source['hybrid_rrf_score'], 1/61)
        self.assertEqual(source['branch_ranks'], {'bm25': 1})

    async def test_optional_reranker_marks_new_score_and_retains_branches(self):
        hit = document('b', 'rarekey', score=1/61, score_type='hybrid_rrf',
                       retrieval_mode='hybrid', hybrid_rrf_score=1/61, dense_score=.4,
                       bm25_score=3, branch_ranks={'dense': 2, 'bm25': 1})
        response = Mock()
        response.json.return_value = {'results': [{'index': 0, 'relevance_score': .9}]}
        client = AsyncMock()
        client.post.return_value = response
        config = RerankerConfig(api_url='https://example.invalid', api_key='test', model_name='jina-test')
        with patch('httpx.AsyncClient') as factory:
            factory.return_value.__aenter__.return_value = client
            hits = await ChatService().rerank_documents('rarekey', [hit], config)
        self.assertEqual(hits[0]['score_type'], 'reranker')
        self.assertEqual(hits[0]['score'], .9)
        self.assertEqual(hits[0]['dense_score'], .4)
        self.assertEqual(hits[0]['bm25_score'], 3)

    def test_context_does_not_call_small_rrf_similarity(self):
        hit = document('b', 'rarekey', score=1/61, retrieval_mode='hybrid')
        context = ChatService().format_context([hit])
        self.assertIn('[S1]', context)
        self.assertIn('检索方式: Hybrid', context)
        self.assertNotIn('相关度:', context)
        self.assertIn('相关度: 0.800', ChatService().format_context([document('a', 'text', score=.8)]))


class SearchEndpointTests(unittest.TestCase):
    # AC-5101 / AC-5104
    def test_http_validates_and_propagates_mode_and_preserves_errors(self):
        client = TestClient(milvus.app)
        payload = dict(collection_name='kb', query_text='rarekey', retrieval_mode='hybrid',
                       filter_expr='file_id == "a"', top_k=2, dense_score_threshold=.1)
        with patch.object(milvus.milvus_service, 'search_by_text', return_value=[]) as search, \
                patch.object(milvus.asyncio, 'to_thread', wraps=milvus.asyncio.to_thread) as worker:
            response = client.post('/search', json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(search.call_args.kwargs['retrieval_mode'], 'hybrid')
            self.assertEqual(search.call_args.kwargs['filter_expr'], payload['filter_expr'])
            invalid = client.post('/search', json=dict(payload, retrieval_mode='unknown'))
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(search.call_count, 1)
            self.assertEqual(worker.call_count, 1)
        with patch.object(milvus.milvus_service, 'search_by_text', side_effect=HTTPException(413, 'too large')):
            self.assertEqual(client.post('/search', json=payload).status_code, 413)


if __name__ == '__main__':
    unittest.main()
