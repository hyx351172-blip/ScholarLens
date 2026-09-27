import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.integration import prepare_scifact_verifier as sf


def fixture(count=3):
    claims, corpus = [], []
    for label_index, label in enumerate(sf.LABELS):
        for i in range(count):
            cid = label_index * 100 + i + 1
            did = cid + 1000
            corpus.append(dict(doc_id=did, title=f'Paper {did}', abstract=[
                f'Treatment {cid} was investigated in this study.',
                f'Treatment {cid} improved the measured outcome.',
                'The study did not evaluate other populations.'], structured=False))
            evidence = {} if label == 'NOT_ENOUGH_INFO' else {
                str(did): [dict(label=label, sentences=[1]), dict(label=label, sentences=[0, 1])]}
            claims.append(dict(id=cid, claim=f'Treatment {cid} improves the outcome.',
                               cited_doc_ids=[did], evidence=evidence))
    return claims, corpus


def bundle(count=1):
    return sf.build_bundle(*fixture(), per_class=count, seed='unit-test')


def response(entry, label, *, status='ok'):
    values = {'SUPPORT': ('supported', 'entailed'), 'CONTRADICT': ('unsupported', 'contradicted'),
              'NOT_ENOUGH_INFO': ('unsupported', 'not_in_evidence'),
              'UNCERTAIN': ('uncertain', 'ambiguous_evidence')}
    verdict, reason = values[label]
    p = entry['packet']
    raw = json.dumps(dict(packet_id=p['packet_id'], claim_id=p['claim_id'], verdict=verdict,
                          reason_code=reason, reason='Injected unit-test decision, not a real review.',
                          evidence_ids=[p['selected_anchors'][0]['anchor_id']]))
    return dict(key=entry['key'], request_sha256=sf.value_hash(sf.request_for(p)),
                status=status, raw_content=raw, finish_reason='stop', provider_refusal=False)


class AdapterTests(unittest.TestCase):
    def test_all_labels_receive_full_abstract_and_gold_stays_separate(self):
        claims, corpus = fixture()
        value = sf.build_bundle(claims, corpus, per_class=2)
        lookup = {d['doc_id']: d for d in corpus}
        gold = {g['key']: g for g in value['gold']}
        for e in value['entries']:
            g = gold[e['key']]
            self.assertEqual(''.join(a['text'] for a in e['packet']['selected_anchors']),
                             '\n'.join(lookup[g['doc_id']]['abstract']))
            self.assertEqual(e['packet']['evidence_mode'], 'fixed_v1')
            self.assertIsNone(g['human_verdict'])
            self.assertEqual(len(g['rationale_sets']), 0 if g['label'] == 'NOT_ENOUGH_INFO' else 2)
            request = sf.request_for(e['packet'])
            self.assertEqual(request['max_tokens'], 1000)
            payload = json.loads(request['messages'][1]['content'])
            for field in ('label', 'rationale_sets', 'sentences', 'human_verdict', 'gold'):
                self.assertNotIn(field, payload)
            self.assertNotIn('rationale_sets', json.dumps(request))

    def test_duplicate_ids_missing_documents_and_empty_abstract_fail(self):
        for change in ('duplicate_claim', 'duplicate_doc', 'missing', 'empty'):
            claims, corpus = fixture()
            if change == 'duplicate_claim': claims.append(copy.deepcopy(claims[0]))
            if change == 'duplicate_doc': corpus.append(copy.deepcopy(corpus[0]))
            if change == 'missing': corpus.pop(0)
            if change == 'empty': corpus[0]['abstract'] = []
            with self.assertRaises(ValueError): sf.build_bundle(claims, corpus, per_class=1)

    def test_bad_labels_indices_and_unlabeled_test_rows_fail(self):
        for change in ('mixed_label', 'bad_label', 'bounds', 'negative', 'boolean', 'empty_rationale', 'unlabeled'):
            claims, corpus = fixture()
            rationale = claims[0]['evidence'][str(corpus[0]['doc_id'])]
            if change == 'mixed_label': rationale[1]['label'] = 'CONTRADICT'
            if change == 'bad_label': rationale[0]['label'] = 'REFUTES'
            if change == 'bounds': rationale[0]['sentences'] = [3]
            if change == 'negative': rationale[0]['sentences'] = [-1]
            if change == 'boolean': rationale[0]['sentences'] = [True]
            if change == 'empty_rationale': rationale[0]['sentences'] = []
            if change == 'unlabeled': del claims[0]['evidence']
            with self.assertRaises(ValueError): sf.build_bundle(claims, corpus, per_class=1)

    def test_unannotated_neighbor_of_positive_not_mislabeled_as_nei(self):
        claims, corpus = fixture()
        claims[0]['cited_doc_ids'].append(corpus[-1]['doc_id'])
        value = sf.build_bundle(claims, corpus, per_class=1)
        self.assertEqual(value['audit']['candidate_pairs'], len(claims))

    def test_duplicate_cited_ids_are_audited_without_duplicate_pairs(self):
        claims, corpus = fixture()
        claims[-1]['cited_doc_ids'] *= 2
        value = sf.build_bundle(claims, corpus, per_class=1)
        self.assertEqual(value['audit']['candidate_pairs'], len(claims))
        self.assertEqual(value['audit']['annotation_warnings'], [dict(
            claim_id=claims[-1]['id'], reason='duplicate_cited_document_ids',
            original=claims[-1]['cited_doc_ids'], unique=claims[-1]['cited_doc_ids'][:1])])

    def test_noncanonical_evidence_doc_id_is_rejected(self):
        claims, corpus = fixture()
        evidence = claims[0]['evidence']
        key = next(iter(evidence))
        claims[0]['evidence'] = {'0' + key: evidence[key]}
        with self.assertRaises(ValueError): sf.build_bundle(claims, corpus, per_class=1)


class SamplingTests(unittest.TestCase):
    def test_reordered_inputs_same_selection_and_packets(self):
        claims, corpus = fixture(10)
        a = sf.build_bundle(claims, corpus, per_class=3, seed='frozen')
        b = sf.build_bundle(list(reversed(claims)), list(reversed(corpus)), per_class=3, seed='frozen')
        self.assertEqual(a, b)
        self.assertEqual(len({g['claim_id'] for g in a['gold']}), 9)
        self.assertEqual(len({g['doc_id'] for g in a['gold']}), 9)
        self.assertEqual(a['summary']['label_counts'], dict.fromkeys(sf.LABELS, 3))

    def test_same_paper_or_normalized_claim_is_not_repeated(self):
        claims, corpus = fixture(10)
        claims[1]['claim'] = claims[0]['claim'].upper()
        claims[2]['cited_doc_ids'] = claims[0]['cited_doc_ids']
        claims[2]['evidence'] = copy.deepcopy(claims[0]['evidence'])
        value = sf.build_bundle(claims, corpus, per_class=8)
        self.assertEqual(len({g['doc_id'] for g in value['gold']}), 24)
        self.assertEqual(len({e['packet']['claim'].casefold() for e in value['entries']}), 24)

    def test_long_abstract_excluded_not_truncated_and_invalid_claim_logged(self):
        claims, corpus = fixture(4)
        corpus[0]['abstract'] = [' '.join(['word'] * 1200)]
        # Keep rationales valid while testing the transport eligibility filter.
        corpus[0]['abstract'] += ['Other result.', 'Another result.']
        claims[1]['claim'] = 'First sentence. Another sentence.'
        value = sf.build_bundle(claims, corpus, per_class=1)
        excluded = value['audit']['excluded_pairs']
        self.assertTrue(any(e['reason'] == 'abstract_exceeds_eight_anchors' for e in excluded))
        self.assertTrue(any(e['reason'] == 'claim_contract_rejected' for e in excluded))
        self.assertFalse({1, 2} & {g['claim_id'] for g in value['gold']})

    def test_insufficient_balance_or_invalid_budget_fails(self):
        for count in (0, True, 4):
            with self.assertRaises(ValueError): sf.build_bundle(*fixture(), per_class=count)


class PreparationTests(unittest.TestCase):
    def test_export_write_once_hash_verified_and_zero_calls(self):
        value = bundle()
        with TemporaryDirectory() as directory, patch('socket.socket.connect', side_effect=AssertionError('offline')):
            out = Path(directory) / 'prepared'
            sf.export_bundle(value, out, source_hashes={})
            self.assertEqual(sf.verify_prepared(out)['planned_calls'], 3)
            report = sf.read(out / 'summary.json')
            self.assertEqual(report['provider_calls'], 0)
            self.assertIsNone(report['accuracy'])
            self.assertEqual(report['status'], 'prepared_not_run')
            with self.assertRaises(FileExistsError): sf.export_bundle(value, out, source_hashes={})
            # A changed label artifact must block, even though labels are not in the prompt.
            (out / 'gold.json').write_text('[]', encoding='utf-8')
            with self.assertRaises(ValueError): sf.verify_prepared(out)

    def test_changed_request_or_source_hash_blocks(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'prepared'
            sf.export_bundle(bundle(), out, source_hashes={})
            path = next(out.glob('request-*.json'))
            path.write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError): sf.verify_prepared(out)

    def test_history_is_intact_without_network(self):
        checks = sf.verify_history()
        self.assertGreaterEqual(len(checks), 200)


class ScoringTests(unittest.TestCase):
    def test_perfect_injected_decisions_and_contradiction_nei_mapping(self):
        value = bundle()
        labels = {g['key']: g['label'] for g in value['gold']}
        results = [response(e, labels[e['key']]) for e in value['entries']]
        report = sf.score(value['entries'], value['gold'], results)
        self.assertEqual(report['accuracy_full_denominator'], 1)
        self.assertEqual(report['macro_f1'], 1)
        self.assertEqual(report['false_accept_count'], 0)
        self.assertEqual(report['positive_block_count'], 0)

    def test_all_supported_exposes_false_accepts(self):
        value = bundle()
        report = sf.score(value['entries'], value['gold'], [response(e, 'SUPPORT') for e in value['entries']])
        self.assertAlmostEqual(report['accuracy_full_denominator'], 1 / 3)
        self.assertEqual(report['false_accept_count'], 2)
        self.assertEqual(report['false_accept_denominator'], 2)
        self.assertEqual(report['false_accept_rate'], 1)

    def test_uncertain_never_counts_as_correct_nei(self):
        value = bundle()
        report = sf.score(value['entries'], value['gold'], [response(e, 'UNCERTAIN') for e in value['entries']])
        self.assertEqual(report['accuracy_full_denominator'], 0)
        self.assertEqual(report['uncertain'], 3)
        self.assertEqual(report['confusion']['NOT_ENOUGH_INFO']['UNCERTAIN'], 1)
        self.assertEqual(report['positive_block_count'], 1)
        self.assertEqual(report['positive_negative_verdict_count'], 0)

    def test_errors_missing_and_partial_results_keep_denominator(self):
        value = bundle()
        report = sf.score(value['entries'], value['gold'], [response(value['entries'][0], 'SUPPORT', status='error')])
        self.assertEqual(report['total'], 3)
        self.assertEqual(report['errors'], 1)
        self.assertEqual(report['missing'], 2)
        self.assertFalse(report['complete'])
        self.assertEqual(report['accuracy_full_denominator'], 0)

    def test_invalid_raw_id_truncation_or_reason_pair_is_error(self):
        value = bundle()
        for change in ('identity', 'reason', 'truncated', 'refused', 'json'):
            result = response(value['entries'][0], 'SUPPORT')
            obj = json.loads(result['raw_content'])
            if change == 'identity': obj['packet_id'] = 'wrong'
            if change == 'reason': obj['reason_code'] = 'contradicted'
            result['raw_content'] = json.dumps(obj)
            if change == 'truncated': result['finish_reason'] = 'length'
            if change == 'refused': result['provider_refusal'] = True
            if change == 'json': result['raw_content'] = '{}'
            report = sf.score(value['entries'], value['gold'], [result])
            self.assertEqual(report['errors'], 1)

    def test_unknown_duplicate_or_unbound_results_fail_closed(self):
        value = bundle()
        result = response(value['entries'][0], 'SUPPORT')
        for results in ([result, result], [dict(result, key='other')], [dict(result, request_sha256='bad')]):
            with self.assertRaises(ValueError): sf.score(value['entries'], value['gold'], results)

    def test_zero_results_are_not_zero_accuracy(self):
        value = bundle()
        report = sf.score(value['entries'], value['gold'], [])
        self.assertEqual(report['missing'], 3)
        self.assertIsNone(report['accuracy_full_denominator'])
        self.assertIsNone(report['macro_f1'])


if __name__ == '__main__':
    unittest.main()
