import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests.integration import run_qualified_support_remaining as live
from tests.test_qualified_claim_support_live import response
from tests.test_selected_claim_support_live import Client


class PreparationTests(unittest.TestCase):
    def test_exact_remaining51_requests_and_write_once(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'
            report = live.prepare(out)
            self.assertEqual(report['planned_calls'], 51)
            self.assertEqual(report['groups'], {'scifact': 29, 'selected_claim_regression': 22})
            entries = live.preflight(out, True, 51)
            self.assertEqual(entries, live.read(live.BASE / 'entries.json')[1:])
            self.assertNotIn(live.EXCLUDED_KEY, [e['key'] for e in entries])
            for e in entries:
                request = live.read(out / f"request-{e['key']}.json")
                self.assertEqual(request, live.read(live.BASE / f"request-{e['key']}.json"))
                self.assertNotIn('gold_label', json.dumps(request))
                self.assertNotIn('human_verdict', json.dumps(request))
            with self.assertRaises(FileExistsError): live.prepare(out)

    def test_input_and_history_drift_block(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            next(out.glob('request-*.json')).write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError): live.preflight(out, True, 51)
        with patch.object(live, 'REPLAY_MANIFEST_SHA256', '0' * 64):
            with self.assertRaises(ValueError): live.load_cohort()


class JudgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = live.read(live.BASE / 'entries.json')[1]
        self.request = live.request_for(self.entry['packet'])

    async def test_real_v21_alignment_not_frozen_v2_error(self):
        r = response(self.request)
        value = json.loads(r.choices[0].message.content)
        for check in value['checks'].values():
            check['citations'][0]['quote'] = check['citations'][0]['quote'].replace('\n', ' ')
        r.choices[0].message.content = json.dumps(value)
        provider = AsyncMock(return_value=r)
        result = await live.judge(self.entry, self.request, provider)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['strict_v2_status'], 'error')
        self.assertEqual(result['decision']['version'], live.v21.VERSION)
        self.assertNotIn('error_type', result)
        self.assertEqual(result['raw_content'], r.choices[0].message.content)
        provider.assert_awaited_once_with(**self.request)

    async def test_no_promotion_of_truncation_refusal_api_or_content_change(self):
        for kind in ('length', 'refusal', 'api', 'quote'):
            r = response(self.request)
            if kind == 'length': r.choices[0].finish_reason = 'length'
            if kind == 'refusal': r.choices[0].message.refusal = 'refused'
            if kind == 'quote':
                value = json.loads(r.choices[0].message.content)
                value['checks']['content']['citations'][0]['quote'] = 'Fabricated source statement.'
                r.choices[0].message.content = json.dumps(value)
            provider = AsyncMock(side_effect=RuntimeError('private-secret')) if kind == 'api' else AsyncMock(return_value=r)
            result = await live.judge(self.entry, self.request, provider)
            self.assertEqual(result['status'], 'error')
            self.assertIsNone(result['decision'])
            self.assertNotIn('private-secret', json.dumps(result))
            self.assertEqual(provider.await_count, 1)


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit51_approval_before_credentials(self):
        for approved, budget in ((False, 51), (True, 52), (True, 50), (True, True)):
            factory = Mock(side_effect=AssertionError('no credentials'))
            with self.assertRaises(ValueError): await live.run(approved, budget, client_factory=factory)
            factory.assert_not_called()

    async def test_51_calls_distinct_scoring_and_cache(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            async def reply(**request):
                self.assertTrue((out / 'run-started.json').exists())
                self.assertEqual(len(list(out.glob('attempt-*.json'))), provider.await_count)
                return response(request)
            provider = AsyncMock(side_effect=reply)
            report = await live.run(True, 51, out, client_factory=lambda: (Client(provider), 'test-secret'))
            self.assertEqual(provider.await_count, 51)
            self.assertEqual(report['status'], 'completed')
            self.assertEqual(report['scifact_v21']['total'], 29)
            self.assertEqual(report['scifact_v21']['correct'], 10)
            self.assertEqual(report['scifact_v21']['false_accept_count'], 19)
            self.assertEqual(report['scifact_v1_same29']['correct'], 25)
            self.assertEqual(report['scifact_v1_same29']['total'], 29)
            self.assertEqual(report['regression']['total'], 22)
            self.assertIsNone(report['regression']['semantic_accuracy'])
            self.assertIsNone(report['mixed52_live_accuracy'])
            self.assertEqual(report['historical_replay']['key'], live.EXCLUDED_KEY)
            self.assertEqual(report['historical_replay']['new_provider_calls'], 0)
            self.assertTrue(all(c['human_verdict'] is None for c in live.read(out / 'review-cards.json')))
            factory = Mock(side_effect=AssertionError('no new calls'))
            self.assertEqual(await live.run(True, 51, out, client_factory=factory), report)
            factory.assert_not_called()

    async def test_error_stops_and_preserves_missing(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            provider = AsyncMock(side_effect=TimeoutError())
            result = await live.run(True, 51, out, client_factory=lambda: (Client(provider), 'test-secret'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(result['status'], 'stopped_error')
            self.assertEqual(result['scifact_v21']['errors'], 1)
            self.assertEqual(result['scifact_v21']['missing'], 28)
            self.assertEqual(result['regression']['missing'], 22)
            factory = Mock(side_effect=AssertionError('no automatic resume'))
            self.assertEqual(await live.run(True, 51, out, client_factory=factory), result)
            factory.assert_not_called()

    async def test_secret_echo_fails_and_is_redacted(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            def echo(**request):
                r = response(request); value = json.loads(r.choices[0].message.content)
                value['checks']['content']['reason'] = 'private-credential'
                r.choices[0].message.content = json.dumps(value)
                return r
            provider = AsyncMock(side_effect=echo)
            report = await live.run(True, 51, out, client_factory=lambda: (Client(provider), 'private-credential'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(report['errors'], 1)
            self.assertNotIn('private-credential', (out / 'results.json').read_text(encoding='utf-8'))

    async def test_orphan_and_interrupted_runs_never_resume(self):
        key = live.read(live.BASE / 'entries.json')[1]['key']
        for marker in ('run-started.json', f'attempt-{key}.json', f'result-{key}.json'):
            with TemporaryDirectory() as directory:
                out = Path(directory) / 'run'; live.prepare(out); live.write(out / marker, {})
                factory = Mock(side_effect=AssertionError('no credentials'))
                with self.assertRaises(ValueError): await live.run(True, 51, out, client_factory=factory)
                factory.assert_not_called()

    async def test_concurrent_invocations_do_not_double_spend(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            async def error(**request):
                await asyncio.sleep(0)
                raise TimeoutError()
            provider = AsyncMock(side_effect=error)
            factory = lambda: (Client(provider), 'test-secret')
            reports = await asyncio.gather(live.run(True, 51, out, client_factory=factory),
                                           live.run(True, 51, out, client_factory=factory), return_exceptions=True)
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(sum(isinstance(r, (ValueError, FileExistsError)) for r in reports), 1)


class SummaryTests(unittest.TestCase):
    def setUp(self): self.entries = live.read(live.BASE / 'entries.json')[1:]

    def result(self, state='entailed', usage=True):
        e = self.entries[0]; request = live.request_for(e['packet'])
        return asyncio.run(live.judge(e, request, AsyncMock(return_value=response(request, state, usage=usage))))

    def test_raw_reparse_ignores_cached_decision_and_rejects_forgery(self):
        r = self.result(); r['decision']['verdict'] = 'unsupported'
        self.assertEqual(live.summarize(self.entries, [r])['scifact_v21']['cases'][0]['predicted'], 'SUPPORT')
        for rows in ([r, r], [dict(r, key=live.EXCLUDED_KEY)], [dict(r, request_sha256='wrong')]):
            with self.assertRaises(ValueError): live.summarize(self.entries, rows)
        r['raw_content'] = '{}'
        self.assertEqual(live.summarize(self.entries, [r])['scifact_v21']['errors'], 1)

    def test_uncertainty_and_unknown_usage_not_correct_or_zero(self):
        report = live.summarize(self.entries, [self.result('uncertain', usage=False)])
        self.assertEqual(report['scifact_v21']['uncertain'], 1)
        self.assertEqual(report['scifact_v21']['missing'], 28)
        self.assertEqual(report['scifact_v21']['correct'], 0)
        self.assertIsNone(report['measured_token_totals']['total_tokens'])
        self.assertEqual(report['usage_unknown_calls'], 1)

    def test_empty_batch_has_no_quality_score(self):
        report = live.summarize(self.entries, [])
        self.assertIsNone(report['scifact_v21']['accuracy_full_denominator'])
        self.assertEqual(report['scifact_v21']['missing'], 29)
        self.assertEqual(report['regression']['missing'], 22)
        self.assertEqual(report['provider_calls'], 0)

    def test_subset_scoring_arithmetic_with_injected_labels(self):
        gold = {r['key']: r['gold_label'] for r in live.read(live.BASE / 'labels.json')}
        outcomes = {e['key']: gold[e['key']] if e['group'] == 'scifact' else 'MISSING' for e in self.entries}
        # Only arithmetic is tested here, not model prediction quality.
        report = live.score29(self.entries, outcomes)
        self.assertEqual(report['correct'], 29)
        self.assertEqual(report['macro_f1'], 1)
        self.assertEqual(report['false_accept_denominator'], 19)
        self.assertEqual(report['positive_block_denominator'], 10)
        self.assertEqual(report['positive_block_count'], 0)

    def test_cache_tampering_rejected(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            row = self.result()
            live.write(out / f"result-{row['key']}.json", row)
            summary = live.finish(out, self.entries, [row])
            self.assertEqual(live.verify_summary(out, self.entries), summary)
            summary['provider_calls'] = 51
            (out / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
            with self.assertRaises(ValueError): live.verify_summary(out, self.entries)


if __name__ == '__main__':
    unittest.main()
