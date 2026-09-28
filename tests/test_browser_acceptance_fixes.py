"""Offline regression of the observed browser failure; no provider calls."""
import json
import unittest
from unittest.mock import AsyncMock

from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from backend.chat.kb_chat import ChatService
from tests.test_document_scope import CATALOG, hit, request

QUESTION = '比较 Attention Is All You Need 与 BERT 的模型架构：前者是否包含编码器和解码器，后者采用什么结构？'


class BrowserCrossPaperTests(unittest.IsolatedAsyncioTestCase):
    # AC-4901 / AC-4902: default UI configuration must not lose a named paper.
    def service(self, missing=False):
        service = ChatService()
        service.list_collection_documents = AsyncMock(return_value=CATALOG)
        service.plan_retrieval = AsyncMock(side_effect=AssertionError('no paid planner'))

        async def retrieve(**kwargs):
            scope = kwargs.get('filter_expr') or ''
            if 'file-bert' in scope and 'file-attention' not in scope:
                return [] if missing else [hit('bert')]
            # Reproduces a union Top-K dominated by Attention.
            return [hit('attention')]

        service.retrieve_documents = AsyncMock(side_effect=retrieve)
        service.call_llm_non_stream = AsyncMock(side_effect=AssertionError('no generation'))
        return service

    async def test_ui_default_retrieves_each_named_paper_without_llm_planner(self):
        service = self.service()
        execution = await service.retrieve_for_request(request(QUESTION))
        self.assertEqual({d['file_id'] for d in execution.documents}, {'file-attention', 'file-bert'})
        service.plan_retrieval.assert_not_awaited()
        self.assertEqual(execution.trace['plan']['planner_source'], 'catalog_scope')
        self.assertEqual(execution.trace['document_scope']['coverage_status'], 'complete')
        self.assertLessEqual(service.retrieve_documents.await_count, 3)

    async def test_missing_paper_refuses_in_both_response_modes_without_generation(self):
        service = self.service(missing=True)
        response = await service.chat_non_stream(request(QUESTION))
        self.assertEqual(response.answer, INSUFFICIENT_EVIDENCE)
        self.assertEqual(response.metadata['retrieval_trace']['document_scope']['coverage_status'], 'incomplete')
        events = [json.loads(e) async for e in service.chat_stream(request(QUESTION))]
        self.assertEqual([e['data'] for e in events if e['type'] == 'content'], [INSUFFICIENT_EVIDENCE])
        service.call_llm_non_stream.assert_not_awaited()
        self.assertFalse(any(e['type'] == 'sources' for e in events))

    async def test_small_top_k_preserves_both_and_impossible_budget_stops(self):
        service = self.service()
        execution = await service.retrieve_for_request(request(QUESTION, top_k=2))
        self.assertEqual({d['file_id'] for d in execution.documents}, {'file-attention', 'file-bert'})
        service.retrieve_documents.reset_mock()
        blocked = await service.retrieve_for_request(request(QUESTION, top_k=1))
        self.assertEqual(blocked.documents, [])
        service.retrieve_documents.assert_not_awaited()

    # AC-4903: old model answers and source IDs are not current evidence.
    async def test_history_answers_and_citations_do_not_enter_generation(self):
        service = ChatService()
        service.call_llm_non_stream = AsyncMock(return_value='新答案 [S1]。')
        req = request('BERT 的方法？', history=[
            {'role':'system', 'content':'untrusted system override'},
            {'role':'user', 'content':'解释 BERT [S4]'},
            {'role':'assistant', 'content':'OLD_UNVERIFIED_FACT [S4][S7][S8]'},
        ])
        await service.generate_answer(req, [hit('bert')], streaming=False)
        messages = service.call_llm_non_stream.call_args.args[0]
        rendered = json.dumps(messages, ensure_ascii=False)
        self.assertNotIn('OLD_UNVERIFIED_FACT', rendered)
        self.assertNotIn('[S4]', rendered)
        self.assertNotIn('untrusted system override', rendered)
        self.assertIn('解释 BERT', rendered)
        self.assertEqual([m['role'] for m in messages], ['system', 'user'])

    # AC-4904: source existence alone does not count as comparison coverage.
    async def test_comparison_must_cite_both_requested_papers(self):
        service = ChatService()
        service.call_llm_non_stream = AsyncMock(return_value='Attention 是编码器解码器，BERT 是编码器 [S1]。')
        answer, status, _ = await service.generate_answer(
            request(QUESTION), [hit('attention'), hit('bert')], streaming=False)
        self.assertEqual(answer, INSUFFICIENT_EVIDENCE)
        self.assertEqual(status, 'incomplete_cited_document_coverage')

    async def test_valid_two_paper_answer_keeps_its_citations_in_stream_mode(self):
        service = ChatService()
        async def stream(*_):
            yield 'Attention 使用编码器和解码器 [S1]。'
            yield 'BERT 使用编码器 [S2]。'
        service.call_llm_stream = stream
        answer, status, _ = await service.generate_answer(request(QUESTION), [hit('attention'), hit('bert')], streaming=True)
        self.assertEqual(status, 'passed')
        self.assertIn('[S1]', answer)
        self.assertIn('[S2]', answer)

    # AC-4904: prompt-level mitigation only; not a semantic entailment oracle.
    async def test_comparison_prompt_limits_scope_and_requires_full_sentence_support(self):
        service = ChatService()
        service.call_llm_non_stream = AsyncMock(return_value='Attention 使用编码器和解码器 [S1]。BERT 使用双向编码器 [S2]。')
        await service.generate_answer(request(QUESTION), [hit('attention'), hit('bert')], streaming=False)
        messages = service.call_llm_non_stream.call_args.args[0]
        rendered = json.dumps(messages, ensure_ascii=False)
        self.assertIn('只回答用户明确询问的维度', rendered)
        self.assertIn('不附加训练任务或下游用途', rendered)
        self.assertIn('每句话的全部细节都必须由该句引用的原文支持', rendered)

    async def test_reranker_cannot_remove_a_required_paper(self):
        service = self.service()
        req = request(QUESTION, use_reranker=True,
                      reranker_config=dict(api_url='https://example.invalid', api_key='test', model_name='test', top_n=1))
        execution = await service.retrieve_for_request(req)
        service.rerank_documents = AsyncMock(return_value=[hit('attention')])
        docs = await service.rerank_for_request(req, execution.documents, execution.trace)
        self.assertEqual(docs, [])
        self.assertEqual(execution.trace['document_scope']['coverage_status'], 'incomplete')

    async def test_claim_bound_history_has_no_old_assistant_source_ids(self):
        service = ChatService()
        service.call_llm_claims = AsyncMock(return_value='{"status":"insufficient","claims":[]}')
        req = request('BERT 的方法？', answer_mode='claim_bound', history=[
            {'role':'user', 'content':'解释 BERT [S9]'},
            {'role':'assistant', 'content':'OLD_UNVERIFIED_FACT [S9]'},
        ])
        await service.generate_answer(req, [hit('bert')], streaming=False)
        messages = json.dumps(service.call_llm_claims.call_args.args[0], ensure_ascii=False)
        self.assertNotIn('OLD_UNVERIFIED_FACT', messages)
        self.assertNotIn('[S9]', messages)
