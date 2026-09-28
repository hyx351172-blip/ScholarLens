import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.integration import prepare_qualified_claim_support as prep


class PreparationTests(unittest.TestCase):
    def test_same_52_inputs_no_new_context_or_labels_in_messages(self):
        value = prep.build_preparation()
        self.assertEqual(value['summary']['cases'], 52)
        self.assertEqual(value['summary']['groups'], {'scifact': 30, 'selected_claim_regression': 22})
        self.assertEqual(len({r['key'] for r in value['entries']}), 52)
        self.assertIsNone(value['summary']['semantic_accuracy'])
        self.assertEqual(value['summary']['provider_calls'], 0)
        for row in value['entries']:
            self.assertEqual(row['packet']['base_packet']['packet_id'], row['v1_packet_id'])
            self.assertEqual(len(row['messages']), 2)
            self.assertNotIn('gold_label', row['messages'][1]['content'])
            self.assertNotIn('ai_assessment', row['messages'][1]['content'])
        self.assertEqual(sum(r['gold_label'] is None for r in value['labels']), 22)
        self.assertTrue(all(r['human_verdict'] is None for r in value['labels']))

    def test_four_review_records_are_source_backed_and_not_adjudicated(self):
        review = prep.read(prep.REVIEW)
        self.assertEqual(len(review['cases']), 4)
        self.assertFalse(review['labels_changed'])
        self.assertFalse(review['cases_removed'])
        self.assertEqual(review['original_denominator'], 30)
        self.assertEqual(review['original_correct'], 26)
        prep.validate_review(review)
        bad = copy.deepcopy(review)
        bad['cases'][0]['evidence_quotes'] = ['Invented evidence that is not in the source.']
        with self.assertRaises(ValueError): prep.validate_review(bad)

    def test_review_cannot_change_gold_or_promote_human_verification(self):
        for field, change in (('original_label', 'NOT_ENOUGH_INFO'), ('human_verdict', 'approved'),
                              ('gold_action', 'corrected')):
            bad = prep.read(prep.REVIEW)
            bad['cases'][0][field] = change
            with self.assertRaises(ValueError): prep.validate_review(bad)

    def test_historical_drift_stops_preparation(self):
        with patch.object(prep, 'digest', return_value='0' * 64):
            with self.assertRaises(ValueError): prep.build_preparation()

    def test_export_write_once_and_replay_verifies_hashes(self):
        with TemporaryDirectory() as directory, patch('socket.socket.connect', side_effect=AssertionError('offline')):
            out = Path(directory) / 'prepared'
            report = prep.prepare(out)
            self.assertEqual(report['cases'], 52)
            self.assertEqual(prep.verify_prepared(out)['cases'], 52)
            with self.assertRaises(FileExistsError): prep.prepare(out)
            (out / 'entries.json').write_text('[]', encoding='utf-8')
            with self.assertRaises(ValueError): prep.verify_prepared(out)


if __name__ == '__main__':
    unittest.main()
