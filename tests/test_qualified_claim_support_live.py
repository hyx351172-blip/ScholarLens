import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests.integration import run_qualified_claim_support_live as live
from tests.test_qualified_claim_support import decision
from tests.test_selected_claim_support_live import Client


def response(request, state='entailed', finish='stop', usage=True, refusal=None):
    packet = json.loads(request['messages'][1]['content'])
    value = decision(packet)
    value['checks']['content']['status'] = state
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish,
        message=SimpleNamespace(content=json.dumps(value), refusal=refusal))],
        usage=SimpleNamespace(model_dump=lambda: dict(prompt_tokens=100, completion_tokens=50, total_tokens=150)) if usage else None)


class PreparationTests(unittest.TestCase):
    def test_exact_52_label_blind_write_once_requests(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'
            self.assertEqual(live.prepare(out)['planned_calls'], 52)
            entries = live.preflight(out, True, 52)
            self.assertEqual(entries, live.read(live.BASE / 'entries.json'))
            for e in entries:
                request = live.read(out / f"request-{e['key']}.json")
                self.assertEqual(request, live.read(live.BASE / f"request-{e['key']}.json"))
                self.assertEqual(request['max_tokens'], 1500)
                for forbidden in ('gold_label', 'human_verdict', 'ai_draft_assessment', 'rationale_sets'):
                    self.assertNotIn(forbidden, json.dumps(request))
            with self.assertRaises(FileExistsError): live.prepare(out)

    def test_request_drift_blocks(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            next(out.glob('request-*.json')).write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError): live.preflight(out, True, 52)


class JudgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = live.read(live.BASE / 'entries.json')[0]
        self.request = live.request_for(self.entry['packet'])

    async def test_v2_contract_exact_request_and_usage(self):
        provider = AsyncMock(return_value=response(self.request))
        row = await live.judge(self.entry, self.request, provider)
        provider.assert_awaited_once_with(**self.request)
        self.assertEqual(row['status'], 'ok')
        self.assertEqual(row['decision']['packet_id'], self.entry['packet']['packet_id'])
        self.assertEqual(row['usage']['total_tokens'], 150)
        self.assertEqual(row['group'], 'scifact')

    async def test_invalid_quote_and_refusal_and_truncation_are_errors(self):
        for kind in ('quote', 'refusal', 'length', 'json'):
            r = response(self.request)
            if kind == 'refusal': r.choices[0].message.refusal = 'refused'
            if kind == 'length': r.choices[0].finish_reason = 'length'
            if kind == 'json': r.choices[0].message.content = '{}'
            if kind == 'quote':
                value = json.loads(r.choices[0].message.content)
                value['checks']['scope']['citations'][0]['quote'] = 'invented quote not in source'
                r.choices[0].message.content = json.dumps(value)
            provider = AsyncMock(return_value=r)
            row = await live.judge(self.entry, self.request, provider)
            self.assertEqual(row['status'], 'error')
            self.assertIsNone(row['decision'])
            self.assertEqual(row['raw_content'], r.choices[0].message.content)
            self.assertEqual(provider.await_count, 1)

    async def test_total_deadline_and_no_retry(self):
        seen = []
        async def timeout(coro, timeout):
            seen.append(timeout)
            await coro
            raise TimeoutError()
        provider = AsyncMock(return_value=response(self.request))
        with patch.object(live.asyncio, 'wait_for', side_effect=timeout):
            row = await live.judge(self.entry, self.request, provider)
        self.assertEqual(seen, [60])
        self.assertEqual(provider.await_count, 1)
        self.assertEqual(row['error_type'], 'TimeoutError')


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_approval_before_credentials(self):
        for approved, budget in ((False, 52), (True, 51), (True, 53), (True, True)):
            factory = Mock(side_effect=AssertionError('no credentials'))
            with self.assertRaises(ValueError): await live.run(approved, budget, client_factory=factory)
            factory.assert_not_called()

    async def test_52_calls_separate_groups_and_cache(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            async def reply(**request):
                self.assertTrue((out / 'run-started.json').exists())
                self.assertEqual(len(list(out.glob('attempt-*.json'))), provider.await_count)
                return response(request)
            provider = AsyncMock(side_effect=reply)
            summary = await live.run(True, 52, out, client_factory=lambda: (Client(provider), 'test-secret'))
            self.assertEqual(provider.await_count, 52)
            self.assertEqual(summary['status'], 'completed')
            self.assertEqual(summary['scifact_v2']['total'], 30)
            self.assertAlmostEqual(summary['scifact_v2']['accuracy_full_denominator'], 1 / 3)
            self.assertEqual(summary['scifact_v2']['false_accept_count'], 20)
            self.assertEqual(summary['scifact_v1']['correct'], 26)
            self.assertEqual(summary['regression']['total'], 22)
            self.assertEqual(sum(summary['regression']['transitions'].values()), 22)
            self.assertIsNone(summary['regression']['semantic_accuracy'])
            self.assertEqual(summary['measured_token_totals']['total_tokens'], 52 * 150)
            cards = live.read(out / 'review-cards.json')
            self.assertEqual(len(cards), 52)
            self.assertTrue(all(c['human_verdict'] is None for c in cards))
            factory = Mock(side_effect=AssertionError('no repeat calls'))
            self.assertEqual(await live.run(True, 52, out, client_factory=factory), summary)
            factory.assert_not_called()

    async def test_api_error_stops_and_full_denominators_survive(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            provider = AsyncMock(side_effect=RuntimeError('private-test-key'))
            summary = await live.run(True, 52, out, client_factory=lambda: (Client(provider), 'private-test-key'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(summary['status'], 'stopped_error')
            self.assertEqual(summary['scifact_v2']['errors'], 1)
            self.assertEqual(summary['scifact_v2']['missing'], 29)
            self.assertEqual(summary['regression']['missing'], 22)
            self.assertIsNone(summary['measured_token_totals']['total_tokens'])
            self.assertNotIn('private-test-key', (out / 'results.json').read_text(encoding='utf-8'))
            factory = Mock(side_effect=AssertionError('no automatic retry'))
            await live.run(True, 52, out, client_factory=factory)
            factory.assert_not_called()

    async def test_truncation_stops_without_retry(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            provider = AsyncMock(side_effect=lambda **r: response(r, finish='length'))
            summary = await live.run(True, 52, out, client_factory=lambda: (Client(provider), 'test-secret'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(summary['finish_reason_counts'], {'length': 1})

    async def test_secret_echo_redacted_and_failed(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            def echo(**request):
                r = response(request)
                value = json.loads(r.choices[0].message.content)
                value['checks']['content']['reason'] = 'private-test-key'
                r.choices[0].message.content = json.dumps(value)
                return r
            provider = AsyncMock(side_effect=echo)
            summary = await live.run(True, 52, out, client_factory=lambda: (Client(provider), 'private-test-key'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(summary['scifact_v2']['errors'], 1)
            self.assertNotIn('private-test-key', (out / 'results.json').read_text(encoding='utf-8'))

    async def test_interrupted_or_orphan_run_never_resumes(self):
        key = live.read(live.BASE / 'entries.json')[0]['key']
        for marker in ('run-started.json', f'attempt-{key}.json', f'result-{key}.json'):
            with TemporaryDirectory() as directory:
                out = Path(directory) / 'run'; live.prepare(out); live.write(out / marker, {})
                factory = Mock(side_effect=AssertionError('no credentials'))
                with self.assertRaises(ValueError): await live.run(True, 52, out, client_factory=factory)
                factory.assert_not_called()

    async def test_concurrent_invocation_cannot_double_spend(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            async def reply(**request):
                await asyncio.sleep(0)
                return response(request)
            provider = AsyncMock(side_effect=reply)
            factory = lambda: (Client(provider), 'test-secret')
            results = await asyncio.gather(live.run(True, 52, out, client_factory=factory),
                                          live.run(True, 52, out, client_factory=factory), return_exceptions=True)
            self.assertEqual(provider.await_count, 52)
            self.assertEqual(sum(isinstance(r, (ValueError, FileExistsError)) for r in results), 1)


class SummaryTests(unittest.TestCase):
    def setUp(self): self.entries = live.read(live.BASE / 'entries.json')

    def row(self, state='entailed', usage=True):
        entry = self.entries[0]; request = live.request_for(entry['packet'])
        return asyncio.run(live.judge(entry, request, AsyncMock(return_value=response(request, state, usage=usage))))

    def test_reparse_raw_not_cached_decision(self):
        row = self.row()
        row['decision']['verdict'] = 'unsupported'
        row['decision']['reason_code'] = 'contradicted'
        report = live.summarize(self.entries, [row])
        self.assertEqual(report['scifact_v2']['cases'][0]['predicted'], 'SUPPORT')
        row['raw_content'] = '{}'
        self.assertEqual(live.summarize(self.entries, [row])['scifact_v2']['errors'], 1)

    def test_unknown_duplicate_and_wrong_request_rejected(self):
        row = self.row()
        for rows in ([row, row], [dict(row, key='forged')], [dict(row, request_sha256='forged')]):
            with self.assertRaises(ValueError): live.summarize(self.entries, rows)

    def test_uncertainty_not_nei_and_missing_usage_not_zero(self):
        report = live.summarize(self.entries, [self.row('uncertain', usage=False)])
        self.assertEqual(report['scifact_v2']['uncertain'], 1)
        self.assertEqual(report['scifact_v2']['missing'], 29)
        self.assertEqual(report['scifact_v2']['correct'], 0)
        self.assertEqual(report['usage_unknown_calls'], 1)
        self.assertIsNone(report['measured_token_totals']['total_tokens'])
        self.assertIsNone(report['regression']['semantic_accuracy'])

    def test_no_results_no_accuracy(self):
        report = live.summarize(self.entries, [])
        self.assertIsNone(report['scifact_v2']['accuracy_full_denominator'])
        self.assertIsNone(report['scifact_v2']['false_accept_rate'])
        self.assertEqual(report['scifact_v2']['missing'], 30)
        self.assertEqual(report['regression']['missing'], 22)

    def test_scoring_math_with_injected_three_way_labels(self):
        # Synthetic labels validate arithmetic, never count as model performance.
        gold = {r['key']: r['gold_label'] for r in live.read(live.BASE / 'labels.json')}
        rows = []
        for entry in self.entries[:30]:
            request = live.request_for(entry['packet'])
            state = {'SUPPORT': 'entailed', 'CONTRADICT': 'contradicted', 'NOT_ENOUGH_INFO': 'missing'}[gold[entry['key']]]
            rows.append(asyncio.run(live.judge(entry, request, AsyncMock(return_value=response(request, state)))))
        report = live.summarize(self.entries, rows)
        self.assertEqual(report['scifact_v2']['correct'], 30)
        self.assertEqual(report['scifact_v2']['macro_f1'], 1)
        self.assertEqual(report['scifact_v2']['positive_block_count'], 0)
        self.assertEqual(report['scifact_v2']['false_accept_count'], 0)
        self.assertEqual(report['regression']['missing'], 22)

    def test_cached_summary_tamper_rejected(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            row = self.row()
            live.write(out / f"result-{row['key']}.json", row)
            summary = live.finish(out, self.entries, [row])
            self.assertEqual(live.verify_summary(out, self.entries), summary)
            summary['provider_calls'] = 52
            (out / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
            with self.assertRaises(ValueError): live.verify_summary(out, self.entries)


if __name__ == '__main__':
    unittest.main()
