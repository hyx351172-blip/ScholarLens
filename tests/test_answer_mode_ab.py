import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from backend.chat.claim_bound_output_v2 import CLAIM_FORMAT_ERROR
from tests.integration.compare_answer_modes import (
    IDS, MODES, PROTOCOL, make_inputs, pair_order, generate, packet, preflight, summarize,
    read, write, digest, load_live_config,
)


CASE = dict(id='A01', query='模型是什么？', documents=[dict(
    source_id='S1', filename='paper.pdf', chunk_text='The model is Transformer.', score=.9, metadata={})])


def response(content, finish='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish,
        message=SimpleNamespace(content=content, refusal=None))],
        usage=SimpleNamespace(model_dump=lambda:dict(prompt_tokens=100,completion_tokens=20,total_tokens=120)))


class PreparationTests(unittest.TestCase):
    # AC-3501
    def test_fixed_selection_and_no_expectations_in_input(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp)
            for cid in IDS:
                write(base/f'answer-{cid}.json',dict(query='q',expected='SECRET_GOLD',response=dict(
                    success=True,sources=[] if cid=='E01' else CASE['documents'])))
            inputs=make_inputs(base)
            self.assertEqual([c['id'] for c in inputs],list(IDS))
            self.assertNotIn('SECRET_GOLD',json.dumps(inputs))
            self.assertEqual(sum(bool(c['documents']) for c in inputs)*2,22)

    def test_bad_source_number_or_failed_baseline_rejected(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp)
            for cid in IDS:
                docs=copy.deepcopy(CASE['documents']);docs[0]['source_id']='S9'
                write(base/f'answer-{cid}.json',dict(query='q',response=dict(success=True,sources=docs)))
            with self.assertRaises(ValueError): make_inputs(base)

    def test_balanced_pair_order(self):
        pairs=pair_order([dict(CASE,id=cid) for cid in IDS])
        self.assertEqual(len(pairs),24)
        self.assertEqual([m for _,m in pairs[:4]],['legacy','claim_bound','claim_bound','legacy'])
        self.assertEqual(len(set((c['id'],m) for c,m in pairs)),24)


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    # AC-3502 / AC-3504 / AC-3506
    async def test_production_contract_and_exact_request_replay(self):
        for mode in MODES:
            p=await packet(CASE,mode)
            self.assertEqual(p['temperature'],0);self.assertEqual(p['max_tokens'],2000)
            self.assertEqual(p.get('response_format'), {'type':'json_object'} if mode=='claim_bound' else None)
            calls=[]
            async def provider(**kwargs):
                calls.append(kwargs)
                return response('Transformer [S1]' if mode=='legacy' else json.dumps(dict(status='answered',claims=[
                    dict(text='Transformer。',evidence_ids=['S1:E0001'])])))
            result=await generate(CASE,mode,p,provider)
            self.assertEqual(calls,[p]);self.assertIn('[S1]',result['answer'])
            self.assertEqual(result['usage']['total_tokens'],120)
            self.assertEqual(result['provider_calls'],1)

    async def test_no_sources_no_call(self):
        case=dict(CASE,documents=[])
        async def forbidden(**kwargs): raise AssertionError('no call')
        for mode in MODES:
            p=await packet(case,mode);self.assertIsNone(p)
            r=await generate(case,mode,p,forbidden)
            self.assertEqual(r['provider_calls'],0);self.assertEqual(r['answer'],INSUFFICIENT_EVIDENCE)

    async def test_new_guard_rejects_but_preserves_raw_response(self):
        p=await packet(CASE,'claim_bound')
        async def provider(**kwargs): return response('{"bad":"raw"}')
        r=await generate(CASE,'claim_bound',p,provider)
        self.assertEqual(r['guard_status'],'invalid_claim_structure')
        self.assertEqual(r['raw_content'],'{"bad":"raw"}')
        # Current production v2 message; the historical v1 file is archived before editing.
        self.assertEqual(r['answer'],CLAIM_FORMAT_ERROR)

    async def test_truncation_preserved_and_mode_specific_behavior_not_overridden(self):
        for mode in MODES:
            p=await packet(CASE,mode)
            async def provider(**kwargs): return response('Transformer [S1]','length')
            r=await generate(CASE,mode,p,provider)
            self.assertEqual(r['finish_reason'],'length')
            self.assertEqual(r['guard_status'],'passed' if mode=='legacy' else 'incomplete_claim_generation')

    async def test_errors_sanitized_no_retry(self):
        calls=[]
        async def provider(**kwargs): calls.append(1);raise RuntimeError('SECRET_API_KEY')
        r=await generate(CASE,'legacy',await packet(CASE,'legacy'),provider)
        self.assertEqual(len(calls),1);self.assertEqual(r['status'],'error')
        self.assertNotIn('SECRET_API_KEY',json.dumps(r))

    async def test_packet_drift_rejected_before_call(self):
        p=await packet(CASE,'legacy');p['max_tokens']=999
        async def forbidden(**kwargs): raise AssertionError('must not call')
        with self.assertRaises(ValueError): await generate(CASE,'legacy',p,forbidden)


class SafetyTests(unittest.TestCase):
    # AC-3503
    def test_local_config_fallback_without_starting_services(self):
        with patch('tests.integration.run_multipaper_journey.api',side_effect=OSError('offline')), \
             patch('dotenv.dotenv_values',return_value=dict(API_KEY='test-secret',MODEL_NAME='qwen3-vl-plus',
                 MODEL_URL='https://dashscope.aliyuncs.com/compatible-mode/v1')):
            self.assertEqual(load_live_config()['model_name'],'qwen3-vl-plus')

    def test_config_fallback_must_not_redirect_to_unknown_provider(self):
        with patch('tests.integration.run_multipaper_journey.api',side_effect=OSError('offline')), \
             patch('dotenv.dotenv_values',return_value=dict(API_KEY='test-secret',MODEL_NAME='qwen3-vl-plus',
                 MODEL_URL='https://example.invalid/v1')):
            with self.assertRaises(ValueError):load_live_config()

    def test_budget_approval_unresolved_attempt_and_input_drift(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';out.mkdir();source=root/'input.txt';source.write_text('frozen')
            write(out/'manifest.json',dict(protocol=PROTOCOL,planned_calls=22,file_sha256={'input.txt':digest(source)}))
            for approved,budget in ((False,22),(True,21),(True,True)):
                with self.assertRaises(ValueError): preflight(out,root,approved,budget)
            preflight(out,root,True,22)
            write(out/'attempt-A01-legacy.json',{})
            with self.assertRaises(ValueError): preflight(out,root,True,22)
            write(out/'result-A01-legacy.json',{})
            source.write_text('changed')
            with self.assertRaises(ValueError): preflight(out,root,True,22)

    def test_write_once(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json';write(p,{'old':1})
            with self.assertRaises(FileExistsError):write(p,{'new':2})
            self.assertEqual(read(p),{'old':1})


class SummaryTests(unittest.TestCase):
    # AC-3505
    def test_errors_and_guard_rejection_remain_in_denominator(self):
        labels=[dict(id='A01',answerable=True),dict(id='E01',answerable=False)]
        results=[dict(id=cid,mode=mode,status='ok',answer=INSUFFICIENT_EVIDENCE,
            guard_status='invalid_claim_structure' if cid=='A01' else 'no_evidence',
            provider_calls=int(cid=='A01'),seconds=1,usage={'total_tokens':120},finish_reason='stop',
            citation_ids=[],unknown_citations=[]) for cid in ('A01','E01') for mode in MODES]
        results[0].update(status='error',answer=None,guard_status=None)
        s=summarize(labels,results)
        self.assertEqual(s['modes']['legacy']['cases'],2)
        self.assertEqual(s['modes']['legacy']['errors'],1)
        self.assertEqual(s['modes']['claim_bound']['answerable_fixed_refusals'],1)
        self.assertFalse(s['semantic_accuracy_available'])


if __name__=='__main__': unittest.main()
