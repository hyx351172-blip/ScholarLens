import copy
import itertools
import json
import unittest
from unittest.mock import patch

from backend.chat import qualified_evidence_ids as v3
from backend.chat import selected_claim_support as v1
from backend.chat import qualified_claim_support as v2
from tests.test_qualified_claim_support import QUESTION, DOCS, raw, plan, decision


def packet(claim='New drugs often do not penetrate the tissue.', docs=None):
    return v3.from_v1_packet(plan(claim, docs)['packets'][0]['base_packet'])


def response(p, **scope):
    value = decision(p, **scope)
    for check in value['checks'].values():
        check['evidence_ids'] = [c['anchor_id'] for c in check.pop('citations')]
    return value


def parse(p, value):
    return v3.parse_decision(json.dumps(value, ensure_ascii=False), p)


class PacketTests(unittest.TestCase):
    def test_new_identity_preserves_deep_copied_evidence(self):
        base = plan()['packets'][0]['base_packet']; before = copy.deepcopy(base)
        p = v3.from_v1_packet(base)
        self.assertEqual(p['base_packet'], before)
        self.assertNotEqual(p['packet_id'], v2.from_v1_packet(base)['packet_id'])
        p['base_packet']['selected_anchors'][0]['text'] = 'mutated'
        self.assertEqual(base, before)

    def test_messages_preserve_semantic_prefix_and_only_change_citation_policy(self):
        p = packet(); system, user = v3.review_messages(p)
        prefix = v2.POLICY.split('Every entailed or contradicted check requires', 1)[0]
        self.assertTrue(system['content'].startswith(prefix))
        self.assertIn('evidence_ids', system['content'])
        self.assertNotIn('"quote":', system['content'])
        self.assertEqual(json.loads(user['content']), p)
        self.assertNotIn('gold_label', user['content'])

    def test_no_sibling_evidence(self):
        docs = [dict(chunk_text='Drug X works. Sibling fact must not be borrowed.')]
        output = json.dumps(dict(status='answered', claims=[dict(text='Drug X works.', evidence_ids=['S1:U0001'])]))
        p = v3.prepare_review(QUESTION, docs, output)['packets'][0]
        self.assertNotIn('Sibling fact', v3.review_messages(p)[1]['content'])

    def test_tampered_packet_rejected(self):
        for kind in ('id', 'base', 'cue', 'extra', 'version'):
            p = packet()
            if kind == 'id': p['packet_id'] = '0' * 64
            if kind == 'base': p['base_packet']['claim'] += ' altered'
            if kind == 'cue': p['risk_cues'] = []
            if kind == 'extra': p['gold_label'] = 'SUPPORT'
            if kind == 'version': p['version'] = v2.VERSION
            with self.subTest(kind=kind), self.assertRaises(ValueError): v3.review_messages(p)

    def test_bad_anchor_types_and_bounds_fail_with_valueerror(self):
        for field, value in (('anchor_id', 3), ('text', None), ('start', True), ('end', -1),
                             ('filename', []), ('text', 'x' * 64001)):
            base = packet()['base_packet']; a = base['selected_anchors'][0]; a[field] = value
            if field == 'text' and isinstance(value, str): a['end'] = a['start'] + len(value)
            base['packet_id'] = v1._packet_id(base)
            with self.subTest(field=field), self.assertRaises(ValueError): v3.from_v1_packet(base)

    def test_unicode_and_risk_cue_offsets_preserved(self):
        p = packet('药物并不总是能进入组织。')
        self.assertTrue(p['risk_cues'])
        for cue in p['risk_cues']:
            self.assertEqual(p['base_packet']['claim'][cue['start']:cue['end']], cue['text'])


class DecisionTests(unittest.TestCase):
    def test_citations_are_entire_original_anchor_not_model_quotes(self):
        p = packet(); value = response(p); result = parse(p, value)
        a = p['base_packet']['selected_anchors'][0]
        c = result['checks']['content']['citations'][0]
        self.assertEqual(c['quote'], a['text'])
        self.assertEqual((c['source_start'], c['source_end']), (a['start'], a['end']))
        self.assertEqual(c['granularity'], 'selected_anchor')
        self.assertEqual(c['provenance'], 'program_resolved_id')
        self.assertEqual(result['checks']['content']['evidence_ids'], [a['anchor_id']])
        self.assertNotIn('model_quote', c)
        self.assertEqual(value, response(p))

    def test_repeated_text_newlines_unicode_and_math_are_not_normalized(self):
        p = packet(docs=[dict(chunk_text='重复🙂 α/r\r\nSame. Same.\t原文 [...] 保留。')])
        c = parse(p, response(p))['checks']['content']['citations'][0]
        self.assertEqual(c['quote'], p['base_packet']['selected_anchors'][0]['text'])
        self.assertEqual(c['source_end'] - c['source_start'], len(c['quote']))

    def test_nonzero_source_coordinates_and_noncontiguous_ids(self):
        docs = [dict(chunk_text='First fact. Unselected gap. Third fact.')]
        text = json.dumps(dict(status='answered', claims=[dict(text='Two facts.', evidence_ids=['S1:U0001', 'S1:U0003'])]))
        p = v3.prepare_review(QUESTION, docs, text)['packets'][0]
        value = response(p)
        value['checks']['content']['evidence_ids'] = [a['anchor_id'] for a in p['base_packet']['selected_anchors']]
        cs = parse(p, value)['checks']['content']['citations']
        self.assertEqual(len(cs), 2)
        self.assertGreater(cs[1]['source_start'], cs[0]['source_end'])
        self.assertNotIn('Unselected', ''.join(c['quote'] for c in cs))
        for c in cs:
            self.assertEqual(c['quote'], docs[0]['chunk_text'][c['source_start']:c['source_end']])

    def test_invalid_duplicate_unselected_and_wrong_type_ids_rejected(self):
        p = packet(); selected = p['base_packet']['selected_anchors'][0]['anchor_id']
        for ids in (None, selected, [selected, selected], ['S99:E0001'], [1], [{}], [selected] * 4, []):
            value = response(p); value['checks']['content']['evidence_ids'] = ids
            with self.subTest(ids=ids), self.assertRaises(ValueError): parse(p, value)

    def test_unknown_ids_rejected_even_for_missing_or_uncertain(self):
        p = packet()
        for status in ('missing', 'uncertain'):
            value = response(p); value['checks']['content'].update(status=status, evidence_ids=['S99:E0001'])
            with self.assertRaises(ValueError): parse(p, value)

    def test_optional_evidence_vs_required_evidence(self):
        p = packet()
        for status in v2.STATES:
            value = response(p); value['checks']['content'].update(status=status, evidence_ids=[])
            if status in ('entailed', 'contradicted'):
                with self.assertRaises(ValueError): parse(p, value)
            else:
                self.assertEqual(parse(p, value)['checks']['content']['citations'], [])

    def test_quote_offsets_extra_checks_and_overall_verdict_rejected(self):
        for field, extra in (('quote', 'invented [...]'), ('citations', []), ('start', 0), ('end', 1)):
            p = packet(); value = response(p); value['checks']['content'][field] = extra
            with self.subTest(field=field), self.assertRaises(ValueError): parse(p, value)
        for change in ('overall', 'fourth', 'missing_facet', 'wrong_scope', 'reason_size', 'status'):
            value = response(p)
            if change == 'overall': value['verdict'] = 'supported'
            if change == 'fourth': value['checks']['extra'] = {}
            if change == 'missing_facet': del value['checks']['content']
            if change == 'wrong_scope': value['checks']['scope']['relation'] = []
            if change == 'reason_size': value['checks']['content']['reason'] = 'x' * 601
            if change == 'status': value['checks']['content']['status'] = []
            with self.subTest(change=change), self.assertRaises(ValueError): parse(p, value)

    def test_old_or_cross_packet_responses_rejected(self):
        p = packet()
        with self.assertRaises(ValueError): parse(p, decision(p))
        value = response(p); value['packet_id'] = packet('A different claim.')['packet_id']
        with self.assertRaises(ValueError): parse(p, value)
        value = response(p); value['claim_id'] = 'C002'
        with self.assertRaises(ValueError): parse(p, value)

    def test_malformed_json_and_resource_bounds(self):
        p = packet(); encoded = json.dumps(response(p))
        for value in (None, '', '[]', encoded + '{}', encoded[:-1] + ',"checks":{}}',
                      encoded.replace('"entailed"', 'NaN', 1), '[' * 2000 + '0' + ']' * 2000, 'x' * 24001):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError): v3.parse_decision(value, p)


class SemanticParityTests(unittest.TestCase):
    def test_all_rule_combinations_match_v2(self):
        for claim in ('Drugs often work.', 'Drug X works.', 'Not all drugs work.'):
            p = packet(claim); old = v2.from_v1_packet(p['base_packet'])
            for states, basis, relation in itertools.product(itertools.product(sorted(v2.STATES), repeat=3), sorted(v2.BASES), sorted(v2.RELATIONS)):
                new = response(p, basis=basis, relation=relation); prior = decision(old, basis=basis, relation=relation)
                for facet, status in zip(v2.FACETS, states):
                    new['checks'][facet]['status'] = prior['checks'][facet]['status'] = status
                actual, expected = parse(p, new), v2.parse_decision(json.dumps(prior), old)
                for key in ('verdict', 'reason_code', 'guard_codes', 'effective_checks'):
                    self.assertEqual(actual[key], expected[key], (claim, states, basis, relation, key))

    def test_valid_ids_do_not_prove_entailment(self):
        p = packet('A knowingly unsupported invented claim.')
        result = parse(p, response(p))
        self.assertEqual(result['verdict'], 'supported')
        self.assertFalse(result['semantic_verified']); self.assertFalse(result['human_verified'])


class GateTests(unittest.TestCase):
    def test_opt_in_supported_gate_keeps_answer(self):
        claim = 'Drug X does not penetrate the tissue.'
        p = packet(claim)
        with patch('socket.socket.connect', side_effect=AssertionError('offline')):
            result = v3.gate_answer(QUESTION, DOCS, raw(claim), {'C001': json.dumps(response(p))}, evidence_mode='fixed_v1')
        self.assertTrue(result['release_allowed'])
        self.assertEqual(result['answer'], plan(claim)['candidate_answer'])
        self.assertFalse(result['semantic_verified'])

    def test_missing_invalid_stale_and_extra_reviews_fail_closed(self):
        for reviews, expected in (({}, 'review_incomplete'), ([], 'review_invalid'),
                                  ({'C999': '{}'}, 'review_invalid'), ({'C001': '{}'}, 'review_invalid'),
                                  ({'C001': json.dumps(response(packet('Another claim.')))}, 'review_invalid')):
            result = v3.gate_answer(QUESTION, DOCS, raw(), reviews, evidence_mode='fixed_v1')
            self.assertEqual(result['status'], expected); self.assertFalse(result['release_allowed'])

    def test_one_unsupported_claim_blocks_whole_candidate(self):
        output = json.dumps(dict(status='answered', claims=[dict(text='Drug X works.', evidence_ids=['S1:E0001']), dict(text='Drugs often work.', evidence_ids=['S1:E0001'])]))
        prepared = v3.prepare_review(QUESTION, DOCS, output, evidence_mode='fixed_v1')
        replies = {p['base_packet']['claim_id']: json.dumps(response(p, basis='single_example')) for p in prepared['packets']}
        result = v3.gate_answer(QUESTION, DOCS, output, replies, evidence_mode='fixed_v1')
        self.assertEqual(result['status'], 'review_unsupported'); self.assertFalse(result['release_allowed'])

    def test_no_evidence_invalid_and_insufficient_remain_distinct(self):
        for docs, output, expected in (([], None, 'no_evidence'), (DOCS, '{}', 'invalid_claim_structure'),
                                      (DOCS, '{"status":"insufficient","claims":[]}', 'claim_bound_insufficient')):
            result = v3.gate_answer(QUESTION, docs, output, {}, evidence_mode='fixed_v1')
            self.assertEqual(result['status'], expected); self.assertFalse(result['release_allowed'])


if __name__ == '__main__':
    unittest.main()
