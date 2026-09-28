import asyncio
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests.integration import run_selected_claim_support_live as live


def response(request, verdict='supported', code='entailed', finish='stop', usage=True):
    p = json.loads(request['messages'][1]['content'])
    value = dict(packet_id=p['packet_id'], claim_id=p['claim_id'], verdict=verdict,
                 reason_code=code, reason='Test-only injected verdict, not semantic detection.',
                 evidence_ids=[p['selected_anchors'][0]['anchor_id']])
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish,
        message=SimpleNamespace(content=json.dumps(value), refusal=None))],
        usage=SimpleNamespace(model_dump=lambda: dict(prompt_tokens=100, completion_tokens=50, total_tokens=150)) if usage else None)


class Client:
    def __init__(self, provider): self.chat = SimpleNamespace(completions=SimpleNamespace(create=provider))
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False


class PreparationTests(unittest.TestCase):
    def test_write_once_freezes_exact_packets_no_labels(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'
            report = live.prepare(out)
            self.assertEqual(report['planned_calls'], 22)
            entries = live.preflight(out, True, 22)
            self.assertEqual(len(entries), 22)
            for row in entries:
                request = live.read(out / f"request-{row['key']}.json")
                self.assertEqual(request, live.request_for(row['packet']))
                self.assertNotIn('human_verdict', json.dumps(request))
                self.assertNotIn('ai_draft_assessment', json.dumps(request))
                self.assertEqual(request['max_tokens'], 1000)
            with self.assertRaises(FileExistsError): live.prepare(out)

    def test_request_or_code_drift_blocks(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            with patch.object(live, 'digest', return_value='0' * 64):
                with self.assertRaises(ValueError): live.preflight(out, True, 22)


class SafetyTests(unittest.TestCase):
    def test_approval_budget_and_config_validation(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            for approval, count in ((False, 22), (True, 21), (True, 23), (True, True)):
                with self.assertRaises(ValueError): live.preflight(out, approval, count)
        valid = dict(api_url='https://dashscope.aliyuncs.com/compatible-mode/v1', api_key='fake', model_name='qwen3-vl-plus')
        live.validate_config(valid)
        for changes in (dict(api_url='http://dashscope.aliyuncs.com/compatible-mode/v1'),
                        dict(api_url='https://example.com/compatible-mode/v1'),
                        dict(api_url='https://user:pass@dashscope.aliyuncs.com/compatible-mode/v1'),
                        dict(api_url='https://dashscope.aliyuncs.com/compatible-mode/v1?token=secret'),
                        dict(model_name='other'), dict(api_key='')):
            with self.assertRaises(ValueError): live.validate_config(dict(valid, **changes))

    def test_real_client_is_configured_with_no_retries(self):
        config = dict(api_url='https://dashscope.aliyuncs.com/compatible-mode/v1', api_key='fake-secret', model_name='qwen3-vl-plus')
        with patch('tests.integration.compare_answer_modes.load_live_config', return_value=config), \
                patch('openai.AsyncOpenAI') as factory:
            _, secret = live.make_client()
            factory.assert_called_once_with(api_key='fake-secret', base_url=config['api_url'],
                                            max_retries=0, timeout=60)
            self.assertEqual(secret, 'fake-secret')


class JudgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): self.row = live.frozen_entries()[0]

    async def test_exact_call_and_strict_parser(self):
        request = live.request_for(self.row['packet'])
        provider = AsyncMock(return_value=response(request))
        result = await live.judge(self.row, request, provider)
        provider.assert_awaited_once_with(**request)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['decision']['verdict'], 'supported')
        self.assertEqual(result['usage']['total_tokens'], 150)

    async def test_incomplete_refused_bad_id_and_bad_json_fail_without_retry(self):
        request = live.request_for(self.row['packet'])
        values = [response(request, finish='length'), response(request), response(request), response(request)]
        values[1].choices[0].message.refusal = 'refused'
        values[2].choices[0].message.content = '{}'
        values[3].choices[0].message.content = values[3].choices[0].message.content.replace(self.row['packet']['packet_id'], '0' * 64)
        for value in values:
            provider = AsyncMock(return_value=value)
            result = await live.judge(self.row, request, provider)
            self.assertEqual(result['status'], 'error'); self.assertEqual(provider.await_count, 1)
            self.assertIsNone(result['decision']); self.assertIsNotNone(result['raw_content'])

    async def test_provider_errors_do_not_leak_messages_or_invent_usage(self):
        provider = AsyncMock(side_effect=RuntimeError('SECRET_KEY'))
        result = await live.judge(self.row, live.request_for(self.row['packet']), provider)
        self.assertEqual(provider.await_count, 1)
        self.assertNotIn('SECRET_KEY', json.dumps(result))
        self.assertIsNone(result['usage'])

    async def test_deadline_is_enforced(self):
        provider = AsyncMock(side_effect=asyncio.TimeoutError('secret timeout details'))
        with patch.object(live.asyncio, 'wait_for', wraps=asyncio.wait_for) as waiter:
            result = await live.judge(self.row, live.request_for(self.row['packet']), provider)
            self.assertEqual(waiter.call_args.kwargs['timeout'], 60)
            self.assertEqual(result['error_type'], 'TimeoutError')

    async def test_request_drift_stops_before_call(self):
        provider = AsyncMock()
        request = live.request_for(self.row['packet']); request['max_tokens'] = 2000
        with self.assertRaises(ValueError): await live.judge(self.row, request, provider)
        provider.assert_not_awaited()


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_22_calls_with_journals_cached_rerun_and_human_nulls(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            async def reply(**request):
                self.assertEqual(len(list(out.glob('attempt-*.json'))), provider.await_count)
                return response(request)
            provider = AsyncMock(side_effect=reply)
            factory = Mock(return_value=(Client(provider), 'fake-secret'))
            summary = await live.run(True, 22, out, client_factory=factory)
            self.assertEqual(provider.await_count, 22)
            self.assertEqual(summary['reviewed_claims'], 22)
            self.assertEqual(summary['model_verdict_counts'], {'supported': 22})
            self.assertIsNone(summary['semantic_accuracy'])
            cards = live.read(out / 'human-review.json')
            self.assertTrue(all(c['human_verdict'] is None for c in cards))
            self.assertEqual(len(cards), 22)
            gates = live.read(out / 'gates.json')
            self.assertEqual(sum(g['result']['release_allowed'] for g in gates), 4)
            forbidden = Mock(side_effect=AssertionError('no client on replay'))
            self.assertEqual(await live.run(True, 22, out, client_factory=forbidden), summary)
            forbidden.assert_not_called()

    async def test_error_stops_batch_keeps_denominator_and_does_not_retry(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            provider = AsyncMock(side_effect=RuntimeError('fake-secret'))
            summary = await live.run(True, 22, out, client_factory=lambda: (Client(provider), 'fake-secret'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(summary['status'], 'stopped_error')
            self.assertEqual(summary['planned_claims'], 22)
            self.assertEqual(summary['unreviewed_claims'], 21)
            self.assertEqual(summary['errors'], 1)
            self.assertEqual(summary['usage_unknown_calls'], 1)
            forbidden = Mock(side_effect=AssertionError('no automatic retry'))
            await live.run(True, 22, out, client_factory=forbidden)
            forbidden.assert_not_called()

    async def test_interrupted_run_or_orphan_attempt_blocks_before_client(self):
        for marker in ('run-started.json', 'attempt-B01-C001.json'):
            with TemporaryDirectory() as directory:
                out = Path(directory) / 'run'; live.prepare(out)
                live.write(out / marker, {})
                factory = Mock(side_effect=AssertionError('must not initialize client'))
                with self.assertRaises(ValueError): await live.run(True, 22, out, client_factory=factory)
                factory.assert_not_called()

    async def test_invalid_approval_never_loads_credentials(self):
        factory = Mock(side_effect=AssertionError('no credential read'))
        with self.assertRaises(ValueError): await live.run(False, 22, client_factory=factory)
        factory.assert_not_called()


class SummaryTests(unittest.TestCase):
    def test_usage_missing_is_not_zero_and_negative_controls_are_not_model_accuracy(self):
        row = dict(status='ok', provider_calls=1, usage=None, seconds=2,
                   decision=dict(verdict='uncertain', reason_code='ambiguous_evidence'), finish_reason='stop')
        summary = live.summarize([row])
        self.assertEqual(summary['planned_claims'], 22)
        self.assertEqual(summary['unreviewed_claims'], 21)
        self.assertEqual(summary['negative_controls'], 2)
        self.assertIsNone(summary['measured_token_totals']['total_tokens'])
        self.assertIsNone(summary['semantic_accuracy'])
        self.assertEqual(summary['human_review_status'], 'pending')


if __name__ == '__main__': unittest.main()
