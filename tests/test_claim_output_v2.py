import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from backend.chat import claim_bound_answer as v1
from backend.chat import claim_bound_output_v2 as v2
from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from backend.chat.kb_chat import app, ChatRequest, ChatService
from backend.chat.multi_query_retrieval import RetrievalExecution


DOCS=[dict(source_id='S1',filename='a.pdf',chunk_text='Score 28.4; score 41.8.',score=1,metadata={})]
CATALOG=v1.build_catalog(DOCS)


def raw(text='结果为28.4；另一个结果为41.8。',ids=None):
    return json.dumps(dict(status='answered',claims=[dict(text=text,evidence_ids=ids if ids is not None else ['S1:E0001'])]))


class ClauseTests(unittest.TestCase):
    # AC-3601
    def test_semicolon_clauses_preserve_text_and_ids(self):
        for text in ('结果为28.4；另一个结果为41.8。','Score 28.4; another score 41.8.',
                     '选中后80%遮蔽；10%随机替换；10%保持不变。'):
            answer,meta=v2.render_claim_answer(raw(text),CATALOG)
            self.assertEqual(meta['status'],'claim_bound_passed')
            self.assertEqual(meta['version'],'claim_bound_v2')
            self.assertFalse(meta['semantic_verified'])
            self.assertEqual(answer,text+' [S1]')
            self.assertEqual(meta['claims'][0]['text'],text)
            self.assertEqual(meta['claims'][0]['evidence'][0]['anchor_id'],'S1:E0001')
            self.assertEqual(meta['warnings'],[dict(claim_id='C001',code='compound_clause')])

    def test_math_semicolon_not_a_prose_warning(self):
        text=r'使用 $f(x;y)$，见 Fig. 2，数值为28.4。'
        answer,meta=v2.render_claim_answer(raw(text),CATALOG)
        self.assertEqual(answer,text+' [S1]');self.assertEqual(meta['warnings'],[])

    def test_no_partial_recovery_when_sibling_has_bad_citation(self):
        obj=json.loads(raw());obj['claims'].append(dict(text='MUST_NOT_LEAK',evidence_ids=['S999:E0001']))
        answer,meta=v2.render_claim_answer(json.dumps(obj),CATALOG)
        self.assertEqual(answer,v2.CLAIM_FORMAT_ERROR);self.assertEqual(meta['claims'],[])
        self.assertEqual(meta['warnings'],[]);self.assertNotIn('MUST_NOT_LEAK',json.dumps(meta))


class ContractParityTests(unittest.TestCase):
    # AC-3602
    def test_invalid_evidence_ids_still_fail_closed(self):
        for ids in ([],['S99:E0001'],['S1:E9999'],['S1:E0001']*2,[True],'S1:E0001'):
            answer,meta=v2.render_claim_answer(raw(ids=ids),CATALOG)
            self.assertEqual(answer,v2.CLAIM_FORMAT_ERROR)
            self.assertEqual(meta['status'],'invalid_claim_structure')

    def test_bad_text_and_envelopes_still_rejected(self):
        values=[raw(t) for t in ('First.Second.','A. B; C.','一。二；三。','A\nB','A\u2028B',
            'A\x00B','事实 [S99]','- list','```code```','<b>x</b>')]
        values+=['['*1500+']'*1500,raw()+'tail','```json\n'+raw()+'\n```',
            '{"status":"answered","status":"answered","claims":[]}',
            '{"status":"answered","claims":NaN}',raw('x'*1201)]
        for value in values:
            answer,meta=v2.render_claim_answer(value,CATALOG)
            self.assertEqual(answer,v2.CLAIM_FORMAT_ERROR)
            self.assertEqual(meta['status'],'invalid_claim_structure')

    def test_v1_is_unchanged_and_simple_v2_answer_is_identical(self):
        self.assertEqual(v1.render_claim_answer(raw(),CATALOG)[1]['status'],'invalid_claim_structure')
        simple=raw('数值为28.4。')
        self.assertEqual(v1.render_claim_answer(simple,CATALOG)[0],v2.render_claim_answer(simple,CATALOG)[0])

    def test_extra_fields_duplicates_and_limits_are_not_relaxed(self):
        base=json.loads(raw('有效结论。'));values=[]
        for field in ('quote','source_ids','intro','reason'):
            obj=copy.deepcopy(base);obj['claims'][0][field]='not allowed';values.append(json.dumps(obj))
        duplicate=copy.deepcopy(base);duplicate['claims']*=2;values.append(json.dumps(duplicate))
        many=copy.deepcopy(base);many['claims']=[dict(text=f'row{i}',evidence_ids=['S1:E0001']) for i in range(21)]
        values.extend((json.dumps(many),'x'*40001,'{"status":"answered","claims":[]}',
            '{"status":"insufficient","claims":[],"extra":true}'))
        for value in values:
            self.assertEqual(v2.render_claim_answer(value,CATALOG)[1]['status'],'invalid_claim_structure')


class FailureTests(unittest.TestCase):
    # AC-3603
    def test_insufficient_and_invalid_output_have_distinct_messages(self):
        insufficient=json.dumps(dict(status='insufficient',claims=[]))
        answer,meta=v2.render_claim_answer(insufficient,CATALOG)
        self.assertEqual(answer,INSUFFICIENT_EVIDENCE)
        self.assertEqual(meta['status'],'claim_bound_insufficient')
        self.assertEqual(v2.render_claim_answer('{}',CATALOG)[0],v2.CLAIM_FORMAT_ERROR)
        self.assertEqual(len({INSUFFICIENT_EVIDENCE,v2.CLAIM_FORMAT_ERROR,
            v2.CLAIM_EVIDENCE_ERROR,v2.CLAIM_GENERATION_ERROR}),4)


class ApiTests(unittest.TestCase):
    # AC-3603 / AC-3604: real ASGI route; only external work stubbed.
    def request(self):
        return ChatRequest(query='q',collection_name='test',answer_mode='claim_bound',
            llm_config=dict(api_url='https://example.invalid',api_key='TEST_SECRET',model_name='test')).model_dump()

    def invoke(self,case,stream):
        svc=ChatService();docs=copy.deepcopy(DOCS)
        if case=='empty':docs=[]
        if case=='oversized':docs[0]['chunk_text']='x'*120001
        svc.retrieve_for_request=AsyncMock(return_value=RetrievalExecution(documents=docs,trace={}))
        svc.call_llm_claims=AsyncMock(return_value='{}' if case=='bad_json' else raw())
        if case=='incomplete':svc.call_llm_claims.side_effect=ValueError('untrusted_error_text')
        svc.call_llm_non_stream=AsyncMock(side_effect=AssertionError('no free text fallback'))
        payload=self.request();payload.update(stream=stream,return_source=False)
        with patch('backend.chat.kb_chat.service',svc),TestClient(app) as client:
            result=client.post('/chat',json=payload)
        self.assertEqual(result.status_code,200)
        self.assertNotIn('TEST_SECRET',result.text);self.assertNotIn('untrusted_error_text',result.text)
        svc.call_llm_non_stream.assert_not_awaited()
        self.assertEqual(svc.call_llm_claims.await_count,0 if case in ('empty','oversized') else 1)
        if stream:
            events=[json.loads(line) for line in result.text.splitlines()]
            return next(e['data'] for e in events if e['type']=='content'),next(e['data'] for e in events if e['type']=='metadata')
        r=result.json();self.assertIsNone(r['sources']);return r['answer'],r['metadata']

    def test_all_messages_and_metadata_consistent_between_response_modes(self):
        for case,status,text in (
            ('valid','claim_bound_passed','结果为28.4；另一个结果为41.8。 [S1]'),
            ('bad_json','invalid_claim_structure',v2.CLAIM_FORMAT_ERROR),
            ('oversized','invalid_claim_evidence',v2.CLAIM_EVIDENCE_ERROR),
            ('incomplete','incomplete_claim_generation',v2.CLAIM_GENERATION_ERROR),
            ('empty','no_evidence',INSUFFICIENT_EVIDENCE)):
            with self.subTest(case=case):
                a,ma=self.invoke(case,False);b,mb=self.invoke(case,True)
                self.assertEqual(a,text);self.assertEqual(b,text)
                self.assertEqual(ma['answer_guard'],status);self.assertEqual(mb['answer_guard'],status)
                self.assertEqual(ma.get('citation_binding'),mb.get('citation_binding'))
                if case!='empty':self.assertEqual(ma['citation_binding']['version'],'claim_bound_v2')

    def test_legacy_default_untouched(self):
        payload=self.request();payload.pop('answer_mode')
        self.assertEqual(ChatRequest(**payload).answer_mode,'legacy')


class ReplayTests(unittest.TestCase):
    # AC-3605: deterministic minimal regression; real cached responses tested offline separately.
    def test_number_comparison_and_attention_comparison_preserve_whole_output(self):
        texts=['表中数值为41.8。','正文为41.0；表格为41.8。']
        obj=dict(status='answered',claims=[dict(text=t,evidence_ids=['S1:E0001']) for t in texts])
        original=json.dumps(obj);before,mb=v1.render_claim_answer(original,CATALOG)
        after,ma=v2.render_claim_answer(original,CATALOG)
        self.assertEqual(mb['status'],'invalid_claim_structure')
        self.assertEqual([c['text'] for c in ma['claims']],texts)
        self.assertEqual(after,'\n\n'.join(t+' [S1]' for t in texts))
        self.assertEqual(ma['warnings'],[dict(claim_id='C002',code='compound_clause')])


if __name__=='__main__':unittest.main()
