import asyncio
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests.integration import run_qualified_ids_pilot as live
from tests.test_qualified_evidence_ids import response as decision
from tests.test_selected_claim_support_live import Client


def response(request, state='entailed', *, usage=True):
    packet = json.loads(request['messages'][1]['content'])
    value = decision(packet)
    value['checks']['content']['status'] = state
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
        message=SimpleNamespace(content=json.dumps(value), refusal=None))],
        usage=SimpleNamespace(model_dump=lambda: dict(prompt_tokens=100, completion_tokens=50, total_tokens=150)) if usage else None)


class PreparationTests(unittest.TestCase):
    def test_exact_ten_unchanged_gold_blind_requests_and_write_once(self):
        with TemporaryDirectory() as directory, patch('socket.socket.connect', side_effect=AssertionError('offline')):
            out = Path(directory) / 'run'; summary = live.prepare(out)
            self.assertEqual(summary['planned_calls'], 10)
            self.assertEqual(summary['groups'], {'scifact': 6, 'selected_claim_regression': 4})
            entries = live.preflight(out, True, 10)
            self.assertEqual(tuple(e['key'] for e in entries), live.KEYS)
            for e in entries:
                request = live.read(out / f"request-{e['key']}.json")
                self.assertEqual(request, live.read(live.BASE / f"request-{e['key']}.json"))
                self.assertNotIn('gold_label', json.dumps(request))
                self.assertNotIn('human_verdict', json.dumps(request))
            with self.assertRaises(FileExistsError): live.prepare(out)

    def test_source_request_and_selection_drift_block(self):
        with patch.object(live, 'BASE_MANIFEST_SHA256', '0' * 64):
            with self.assertRaises(ValueError): live.cohort()
        for filename in ('selection.json', 'entries.json', 'request-SCIFACT-SF-415-6309659.json'):
            with TemporaryDirectory() as directory:
                out = Path(directory) / 'run'; live.prepare(out)
                (out / filename).write_text('{}', encoding='utf-8')
                with self.assertRaises(ValueError): live.preflight(out, True, 10)


class JudgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = live.cohort()[0]
        self.request = live.request_for(self.entry['packet'])

    async def test_exact_request_one_call_real_v3_and_provenance(self):
        provider = AsyncMock(return_value=response(self.request))
        result = await live.judge(self.entry, self.request, provider)
        provider.assert_awaited_once_with(**self.request)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['parser_version'], live.v3.VERSION)
        self.assertEqual(result['usage']['total_tokens'], 150)
        quote = result['decision']['checks']['content']['citations'][0]
        self.assertEqual(quote['provenance'], 'program_resolved_id')
        self.assertEqual(quote['quote'], self.entry['packet']['base_packet']['selected_anchors'][0]['text'])

    async def test_wrong_id_old_contract_refusal_truncation_and_api_fail_once(self):
        for kind in ('id', 'old', 'refusal', 'length', 'api', 'empty'):
            r = response(self.request); obj = json.loads(r.choices[0].message.content)
            if kind == 'id': obj['checks']['scope']['evidence_ids'] = ['S99:E0001']
            if kind == 'old':
                del obj['checks']['content']['evidence_ids']
                obj['checks']['content']['citations'] = [{'anchor_id': 'S1:E0001', 'quote': 'text'}]
            r.choices[0].message.content = json.dumps(obj)
            if kind == 'refusal': r.choices[0].message.refusal = 'refused'
            if kind == 'length': r.choices[0].finish_reason = 'length'
            if kind == 'empty': r.choices = []
            provider = AsyncMock(side_effect=RuntimeError('private-secret')) if kind == 'api' else AsyncMock(return_value=r)
            result = await live.judge(self.entry, self.request, provider)
            self.assertEqual(result['status'], 'error', kind)
            self.assertIsNone(result['decision']); self.assertEqual(provider.await_count, 1)
            self.assertNotIn('private-secret', json.dumps(result))

    async def test_deadline_and_request_drift(self):
        provider = AsyncMock(return_value=response(self.request))
        real_wait = asyncio.wait_for
        async def checked_wait(awaitable, timeout):
            self.assertEqual(timeout, 60)
            return await real_wait(awaitable, timeout)
        with patch.object(live.asyncio, 'wait_for', side_effect=checked_wait):
            await live.judge(self.entry, self.request, provider)
        bad = copy.deepcopy(self.request); bad['max_tokens'] = 1501
        with self.assertRaises(ValueError): await live.judge(self.entry, bad, provider)
        self.assertEqual(provider.await_count, 1)


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit10_budget_precedes_credentials(self):
        for approval, budget in ((False, 10), (True, 9), (True, 11), (True, 52), (True, True)):
            factory = Mock(side_effect=AssertionError('no credentials'))
            with self.assertRaises(ValueError): await live.run(approval, budget, client_factory=factory)
            factory.assert_not_called()

    async def test_ten_calls_no_repeat_cache_and_review_cards(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            async def reply(**request):
                self.assertTrue((out / 'run-started.json').exists())
                self.assertEqual(len(list(out.glob('attempt-*.json'))), provider.await_count)
                return response(request)
            provider = AsyncMock(side_effect=reply)
            report = await live.run(True, 10, out, client_factory=lambda: (Client(provider), 'test-secret'))
            self.assertEqual(provider.await_count, 10); self.assertEqual(report['status'], 'completed')
            self.assertEqual(report['valid_contracts'], 10)
            self.assertEqual(report['scifact']['total'], 6)
            self.assertEqual(report['scifact']['v3_correct'], 3)
            self.assertEqual(report['scifact']['v1_correct'], 5)
            self.assertEqual(report['regression']['total'], 4)
            self.assertIsNone(report['regression']['semantic_accuracy'])
            self.assertIsNone(report['pooled_accuracy'])
            self.assertTrue(all(c['human_verdict'] is None for c in live.read(out / 'review-cards.json')))
            factory = Mock(side_effect=AssertionError('no repeat'))
            self.assertEqual(await live.run(True, 10, out, client_factory=factory), report)
            factory.assert_not_called()

    async def test_first_error_stops_and_missing_not_uncertain(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            provider = AsyncMock(side_effect=TimeoutError())
            report = await live.run(True, 10, out, client_factory=lambda: (Client(provider), 'test-secret'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(report['status'], 'stopped_error'); self.assertEqual(report['not_run'], 9)
            self.assertEqual(report['scifact']['errors'], 1)
            self.assertEqual(report['scifact']['missing'], 5)
            self.assertEqual(report['regression']['missing'], 4)
            self.assertIsNone(report['measured_token_totals']['total_tokens'])
            factory = Mock(side_effect=AssertionError('no resume'))
            self.assertEqual(await live.run(True, 10, out, client_factory=factory), report)
            factory.assert_not_called()

    async def test_orphan_and_interrupted_markers_block_before_client(self):
        for name in ('run-started.json', f'attempt-{live.KEYS[0]}.json', f'result-{live.KEYS[0]}.json'):
            with TemporaryDirectory() as directory:
                out = Path(directory) / 'run'; live.prepare(out); live.write(out / name, {})
                factory = Mock(side_effect=AssertionError('no credentials'))
                with self.assertRaises(ValueError): await live.run(True, 10, out, client_factory=factory)
                factory.assert_not_called()

    async def test_concurrent_invocations_only_one_call_on_error(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            async def fail(**request):
                await asyncio.sleep(0)
                raise TimeoutError()
            provider = AsyncMock(side_effect=fail)
            factory = lambda: (Client(provider), 'test-secret')
            results = await asyncio.gather(live.run(True, 10, out, client_factory=factory),
                                           live.run(True, 10, out, client_factory=factory), return_exceptions=True)
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(sum(isinstance(r, (ValueError, FileExistsError)) for r in results), 1)

    async def test_secret_echo_redaction_and_summary_tamper(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            def echo(**request):
                r = response(request); obj = json.loads(r.choices[0].message.content)
                obj['checks']['content']['reason'] = 'private-credential'
                r.choices[0].message.content = json.dumps(obj)
                return r
            provider = AsyncMock(side_effect=echo)
            report = await live.run(True, 10, out, client_factory=lambda: (Client(provider), 'private-credential'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(report['errors'], 1)
            self.assertNotIn('private-credential', (out / 'results.json').read_text(encoding='utf-8'))
            report['provider_calls'] = 10
            (out / 'summary.json').write_text(json.dumps(report), encoding='utf-8')
            factory = Mock(side_effect=AssertionError('no new call'))
            with self.assertRaises(ValueError): await live.run(True, 10, out, client_factory=factory)
            factory.assert_not_called()


class SummaryTests(unittest.TestCase):
    def setUp(self): self.entries = live.cohort()

    def result(self, state='entailed', usage=True):
        e = self.entries[0]; req = live.request_for(e['packet'])
        return asyncio.run(live.judge(e, req, AsyncMock(return_value=response(req, state, usage=usage))))

    def test_raw_reparse_not_cached_decision_and_invalid_identity(self):
        r = self.result(); r['decision']['verdict'] = 'unsupported'
        self.assertEqual(live.summarize(self.entries, [r])['scifact']['cases'][0]['v3'], 'SUPPORT')
        for rows in ([r, r], [dict(r, key='unknown')], [dict(r, request_sha256='wrong')]):
            with self.assertRaises(ValueError): live.summarize(self.entries, rows)
        r['raw_content'] = '{}'
        self.assertEqual(live.summarize(self.entries, [r])['errors'], 1)

    def test_uncertain_usage_unknown_empty_batch(self):
        report = live.summarize(self.entries, [self.result('uncertain', usage=False)])
        self.assertEqual(report['scifact']['uncertain'], 1)
        self.assertEqual(report['scifact']['missing'], 5)
        self.assertEqual(report['scifact']['v3_correct'], 0)
        self.assertIsNone(report['measured_token_totals']['total_tokens'])
        self.assertEqual(report['usage_unknown_calls'], 1)
        empty = live.summarize(self.entries, [])
        self.assertEqual(empty['not_run'], 10)
        self.assertIsNone(empty['scifact']['descriptive_accuracy_full_denominator'])
        self.assertIsNone(empty['contract_valid_per_planned'])


if __name__ == '__main__':
    unittest.main()
