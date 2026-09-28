import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock

from tests.integration import run_scifact_verifier_live as live
from tests.test_selected_claim_support_live import Client, response


class PreparationTests(unittest.TestCase):
    def test_exact_label_blind_write_once_requests(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'
            summary = live.prepare(out)
            self.assertEqual(summary['planned_calls'], 30)
            entries = live.preflight(out, True, 30)
            self.assertEqual(len(entries), 30)
            self.assertEqual(entries, live.read(live.BASE / 'entries.json'))
            for e in entries:
                saved = live.read(out / f"request-{e['key']}.json")
                self.assertEqual(saved, live.read(live.BASE / f"request-{e['key']}.json"))
                self.assertNotIn('rationale_sets', json.dumps(saved))
                self.assertEqual(saved['max_tokens'], 1000)
            with self.assertRaises(FileExistsError): live.prepare(out)

    def test_drift_blocks_before_run(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            path = next(out.glob('request-*.json'))
            path.write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError): live.preflight(out, True, 30)


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_approval_no_credentials(self):
        for approved, budget in ((False, 30), (True, 29), (True, 31), (True, True)):
            factory = Mock(side_effect=AssertionError('no credentials'))
            with self.assertRaises(ValueError):
                await live.run(approved, budget, client_factory=factory)
            factory.assert_not_called()

    async def test_thirty_calls_score_and_cached_reentry(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            async def reply(**request):
                self.assertTrue((out / 'run-started.json').exists())
                self.assertEqual(len(list(out.glob('attempt-*.json'))), provider.await_count)
                return response(request)
            provider = AsyncMock(side_effect=reply)
            summary = await live.run(True, 30, out, client_factory=lambda: (Client(provider), 'fake-secret'))
            self.assertEqual(provider.await_count, 30)
            self.assertEqual(summary['status'], 'completed')
            self.assertEqual(summary['provider_calls'], 30)
            self.assertAlmostEqual(summary['metrics']['accuracy_full_denominator'], 1 / 3)
            self.assertEqual(summary['metrics']['false_accept_count'], 20)
            cards = live.read(out / 'review-cards.json')
            self.assertEqual(len(cards), 30)
            self.assertTrue(all(c['human_verdict'] is None for c in cards))
            positive = next(c for c in cards if c['gold']['label'] == 'SUPPORT')
            self.assertTrue(positive['gold_rationale_texts'])
            self.assertEqual(live.read(out / 'metrics.json'), summary['metrics'])
            factory = Mock(side_effect=AssertionError('no repeat calls'))
            self.assertEqual(await live.run(True, 30, out, client_factory=factory), summary)
            factory.assert_not_called()

    async def test_error_stops_and_keeps_thirty_case_denominator(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            provider = AsyncMock(side_effect=RuntimeError('fake-secret'))
            summary = await live.run(True, 30, out, client_factory=lambda: (Client(provider), 'fake-secret'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(summary['status'], 'stopped_error')
            self.assertEqual(summary['metrics']['total'], 30)
            self.assertEqual(summary['metrics']['errors'], 1)
            self.assertEqual(summary['metrics']['missing'], 29)
            self.assertIsNone(summary['measured_token_totals']['total_tokens'])
            self.assertNotIn('fake-secret', (out / 'results.json').read_text(encoding='utf-8'))
            factory = Mock(side_effect=AssertionError('no automatic retry'))
            await live.run(True, 30, out, client_factory=factory)
            factory.assert_not_called()

    async def test_truncation_stops_without_retry(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            provider = AsyncMock(side_effect=lambda **r: response(r, finish='length'))
            summary = await live.run(True, 30, out, client_factory=lambda: (Client(provider), 'secret'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(summary['metrics']['errors'], 1)
            self.assertEqual(summary['finish_reason_counts'], {'length': 1})

    async def test_secret_echo_is_redacted_and_not_scored_as_success(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            def echo(**request):
                value = response(request)
                raw = json.loads(value.choices[0].message.content)
                raw['reason'] = 'private-test-key'
                value.choices[0].message.content = json.dumps(raw)
                return value
            provider = AsyncMock(side_effect=echo)
            summary = await live.run(True, 30, out, client_factory=lambda: (Client(provider), 'private-test-key'))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(summary['metrics']['errors'], 1)
            self.assertNotIn('private-test-key', (out / 'results.json').read_text(encoding='utf-8'))

    async def test_interrupted_and_orphan_runs_do_not_resume(self):
        key = live.read(live.BASE / 'entries.json')[0]['key']
        for marker in ('run-started.json', f'attempt-{key}.json', f'result-{key}.json'):
            with TemporaryDirectory() as directory:
                out = Path(directory) / 'run'; live.prepare(out)
                live.write(out / marker, {})
                factory = Mock(side_effect=AssertionError('must not initialize client'))
                with self.assertRaises(ValueError): await live.run(True, 30, out, client_factory=factory)
                factory.assert_not_called()

    async def test_concurrent_invocation_cannot_double_spend(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'run'; live.prepare(out)
            async def reply(**request):
                await asyncio.sleep(0)
                return response(request)
            provider = AsyncMock(side_effect=reply)
            factory = Mock(return_value=(Client(provider), 'fake-secret'))
            outcomes = await asyncio.gather(
                live.run(True, 30, out, client_factory=factory),
                live.run(True, 30, out, client_factory=factory), return_exceptions=True)
            self.assertEqual(provider.await_count, 30)
            self.assertEqual(sum(isinstance(x, ValueError) for x in outcomes), 1)


class SummaryTests(unittest.TestCase):
    def test_missing_usage_and_uncertain_not_nei(self):
        entries = live.read(live.BASE / 'entries.json')
        request = live.request_for(entries[0]['packet'])
        row = dict(entries[0], case_id=entries[0]['key'])
        provider = AsyncMock(return_value=response(request, 'uncertain', 'ambiguous_evidence', usage=False))
        result = asyncio.run(live.judge(row, request, provider))
        summary = live.summarize(entries, [result])
        self.assertEqual(summary['metrics']['uncertain'], 1)
        self.assertEqual(summary['metrics']['missing'], 29)
        self.assertEqual(summary['metrics']['correct'], 0)
        self.assertIsNone(summary['measured_token_totals']['total_tokens'])
        self.assertEqual(summary['usage_unknown_calls'], 1)


if __name__ == '__main__':
    unittest.main()
