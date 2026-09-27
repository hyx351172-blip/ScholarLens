import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.integration import prepare_qualified_evidence_ids as prep


class PreparationTests(unittest.TestCase):
    def test_same_52_sources_no_gold_in_requests_no_live_approval(self):
        with patch('socket.socket.connect', side_effect=AssertionError('offline')):
            value = prep.build_preparation()
        old = {e['key']: e for e in prep.read(prep.previous.BASE / 'entries.json')}
        self.assertEqual(value['summary']['groups'], {'scifact': 30, 'selected_claim_regression': 22})
        self.assertEqual(len(value['entries']), 52)
        self.assertEqual(value['summary']['new_provider_calls'], 0)
        self.assertIsNone(value['summary']['semantic_accuracy'])
        self.assertFalse(value['summary']['future_call_proposal']['approved'])
        for e in value['entries']:
            self.assertEqual(e['packet']['base_packet'], old[e['key']]['packet']['base_packet'])
            self.assertNotEqual(e['packet']['packet_id'], old[e['key']]['packet']['packet_id'])
            request = prep.request_for(e['packet'])
            self.assertNotIn('gold_label', request['messages'][1]['content'])
            self.assertNotIn('human_verdict', request['messages'][1]['content'])
            self.assertEqual(request['max_tokens'], 1500)
        self.assertEqual(sum(r['gold_label'] is None for r in value['labels']), 22)

    def test_saved_responses_are_only_labelled_simulations_not_new_reviews(self):
        data = prep.build_preparation(); sims = data['simulations']; s = data['summary']
        self.assertEqual(len(sims), 6)
        self.assertEqual(s['simulated_contract_valid'], 6)
        self.assertEqual(s['historical_responses'], 6)
        self.assertEqual(s['v3_live_responses'], 0)
        self.assertEqual(s['v3_not_run'], 52)
        self.assertEqual(s['unmodified_old_rejected'], 6)
        self.assertTrue(all(c['origin'] == 'schema_adapter_simulation_not_model_review' for c in sims))
        self.assertTrue(all(c['human_verdict'] is None for c in sims))
        for c in sims:
            self.assertFalse(c['decision']['semantic_verified'])
            e = next(e for e in data['entries'] if e['key'] == c['key'])
            anchors = {a['anchor_id']: a for a in e['packet']['base_packet']['selected_anchors']}
            for check in c['decision']['checks'].values():
                for cite in check['citations']:
                    self.assertEqual(cite['quote'], anchors[cite['anchor_id']]['text'])
        failed = next(c for c in sims if c['key'] == 'SCIFACT-SF-415-6309659')
        self.assertEqual(failed['original_status'], 'error')
        self.assertEqual(failed['old_v21_error'], 'missing_quote')
        self.assertTrue(any(q.get('error') == 'missing_quote' for q in failed['old_quote_audit']))
        self.assertEqual(failed['decision']['verdict'], 'unsupported')
        self.assertEqual(failed['decision']['reason_code'], 'not_in_evidence')

    def test_adapter_rejects_foreign_identity_and_bad_citation(self):
        old_entry = prep.read(prep.previous.BASE / 'entries.json')[0]
        result = prep.read(prep.previous.BASE / 'results.json')[0]
        p = prep.v3.from_v1_packet(old_entry['packet']['base_packet'])
        import json
        obj = json.loads(result['raw_content'])
        for kind in ('id', 'anchor', 'extra'):
            bad = copy.deepcopy(obj)
            if kind == 'id': bad['packet_id'] = 'wrong'
            if kind == 'anchor': bad['checks']['content']['citations'][0]['anchor_id'] = 'S99:E9999'
            if kind == 'extra': bad['checks']['content']['citations'][0]['start'] = 0
            with self.assertRaises(ValueError): prep.adapt_for_simulation(json.dumps(bad), old_entry['packet'], p)

    def test_frozen_history_drift_rejected(self):
        with patch.object(prep, 'PREVIOUS_SUMMARY_SHA256', '0' * 64):
            with self.assertRaises(ValueError): prep.build_preparation()

    def test_export_write_once_rebuild_and_tamper_check(self):
        with TemporaryDirectory() as directory, patch('socket.socket.connect', side_effect=AssertionError('offline')):
            out = Path(directory) / 'prep'
            summary = prep.prepare(out)
            self.assertEqual(prep.verify_prepared(out), summary)
            with self.assertRaises(FileExistsError): prep.prepare(out)
            (out / 'simulations.json').write_text('[]', encoding='utf-8')
            with self.assertRaises(ValueError): prep.verify_prepared(out)


if __name__ == '__main__':
    unittest.main()
