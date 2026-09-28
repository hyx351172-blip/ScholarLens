import copy
import json
import unittest

from backend.chat import selected_claim_support as v1
from backend.chat import qualified_claim_support as v2

DOCS = [dict(filename='study.txt', chunk_text='Drug X does not penetrate the tissue. The study examined one drug.')]
QUESTION = 'What does this study establish?'


def raw(claim='New drugs often do not penetrate the tissue.'):
    return json.dumps(dict(status='answered', claims=[dict(text=claim, evidence_ids=['S1:E0001'])]))


def plan(claim='New drugs often do not penetrate the tissue.', docs=None):
    return v2.prepare_review(QUESTION, docs or DOCS, raw(claim), evidence_mode='fixed_v1')


def decision(packet, *, basis='explicit_statement', relation='same_or_narrower'):
    base = packet['base_packet']
    anchor = base['selected_anchors'][0]
    cite = dict(anchor_id=anchor['anchor_id'], quote=anchor['text'])
    checks = {name: dict(status='entailed', reason='Injected contract-test assertion, not semantic ground truth.',
                         citations=[copy.deepcopy(cite)]) for name in ('content', 'scope', 'conditions')}
    checks['scope'].update(basis=basis, relation=relation)
    return dict(packet_id=packet['packet_id'], claim_id=base['claim_id'], checks=checks)


def parsed(packet, value):
    return v2.parse_decision(json.dumps(value, ensure_ascii=False), packet)


class PacketTests(unittest.TestCase):
    def test_wrapper_preserves_original_packet_and_claim_spans(self):
        before = v1.prepare_review(QUESTION, DOCS, raw(), evidence_mode='fixed_v1')['packets'][0]
        saved = copy.deepcopy(before)
        packet = v2.from_v1_packet(before)
        self.assertEqual(before, saved)
        self.assertEqual(packet['base_packet'], before)
        self.assertNotEqual(packet['packet_id'], before['packet_id'])
        cues = packet['risk_cues']
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0]['kind'], 'generalization')
        self.assertEqual(before['claim'][cues[0]['start']:cues[0]['end']], 'often')

    def test_only_selected_anchor_and_no_sibling_text(self):
        docs = [dict(chunk_text='Drug X works. A secret unrelated result.')]
        output = json.dumps(dict(status='answered', claims=[dict(text='Drug X works.', evidence_ids=['S1:U0001'])]))
        packet = v2.prepare_review(QUESTION, docs, output)['packets'][0]
        system, user = v2.review_messages(packet)
        self.assertNotIn('secret unrelated', user['content'])
        self.assertEqual(system['content'], v2.POLICY)
        self.assertNotIn('human_verdict', user['content'])

    def test_cue_lexicon_has_boundaries_and_chinese_offsets(self):
        text = 'Methods generally work when warmed; 通常只有在升温后生效。'
        cues = v2.risk_cues(text)
        self.assertIn('generally', [c['text'] for c in cues])
        self.assertIn('when', [c['text'] for c in cues])
        self.assertIn('通常', [c['text'] for c in cues])
        self.assertTrue(all(text[c['start']:c['end']] == c['text'] for c in cues))
        self.assertEqual(v2.risk_cues('Small objects allow a shift.'), [])

    def test_tampered_base_cues_and_policy_fingerprints_fail(self):
        packet = plan()['packets'][0]
        for kind in ('claim', 'anchor', 'cues', 'id', 'extra'):
            bad = copy.deepcopy(packet)
            if kind == 'claim': bad['base_packet']['claim'] += ' altered'
            if kind == 'anchor': bad['base_packet']['selected_anchors'][0]['text'] = 'forged'
            if kind == 'cues': bad['risk_cues'] = []
            if kind == 'id': bad['packet_id'] = '0' * 64
            if kind == 'extra': bad['gold'] = 'SUPPORT'
            with self.assertRaises(ValueError): v2.review_messages(bad)

    def test_old_decision_cannot_pass_new_contract(self):
        packet = plan()['packets'][0]
        old = dict(packet_id=packet['base_packet']['packet_id'], claim_id='C001', verdict='supported',
                   reason_code='entailed', reason='Old response.', evidence_ids=['S1:E0001'])
        with self.assertRaises(ValueError): parsed(packet, old)


class DecisionTests(unittest.TestCase):
    def setUp(self): self.packet = plan()['packets'][0]

    def test_three_required_checks_and_source_derived_offsets(self):
        result = parsed(self.packet, decision(self.packet))
        quote = result['checks']['content']['citations'][0]
        self.assertEqual(quote['quote'], DOCS[0]['chunk_text'][quote['source_start']:quote['source_end']])
        self.assertEqual(result['verdict'], 'supported')
        self.assertFalse(result['semantic_verified'])

    def test_quote_offsets_are_source_relative_not_anchor_relative(self):
        docs = [dict(chunk_text='A neighboring fact. Drug X does not penetrate the tissue.')]
        output = json.dumps(dict(status='answered', claims=[dict(text='Drug X does not penetrate the tissue.', evidence_ids=['S1:U0002'])]))
        packet = v2.prepare_review(QUESTION, docs, output)['packets'][0]
        value = decision(packet)
        citation = value['checks']['content']['citations'][0]
        citation['quote'] = 'does not penetrate'
        result = parsed(packet, value)['checks']['content']['citations'][0]
        self.assertGreater(result['source_start'], packet['base_packet']['selected_anchors'][0]['start'])
        self.assertEqual(docs[0]['chunk_text'][result['source_start']:result['source_end']], citation['quote'])

    def test_missing_extra_checks_or_model_overall_verdict_rejected(self):
        for kind in ('missing', 'extra_check', 'overall', 'extra_field'):
            value = decision(self.packet)
            if kind == 'missing': del value['checks']['conditions']
            if kind == 'extra_check': value['checks']['other'] = value['checks']['content']
            if kind == 'overall': value['verdict'] = 'supported'
            if kind == 'extra_field': value['checks']['content']['confidence'] = 1
            with self.assertRaises(ValueError): parsed(self.packet, value)

    def test_wrong_identity_status_basis_relation_and_reason_fail(self):
        for kind in ('packet', 'claim', 'status', 'basis', 'relation', 'reason', 'typed_status'):
            value = decision(self.packet)
            if kind == 'packet': value['packet_id'] = 'wrong'
            if kind == 'claim': value['claim_id'] = 'C002'
            if kind == 'status': value['checks']['content']['status'] = 'approved'
            if kind == 'basis': value['checks']['scope']['basis'] = 'guess'
            if kind == 'relation': value['checks']['scope']['relation'] = 'same'
            if kind == 'reason': value['checks']['content']['reason'] = ' '
            if kind == 'typed_status': value['checks']['content']['status'] = []
            with self.assertRaises(ValueError): parsed(self.packet, value)

    def test_foreign_fabricated_empty_duplicate_and_untyped_quotes_rejected(self):
        for kind in ('foreign', 'fabricated', 'empty', 'duplicate', 'untyped', 'extra', 'too_many'):
            value = decision(self.packet)
            citations = value['checks']['content']['citations']
            if kind == 'foreign': citations[0]['anchor_id'] = 'S2:E0001'
            if kind == 'fabricated': citations[0]['quote'] = 'All drugs fail.'
            if kind == 'empty': citations.clear()
            if kind == 'duplicate': citations.append(copy.deepcopy(citations[0]))
            if kind == 'untyped': citations[0]['quote'] = None
            if kind == 'extra': citations[0]['start'] = 0
            if kind == 'too_many': citations *= 4
            with self.assertRaises(ValueError): parsed(self.packet, value)

    def test_ambiguous_quote_offset_rejected(self):
        packet = plan(docs=[dict(chunk_text='The drug works. The drug works.')])['packets'][0]
        value = decision(packet)
        value['checks']['content']['citations'][0]['quote'] = 'The drug works.'
        with self.assertRaises(ValueError): parsed(packet, value)

    def test_contradiction_needs_evidence_missing_and_uncertain_may_have_none(self):
        for status, expected in (('missing', 'unsupported'), ('uncertain', 'uncertain')):
            value = decision(self.packet)
            value['checks']['content'].update(status=status, citations=[])
            self.assertEqual(parsed(self.packet, value)['verdict'], expected)
        value['checks']['content']['status'] = 'contradicted'
        with self.assertRaises(ValueError): parsed(self.packet, value)

    def test_contradiction_with_exact_quote_has_separate_code(self):
        value = decision(self.packet)
        value['checks']['content']['status'] = 'contradicted'
        result = parsed(self.packet, value)
        self.assertEqual((result['verdict'], result['reason_code']), ('unsupported', 'contradicted'))

    def test_duplicate_json_nonfinite_deep_trailing_large_and_wrong_types_rejected(self):
        raw_value = json.dumps(decision(self.packet))
        bad = [None, '[]', raw_value + '{}', raw_value[:-1] + ',"checks":{}}',
               '[' * 2000 + '0' + ']' * 2000, 'x' * 24001,
               raw_value.replace('"entailed"', 'NaN', 1)]
        for text in bad:
            with self.assertRaises(ValueError): v2.parse_decision(text, self.packet)


class ScopeTests(unittest.TestCase):
    def test_generalization_single_example_cannot_pass_despite_reported_entailment(self):
        packet = plan()['packets'][0]
        result = parsed(packet, decision(packet, basis='single_example'))
        self.assertEqual(result['verdict'], 'unsupported')
        self.assertEqual(result['reason_code'], 'not_in_evidence')
        self.assertIn('generalization_without_scope_evidence', result['guard_codes'])
        self.assertEqual(result['checks']['scope']['status'], 'entailed')
        self.assertEqual(result['effective_checks']['scope'], 'missing')

    def test_generalization_inference_and_no_basis_also_cannot_pass(self):
        packet = plan()['packets'][0]
        for basis in ('inference', 'none'):
            self.assertEqual(parsed(packet, decision(packet, basis=basis))['verdict'], 'unsupported')

    def test_broad_word_itself_is_not_a_rejection_rule(self):
        packet = plan('Most sampled drugs reach the tissue.',
                      [dict(chunk_text='In the study, most sampled drugs reached the tissue.')])['packets'][0]
        for basis in ('explicit_statement', 'aggregate_evidence'):
            self.assertEqual(parsed(packet, decision(packet, basis=basis))['verdict'], 'supported')

    def test_same_single_example_can_support_a_narrow_claim(self):
        packet = plan('Drug X does not penetrate the tissue.')['packets'][0]
        self.assertEqual(packet['risk_cues'], [])
        self.assertEqual(parsed(packet, decision(packet, basis='single_example'))['verdict'], 'supported')

    def test_negated_universal_is_not_a_broad_frequency_claim(self):
        for claim in ('Not all drugs penetrate the tissue.', 'Drugs do not always penetrate the tissue.',
                      '并非所有药物都能进入组织。', '药物并不总是能进入组织。'):
            packet = plan(claim)['packets'][0]
            self.assertTrue(any(c['kind'] == 'limited_quantifier' for c in packet['risk_cues']))
            self.assertFalse(any(c['kind'] == 'generalization' for c in packet['risk_cues']))
            self.assertEqual(parsed(packet, decision(packet, basis='single_example'))['verdict'], 'supported')

    def test_broader_relation_blocks_even_without_lexical_cue(self):
        packet = plan('Drugs do not penetrate the tissue.')['packets'][0]
        result = parsed(packet, decision(packet, relation='claim_broader'))
        self.assertEqual(result['verdict'], 'unsupported')
        self.assertIn('claim_scope_broader', result['guard_codes'])

    def test_unknown_alignment_abstains_instead_of_supporting(self):
        packet = plan('Drug X does not penetrate the tissue.')['packets'][0]
        result = parsed(packet, decision(packet, relation='unknown'))
        self.assertEqual(result['verdict'], 'uncertain')

    def test_missing_conditions_block_even_when_content_and_scope_pass(self):
        packet = plan()['packets'][0]
        value = decision(packet)
        value['checks']['conditions'].update(status='missing', reason='An essential experimental condition was omitted.', citations=[])
        self.assertEqual(parsed(packet, value)['verdict'], 'unsupported')

    def test_structural_guard_is_not_a_semantic_oracle(self):
        # Deliberately dishonest injected metadata remains structurally valid.
        # Do not report this parser's tests as detecting real-world entailment.
        packet = plan()['packets'][0]
        result = parsed(packet, decision(packet, basis='explicit_statement'))
        self.assertEqual(result['verdict'], 'supported')
        self.assertFalse(result['semantic_verified'])


class GateTests(unittest.TestCase):
    def test_supported_keeps_candidate_text_and_no_semantic_guarantee(self):
        value = plan('Drug X does not penetrate the tissue.')
        p = value['packets'][0]
        result = v2.gate_answer(QUESTION, DOCS, raw('Drug X does not penetrate the tissue.'),
                               {'C001': json.dumps(decision(p, basis='single_example'))}, evidence_mode='fixed_v1')
        self.assertTrue(result['release_allowed'])
        self.assertEqual(result['answer'], value['candidate_answer'])
        self.assertFalse(result['semantic_verified']); self.assertFalse(result['human_verified'])

    def test_scope_failure_blocks_candidate_without_rewrite(self):
        p = plan()['packets'][0]
        result = v2.gate_answer(QUESTION, DOCS, raw(), {'C001': json.dumps(decision(p, basis='single_example'))}, evidence_mode='fixed_v1')
        self.assertFalse(result['release_allowed'])
        self.assertEqual(result['status'], 'review_unsupported')
        self.assertNotIn('New drugs', result['answer'])

    def test_one_failed_claim_suppresses_whole_candidate(self):
        output = json.dumps(dict(status='answered', claims=[
            dict(text='Drug X does not penetrate the tissue.', evidence_ids=['S1:E0001']),
            dict(text='New drugs often do not penetrate the tissue.', evidence_ids=['S1:E0001'])]))
        packets = v2.prepare_review(QUESTION, DOCS, output, evidence_mode='fixed_v1')['packets']
        decisions = {p['base_packet']['claim_id']: json.dumps(decision(p, basis='single_example')) for p in packets}
        result = v2.gate_answer(QUESTION, DOCS, output, decisions, evidence_mode='fixed_v1')
        self.assertEqual(result['status'], 'review_unsupported')
        self.assertFalse(result['release_allowed'])
        self.assertNotIn('Drug X', result['answer'])
        self.assertEqual([r['verdict'] for r in result['reviews']], ['supported', 'unsupported'])

    def test_missing_invalid_extra_and_stale_reviews_fail_closed(self):
        for values, expected in (({}, 'review_incomplete'), ({'C001': '{}'}, 'review_invalid'),
                                 ({'C999': '{}'}, 'review_invalid'), ([], 'review_invalid')):
            result = v2.gate_answer(QUESTION, DOCS, raw(), values, evidence_mode='fixed_v1')
            self.assertEqual(result['status'], expected)
            self.assertFalse(result['release_allowed'])

    def test_empty_insufficient_and_invalid_inputs_stay_distinct(self):
        for docs, output, expected in (([], None, 'no_evidence'), (DOCS, '{}', 'invalid_claim_structure'),
                                      (DOCS, '{"status":"insufficient","claims":[]}', 'claim_bound_insufficient')):
            result = v2.gate_answer(QUESTION, docs, output, {}, evidence_mode='fixed_v1')
            self.assertEqual(result['status'], expected)
            self.assertFalse(result['release_allowed'])


if __name__ == '__main__':
    unittest.main()
