import unittest
import json
from unittest.mock import AsyncMock
from backend.chat.kb_chat import ChatService, ChatRequest
from backend.chat.multi_query_retrieval import RetrievalExecution
from backend.chat.answer_guard import guard_answer, INSUFFICIENT_EVIDENCE


class AnswerGuardTests(unittest.TestCase):
    # AC-2201: malformed, unknown and missing citations fail closed.
    def test_bad_citations(self):
        for answer in ('结论 [S母公司]', '结论 [S99]', '结论 [S1] [S错误]', '结论 [S1', '结论'):
            with self.subTest(answer=answer):
                self.assertEqual(guard_answer(answer, 1)[0], INSUFFICIENT_EVIDENCE)

    # AC-2202: do not keep unsupported explanations attached to abstentions.
    def test_insufficient_answer_discards_external_fact(self):
        answer = '该论文未报告GPT-4在MMLU上的准确率 [S1]。GPT-4发布于2023年 [S1]。'
        self.assertEqual(guard_answer(answer, 1)[0], INSUFFICIENT_EVIDENCE)

    def test_good_answer_is_not_rewritten(self):
        answer = 'Transformer 得到28.4和41.8 [S1]。'
        self.assertEqual(guard_answer(answer, 1), (answer, 'passed'))

    def test_empty_evidence(self):
        self.assertEqual(guard_answer('invented [S1]', 0)[0], INSUFFICIENT_EVIDENCE)


class GuardIntegrationTests(unittest.IsolatedAsyncioTestCase):
    # AC-2203: both response modes enforce the same boundary before emission.
    async def test_stream_and_non_stream(self):
        request = ChatRequest(query='结论是什么', collection_name='test',
                              llm_config=dict(api_key='test', api_url='https://example.invalid', model_name='test'))
        docs = [dict(chunk_text='evidence', filename='paper.pdf', score=1.0, metadata={})]
        for raw in ('结论 [S母公司]', '论文未报告该值 [S1]。发布于2023年。', '正确结果 [S1]'):
            service = ChatService()
            service.retrieve_for_request = AsyncMock(return_value=RetrievalExecution(documents=docs, trace={}))
            service.call_llm_non_stream = AsyncMock(return_value=raw)
            async def fake_stream(*args):
                for char in raw:
                    yield char
            service.call_llm_stream = fake_stream
            response = await service.chat_non_stream(request)
            events = [json.loads(event) async for event in service.chat_stream(request)]
            visible = ''.join(event['data'] for event in events if event['type'] == 'content')
            self.assertEqual(visible, response.answer)
            self.assertEqual(visible, guard_answer(raw, 1)[0])
            self.assertEqual(service.call_llm_non_stream.call_args.args[0][0]['role'], 'system')

    # AC-2204: no evidence means no free-form model call.
    async def test_no_evidence_never_calls_model(self):
        service = ChatService()
        service.retrieve_for_request = AsyncMock(return_value=RetrievalExecution(documents=[], trace={}))
        service.call_llm_non_stream = AsyncMock(side_effect=AssertionError('must not call'))
        def forbidden(*args):
            raise AssertionError('must not call')
        service.call_llm_stream = forbidden
        request = ChatRequest(query='anything', collection_name='test',
                              llm_config=dict(api_key='test', api_url='https://example.invalid', model_name='test'))
        self.assertEqual((await service.chat_non_stream(request)).answer, INSUFFICIENT_EVIDENCE)
        events = [json.loads(event) async for event in service.chat_stream(request)]
        self.assertEqual(events[0]['data'], INSUFFICIENT_EVIDENCE)
