import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from backend.chat.document_scope import resolve_document_scope
from backend.chat.kb_chat import ChatRequest, ChatService
from backend.chat.multi_query_retrieval import parse_query_plan, single_query_plan

CATALOG = [
    {'filename': '1706.03762_attention-is-all-you-need.pdf', 'file_id': 'file-attention'},
    {'filename': '1810.04805_bert.pdf', 'file_id': 'file-bert'},
    {'filename': '2106.09685_lora.pdf', 'file_id': 'file-lora'},
]


def hit(paper):
    doc = next(d for d in CATALOG if d['file_id'] == 'file-' + paper)
    return dict(doc, score=.8, chunk_text=paper, metadata={'chunk_id': paper})


def request(query, **kwargs):
    return ChatRequest(query=query, collection_name='test-scope', stream=False,
                       llm_config=dict(api_url='https://example.invalid', api_key='test', model_name='test'),
                       **kwargs)


class DocumentScopeTests(unittest.TestCase):
    # AC-2901 / AC-2904 / AC-2905
    def test_frozen_failure_questions_select_one_paper(self):
        for query, fid in [
            ('仅依据 Attention Is All You Need：论文报告的 GPT-4 在 MMLU 上的准确率是多少？', 'file-attention'),
            ('仅依据 BERT 论文：BERT 在 GPT-4 发布后的 MMLU 对比实验中取得多少分？', 'file-bert'),
            ('LoRA 摘要中，相比使用 Adam 全量微调 GPT-3 175B，显存减少多少倍？', 'file-lora'),
        ]:
            with self.subTest(query=query):
                scope = resolve_document_scope(query, CATALOG)
                self.assertEqual(scope.status, 'resolved')
                self.assertEqual(scope.file_ids, (fid,))

    def test_paper_local_comparison_overrides_mentioned_baseline_paper(self):
        scope = resolve_document_scope('仅依据 LoRA 论文：与 BERT 的参数配置比较是什么？', CATALOG)
        self.assertEqual(scope.file_ids, ('file-lora',))

    def test_true_cross_paper_comparison_keeps_both(self):
        scope = resolve_document_scope('比较 BERT 与 LoRA 的微调参数。', CATALOG)
        self.assertEqual(set(scope.file_ids), {'file-bert', 'file-lora'})

    def test_unknown_comparison_target_does_not_become_single_paper(self):
        scope = resolve_document_scope('比较 BERT 与 Unknown Study 的方法。', CATALOG)
        self.assertEqual(scope.status, 'unresolved')

    def test_history_switch_ignores_explicitly_excluded_old_paper(self):
        scope = resolve_document_scope('现在切换到 LoRA 论文：A、B 如何初始化？不要回答上一轮 BERT 的配置。', CATALOG)
        self.assertEqual(scope.file_ids, ('file-lora',))

    def test_substrings_are_not_paper_aliases(self):
        self.assertEqual(resolve_document_scope('RoBERTa 如何训练？', CATALOG).status, 'unrestricted')
        self.assertEqual(resolve_document_scope('all these papers summarize attention mechanisms', CATALOG).status, 'unrestricted')

    def test_unknown_restricted_paper_does_not_fall_back_to_general(self):
        self.assertEqual(resolve_document_scope('仅依据《Unknown Study》：结论是什么？', CATALOG).status, 'unresolved')

    def test_restriction_can_name_two_papers_and_must_not_drop_unknown_title(self):
        both = resolve_document_scope('仅依据《BERT》和《LoRA》：比较方法。', CATALOG)
        self.assertEqual(set(both.file_ids), {'file-bert', 'file-lora'})
        missing = resolve_document_scope('仅依据《BERT》和《Unknown Study》：比较方法。', CATALOG)
        self.assertEqual(missing.status, 'unresolved')

    def test_generic_in_prefix_is_not_an_unknown_document_restriction(self):
        self.assertEqual(resolve_document_scope('在深度学习中，什么是正则化？', CATALOG).status, 'unrestricted')

    def test_collection_demonstratives_are_not_unknown_paper_names(self):
        for query in ('根据这些论文总结方法。', '仅依据知识库中的论文回答。', 'According to these papers, summarize methods.'):
            with self.subTest(query=query):
                self.assertEqual(resolve_document_scope(query, CATALOG).status, 'unrestricted')

    def test_duplicate_alias_is_ambiguous_but_exact_filename_resolves(self):
        docs = CATALOG + [{'filename': 'new_bert.pdf', 'file_id': 'other'}]
        # Same semantic alias from a provided title, not a hard-coded lookup.
        docs[-1]['title'] = 'BERT'
        self.assertEqual(resolve_document_scope('BERT 的方法是什么？', docs).status, 'ambiguous')
        self.assertEqual(resolve_document_scope('1810.04805_bert.pdf 的方法？', docs).file_ids, ('file-bert',))

    def test_id_is_authoritative_and_filename_is_escaped_for_legacy(self):
        scope = resolve_document_scope('BERT 的方法？', CATALOG)
        self.assertIn('file_id in ["file-bert"]', scope.filter_expr)
        self.assertFalse(scope.allows(dict(hit('bert'), file_id='wrong')))
        docs = [{'filename': 'paper"quoted.pdf'}]
        legacy = resolve_document_scope('paper"quoted.pdf', docs)
        self.assertIn('paper\\"quoted.pdf', legacy.filter_expr)
        self.assertTrue(legacy.allows({'filename': 'paper"quoted.pdf'}))


class ScopeRetrievalTests(unittest.IsolatedAsyncioTestCase):
    # AC-2902 / AC-2903 / AC-2904 / AC-2905
    def service(self):
        service = ChatService()
        service.list_collection_documents = AsyncMock(return_value=CATALOG)
        service.plan_retrieval = AsyncMock(return_value=single_query_plan())
        service.retrieve_documents = AsyncMock(return_value=[hit('bert'), hit('lora'), hit('attention')])
        return service

    async def test_single_paper_scope_even_without_planner_filters_and_guards_hits(self):
        for multi in (False, True):
            service = self.service()
            result = await service.retrieve_for_request(request('仅依据 BERT 论文：方法是什么？', use_multi_query=multi))
            service.plan_retrieval.assert_not_awaited()
            self.assertEqual([d['file_id'] for d in result.documents], ['file-bert'])
            self.assertIn('file_id in ["file-bert"]', service.retrieve_documents.call_args.kwargs['filter_expr'])
            self.assertEqual(result.trace['document_scope']['dropped_candidates'], 2)

    async def test_comparison_filters_original_union_and_each_target(self):
        service = self.service()
        service.plan_retrieval.return_value = parse_query_plan(
            '{"intent":"comparison","subqueries":[{"id":"bert","target":"BERT","query":"BERT weights?"},'
            '{"id":"lora","target":"LoRA","query":"LoRA weights?"}]}', 'compare')
        result = await service.retrieve_for_request(request('比较 BERT 和 LoRA 的微调方式', use_multi_query=True))
        self.assertEqual({d['file_id'] for d in result.documents}, {'file-bert', 'file-lora'})
        self.assertEqual(result.trace['mode'], 'multi_query')
        filters = {c.kwargs['query']: c.kwargs['filter_expr'] for c in service.retrieve_documents.call_args_list}
        self.assertIn('file-bert', filters['比较 BERT 和 LoRA 的微调方式'])
        self.assertIn('file-lora', filters['比较 BERT 和 LoRA 的微调方式'])
        self.assertNotIn('file-lora', filters['BERT weights?'])
        self.assertNotIn('file-bert', filters['LoRA weights?'])

    async def test_failed_target_fallback_stays_in_original_scope(self):
        service = self.service()
        service.plan_retrieval.return_value = parse_query_plan(
            '{"intent":"comparison","subqueries":[{"id":"bert","target":"BERT","query":"BERT weights?"},'
            '{"id":"missing","target":"Unknown","query":"Unknown weights?"}]}', 'compare')
        result = await service.retrieve_for_request(request('比较 BERT 和 LoRA 的微调方式', use_multi_query=True))
        self.assertEqual({d['file_id'] for d in result.documents}, {'file-bert', 'file-lora'})
        self.assertEqual(result.trace['mode'], 'single_query_fallback')
        self.assertNotIn('Unknown weights?', [c.kwargs['query'] for c in service.retrieve_documents.call_args_list])

    async def test_planner_failure_does_not_expand_scope(self):
        service = self.service()
        service.plan_retrieval.return_value = single_query_plan('planner_timeout')
        result = await service.retrieve_for_request(request('比较 BERT 与 LoRA', use_multi_query=True))
        self.assertEqual({d['file_id'] for d in result.documents}, {'file-bert', 'file-lora'})

    async def test_unknown_restriction_does_not_retrieve(self):
        service = self.service()
        result = await service.retrieve_for_request(request('仅依据《Missing Paper》总结'))
        self.assertEqual(result.documents, [])
        service.retrieve_documents.assert_not_awaited()
        self.assertEqual(result.trace['document_scope']['status'], 'unresolved')

    async def test_catalog_failure_does_not_silently_search_unfiltered(self):
        service = self.service()
        service.list_collection_documents.side_effect = RuntimeError('offline')
        with self.assertRaises(HTTPException) as raised:
            await service.retrieve_for_request(request('BERT 的方法'))
        self.assertEqual(raised.exception.status_code, 503)
        service.retrieve_documents.assert_not_awaited()

    async def test_catalog_error_survives_non_stream_http_error_mapping(self):
        service = self.service()
        service.list_collection_documents.side_effect = RuntimeError('offline')
        with self.assertRaises(HTTPException) as raised:
            await service.chat_non_stream(request('BERT 的方法'))
        self.assertEqual(raised.exception.status_code, 503)

    async def test_catalog_error_survives_route_and_stream(self):
        from backend.chat import kb_chat
        service = self.service()
        service.list_collection_documents.side_effect = RuntimeError('offline')
        with patch.object(kb_chat, 'service', service):
            with self.assertRaises(HTTPException) as raised:
                await kb_chat.chat(request('BERT 的方法'))
            self.assertEqual(raised.exception.status_code, 503)
        import json
        events = [json.loads(e) async for e in service.chat_stream(request('BERT 的方法'))]
        self.assertEqual([e['type'] for e in events], ['error'])

    async def test_malformed_catalog_cannot_masquerade_as_empty(self):
        service = ChatService()
        class BrokenResponse:
            status_code = 200
            def json(self):
                return {'status': 'success', 'documents': [{'filename': None}]}
        with patch('backend.chat.kb_chat.requests.get', return_value=BrokenResponse()):
            with self.assertRaises(HTTPException):
                await service.list_collection_documents('test-scope', 'http://example.invalid')

    async def test_general_question_remains_collection_wide(self):
        service = self.service()
        result = await service.retrieve_for_request(request('总结这些论文的研究结论'))
        self.assertEqual(len(result.documents), 3)
        self.assertIsNone(service.retrieve_documents.call_args.kwargs['filter_expr'])
