import asyncio
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from tests.integration import run_evidence_units_live as live
from tests.integration.compare_answer_modes import read, write, digest, value_hash

CASE = dict(id='B01', query='What is the result?', documents=[dict(source_id='S1', filename='p.pdf',
    chunk_text='This study reports a result. It is a separate fact.', score=1, metadata={})])
RAW = json.dumps(dict(status='answered', claims=[dict(text='本研究报告这一结果。', evidence_ids=['S1:U0001'])]))


def response(raw=RAW, finish='stop', usage=True):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish,
        message=SimpleNamespace(content=raw, refusal=None))],
        usage=SimpleNamespace(model_dump=lambda:dict(prompt_tokens=100,completion_tokens=20,total_tokens=120)) if usage else None)


class SelectionTests(unittest.TestCase):
    # AC-3801
    def test_fixed_selection_excludes_labels_and_preserves_sources(self):
        values=[dict(copy.deepcopy(CASE),id=cid,expected='SECRET_GOLD') for cid in live.IDS]
        values[-1]['documents']=[]
        selected=live.select_inputs(values)
        self.assertEqual(tuple(c['id'] for c in selected),live.IDS)
        self.assertNotIn('SECRET_GOLD',json.dumps(selected))
        self.assertEqual(selected[0]['documents'],CASE['documents'])
        self.assertEqual(sum(bool(c['documents']) for c in selected),5)

    def test_missing_duplicate_or_nonempty_empty_control_rejected(self):
        values=[dict(copy.deepcopy(CASE),id=cid) for cid in live.IDS];values[-1]['documents']=[]
        for bad in (values[:-1],values+[values[0]], [dict(c,documents=CASE['documents']) for c in values]):
            with self.assertRaises(ValueError): live.select_inputs(bad)


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    # AC-3801 / AC-3803 / AC-3804
    async def test_production_packet_and_one_call_with_usage(self):
        request=await live.candidate_packet(CASE);provider=AsyncMock(return_value=response())
        result=await live.generate(CASE,request,provider)
        provider.assert_awaited_once_with(**request)
        self.assertEqual(request['max_tokens'],2000);self.assertEqual(request['temperature'],0)
        self.assertEqual(result['binding']['evidence_catalog_version'],'sentence_v2')
        self.assertEqual(result['usage']['total_tokens'],120)
        self.assertEqual(result['provider_calls'],1)

    async def test_no_evidence_no_call(self):
        provider=AsyncMock(side_effect=AssertionError('must not call'))
        result=await live.generate(dict(CASE,documents=[]),None,provider)
        provider.assert_not_awaited()
        self.assertEqual(result['answer'],INSUFFICIENT_EVIDENCE)
        self.assertEqual(result['provider_calls'],0)

    async def test_bad_structure_truncation_and_old_ids_retained(self):
        request=await live.candidate_packet(CASE)
        for raw,finish,status in (('{}','stop','invalid_claim_structure'),(RAW,'length','incomplete_claim_generation'),
                                 (RAW.replace('U0001','E0001'),'stop','invalid_claim_structure')):
            provider=AsyncMock(return_value=response(raw,finish))
            result=await live.generate(CASE,request,provider)
            provider.assert_awaited_once()
            self.assertEqual(result['raw_content'],raw)
            self.assertEqual(result['finish_reason'],finish)
            self.assertEqual(result['guard_status'],status)

    async def test_network_error_sanitized_no_retry_and_packet_drift_blocks(self):
        request=await live.candidate_packet(CASE)
        provider=AsyncMock(side_effect=RuntimeError('SECRET_KEY'))
        result=await live.generate(CASE,request,provider)
        provider.assert_awaited_once();self.assertNotIn('SECRET_KEY',json.dumps(result))
        self.assertEqual(result['status'],'error')
        bad=dict(request,max_tokens=3000);provider.reset_mock()
        with self.assertRaises(ValueError): await live.generate(CASE,bad,provider)
        provider.assert_not_awaited()


class SafetyTests(unittest.TestCase):
    # AC-3802 / AC-3806
    def fixture(self,root):
        out=root/'out';out.mkdir();source=root/'source.txt';source.write_text('frozen')
        write(out/'manifest.json',dict(protocol=live.PROTOCOL,cases=list(live.IDS),planned_calls=5,
            file_sha256={'source.txt':digest(source)}))
        return out,source

    def test_approval_budget_protocol_and_unresolved_attempt(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);out,source=self.fixture(root)
            for approval,budget in ((False,5),(True,4),(True,True)):
                with self.assertRaises(ValueError): live.preflight(out,root,approval,budget)
            live.preflight(out,root,True,5)
            write(out/'attempt-B01.json',{})
            with self.assertRaises(ValueError): live.preflight(out,root,True,5)

    def test_source_drift_and_foreign_attempt_rejected(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);out,source=self.fixture(root)
            source.write_text('changed')
            with self.assertRaises(ValueError): live.preflight(out,root,True,5)
        with TemporaryDirectory() as tmp:
            root=Path(tmp);out,_=self.fixture(root)
            write(out/'attempt-foreign.json',{});write(out/'result-foreign.json',{})
            with self.assertRaises(ValueError): live.preflight(out,root,True,5)

    def test_write_once_and_secret_redaction(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'result.json';write(p,{'before':1})
            with self.assertRaises(FileExistsError):write(p,{'after':2})
            self.assertEqual(read(p),{'before':1})
        redacted=live.redact(dict(raw_content='echo SECRET'), 'SECRET')
        self.assertNotIn('SECRET',json.dumps(redacted))
        self.assertTrue(redacted['secret_redacted'])


class SummaryTests(unittest.TestCase):
    # AC-3804
    def test_missing_usage_not_reported_as_measured_zero_and_failures_counted(self):
        results=[dict(id=cid,status='ok',provider_calls=int(cid!='E01'),usage={},seconds=1,
                      guard_status='invalid_claim_structure',answer='format error',binding=None) for cid in live.IDS]
        results[0].update(status='error');results[-1].update(answer=INSUFFICIENT_EVIDENCE,guard_status='no_evidence')
        summary=live.summarize(results)
        self.assertEqual(summary['cases'],6);self.assertEqual(summary['errors'],1)
        self.assertEqual(summary['provider_calls'],5)
        self.assertEqual(summary['usage_unknown_calls'],5)
        self.assertFalse(summary['semantic_accuracy_available'])
        self.assertEqual(summary['answerable_output_count'],0)


class ReviewTests(unittest.TestCase):
    # AC-3805
    def test_cards_use_only_selected_spans_and_leave_human_judgments_empty(self):
        from backend.chat.evidence_units import build_catalog, render_claim_answer
        answer,binding=render_claim_answer(RAW,build_catalog(CASE['documents']))
        cards=live.review_case(CASE,dict(answer=answer,binding=binding))
        quote=cards['claims'][0]['selected_evidence'][0]
        self.assertEqual(quote['text'],'This study reports a result. ')
        self.assertNotIn('separate fact',json.dumps(cards))
        self.assertIsNone(cards['claims'][0]['human_support_verdict'])
        self.assertFalse(cards['semantic_verified'])
        binding['claims'][0]['evidence'][0]['end']+=1
        with self.assertRaises(ValueError):live.review_case(CASE,dict(answer=answer,binding=binding))


class RunTests(unittest.IsolatedAsyncioTestCase):
    # AC-3802 / AC-3803 / AC-3806: run the actual journal loop, stub provider only.
    async def fixture(self,root):
        out=root/'out';out.mkdir()
        cases=[dict(copy.deepcopy(CASE),id=cid) for cid in live.IDS]
        cases[-1]['documents']=[]
        write(out/'inputs.json',cases)
        for case in cases:write(out/f"request-{case['id']}.json",await live.candidate_packet(case))
        frozen={p.relative_to(root).as_posix():digest(p) for p in out.iterdir()}
        write(out/'manifest.json',dict(protocol=live.PROTOCOL,cases=list(live.IDS),planned_calls=5,file_sha256=frozen))
        return out

    async def test_exact_five_attempts_client_safety_and_completed_run_never_repeats(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);out=await self.fixture(root)
            client=AsyncMock();client.chat.completions.create.return_value=response()
            with patch.object(live,'ROOT',root),patch.object(live,'load_live_config',return_value=dict(
                    api_key='SECRET',api_url='https://dashscope.aliyuncs.com/compatible-mode/v1')) as config, \
                 patch('openai.AsyncOpenAI') as factory:
                factory.return_value.__aenter__=AsyncMock(return_value=client)
                factory.return_value.__aexit__=AsyncMock(return_value=False)
                summary=await live.run(True,5,out)
                self.assertEqual(summary['provider_calls'],5)
                self.assertEqual(len(list(out.glob('attempt-*.json'))),5)
                self.assertEqual(len(list(out.glob('result-*.json'))),6)
                self.assertEqual(read(out/'result-E01.json')['provider_calls'],0)
                self.assertEqual(factory.call_args.kwargs['max_retries'],0)
                self.assertEqual(factory.call_args.kwargs['timeout'],60)
                self.assertEqual(await live.run(True,5,out),summary)
                self.assertEqual(client.chat.completions.create.await_count,5)
                config.assert_called_once();factory.assert_called_once()
                # Changing a finished result cannot be hidden behind its old summary.
                original=(out/'result-E01.json').read_text()
                (out/'result-E01.json').write_text(original+' ')
                with self.assertRaises(ValueError):await live.run(True,5,out)
            self.assertNotIn('SECRET',''.join(p.read_text() for p in out.glob('*.json')))

    async def test_provider_error_stops_and_cannot_be_retried_by_rerun(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);out=await self.fixture(root)
            client=AsyncMock();client.chat.completions.create.side_effect=RuntimeError('SECRET')
            with patch.object(live,'ROOT',root),patch.object(live,'load_live_config',return_value=dict(
                    api_key='SECRET',api_url='https://dashscope.aliyuncs.com/compatible-mode/v1')), \
                 patch('openai.AsyncOpenAI') as factory:
                factory.return_value.__aenter__=AsyncMock(return_value=client)
                factory.return_value.__aexit__=AsyncMock(return_value=False)
                first=await live.run(True,5,out)
                second=await live.run(True,5,out)
                self.assertEqual(first['status'],'partial_provider_error')
                self.assertEqual(second['status'],'partial_provider_error')
                client.chat.completions.create.assert_awaited_once()
            self.assertEqual(len(list(out.glob('attempt-*.json'))),1)
            self.assertEqual(read(out/'result-B01.json')['status'],'error')
            self.assertNotIn('SECRET',(out/'result-B01.json').read_text())

    async def test_no_approval_or_unresolved_attempt_blocks_before_config_loading(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);out=await self.fixture(root)
            with patch.object(live,'ROOT',root),patch.object(live,'load_live_config',side_effect=AssertionError('forbidden')) as config:
                with self.assertRaises(ValueError):await live.run(False,5,out)
                write(out/'attempt-B01.json',{})
                with self.assertRaises(ValueError):await live.run(True,5,out)
                config.assert_not_called()


if __name__=='__main__':unittest.main()
