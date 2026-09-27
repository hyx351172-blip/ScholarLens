from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.integration import replay_qualified_quote_alignment as replay


class ReplayTests(unittest.TestCase):
    def test_zero_call_replay_preserves_52_and_missing_denominator(self):
        with patch.object(replay.live, 'make_client', side_effect=AssertionError('no credentials or client')) as factory:
            data = replay.build_replay()
        factory.assert_not_called()
        s = data['summary']
        self.assertEqual(s['planned_claims'], 52)
        self.assertEqual(s['saved_responses'], 1)
        self.assertEqual(s['not_run'], 51)
        self.assertEqual(s['v21_contract_valid'], 1)
        self.assertEqual(s['v21_contract_invalid'], 0)
        self.assertEqual(s['new_provider_calls'], 0)
        self.assertEqual(s['citation_match_counts'], {'whitespace_only': 1, 'exact': 5})
        self.assertIsNone(s['semantic_accuracy'])
        self.assertEqual(data['cases'][0]['original_status'], 'error')
        self.assertEqual(data['cases'][0]['replay_status'], 'contract_valid')
        self.assertTrue(all(r['human_verdict'] is None for r in data['cases']))

    def test_export_is_write_once_and_verifiable(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'replay'
            result = replay.export(out)
            self.assertEqual(replay.verify_export(out), result)
            with self.assertRaises(FileExistsError): replay.export(out)
            (out / 'summary.json').write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError): replay.verify_export(out)

    def test_baseline_drift_blocks_offline_replay(self):
        with patch.object(replay, 'BASE_SUMMARY_SHA256', '0' * 64):
            with self.assertRaises(ValueError): replay.build_replay()


if __name__ == '__main__':
    unittest.main()
