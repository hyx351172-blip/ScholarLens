import copy
import hashlib
import json
from pathlib import Path
import unittest

from backend.chat import quote_alignment as match
from backend.chat import qualified_claim_support as v2
from backend.chat import qualified_claim_support_v21 as v21
from tests.test_qualified_claim_support import decision, plan

ROOT = Path(__file__).resolve().parents[1]


class AlignmentTests(unittest.TestCase):
    def test_exact_quote_has_source_offsets(self):
        r = match.align_quote('alpha beta', 'Prefix: alpha beta. End.', source_start=200)
        self.assertEqual((r['source_start'], r['source_end']), (208, 218))
        self.assertEqual(r['match_mode'], 'exact')
        self.assertEqual(r['quote'], r['model_quote'])

    def test_whitespace_only_maps_back_to_original_span(self):
        source = '前文😀:alpha\r\n  beta\t gamma!后文'
        r = match.align_quote('alpha beta\ngamma!', source, source_start=91)
        self.assertEqual(r['quote'], 'alpha\r\n  beta\t gamma!')
        self.assertEqual(r['model_quote'], 'alpha beta\ngamma!')
        self.assertEqual(r['match_mode'], 'whitespace_only')
        self.assertEqual(source[r['source_start'] - 91:r['source_end'] - 91], r['quote'])
        self.assertEqual(r['source_start'], 95)

    def test_edge_whitespace_spans_are_preserved_not_trimmed(self):
        r = match.align_quote(' alpha ', 'X\n\talpha\r\nY')
        self.assertEqual(r['quote'], '\n\talpha\r\n')
        self.assertEqual((r['source_start'], r['source_end']), (1, 10))

    def test_exact_match_does_not_bypass_normalized_ambiguity(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous_quote'):
            match.align_quote('alpha beta', 'alpha beta; alpha\nbeta')

    def test_overlapping_occurrences_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous_quote'):
            match.align_quote('aaa', 'aaaa')

    def test_no_word_number_operator_punctuation_or_case_repair(self):
        source = 'Drug X did not improve score from 12.5 to 13.5; a/b >= 2.'
        for quote in ('did improve score', '12.6 to 13.5', 'a/b > 2', 'a /b >= 2',
                      'drug X', 'Drug X did not improve score from 12.5 to 13.5, a/b >= 2.'):
            with self.subTest(quote=quote), self.assertRaises(ValueError): match.align_quote(quote, source)

    def test_no_dehyphenation_or_separator_insertion_deletion(self):
        for quote, source in (('self regulation', 'self-\nregulation'), ('alpha beta', 'alphabeta'),
                              ('alphabeta', 'alpha\nbeta'), ('alpha beta', 'alpha NEW beta')):
            with self.subTest(quote=quote), self.assertRaises(ValueError): match.align_quote(quote, source)

    def test_no_unicode_or_unlisted_whitespace_normalization(self):
        for source in ('alpha\u00a0beta', 'alpha\u2009beta', 'alpha\vbeta', 'alpha\fbeta',
                       'alpha\u200bbeta', 'alpha\u2028beta'):
            with self.subTest(source=source), self.assertRaises(ValueError): match.align_quote('alpha beta', source)
        with self.assertRaises(ValueError): match.align_quote('fi', '\ufb01')
        with self.assertRaises(ValueError): match.align_quote('é', 'e\u0301')

    def test_invalid_and_bounded_inputs(self):
        for quote, source, offset in ((None, 'x', 0), ('', 'x', 0), (' \n', 'x', 0),
                                      ('x', None, 0), ('x', 'x', -1), ('x', 'x', True),
                                      ('a' * 1201, 'a' * 1201, 0), ('x', 'x' * 64001, 0)):
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                match.align_quote(quote, source, source_start=offset)
        with self.assertRaises(ValueError): match.align_quote('a b', 'a' + ' ' * 1200 + 'b')

    def test_many_whitespace_combinations_map_without_changing_content(self):
        variants = [' ', '  ', '\n', '\r\n', '\t', ' \n\t']
        for left in variants:
            for right in variants:
                source = f'prefix A{left}B{right}C suffix'
                r = match.align_quote('A B C', source, source_start=7)
                self.assertEqual(r['quote'], f'A{left}B{right}C')
                self.assertEqual(source[r['source_start'] - 7:r['source_end'] - 7], r['quote'])


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.packet = plan(docs=[dict(filename='sample.txt', chunk_text='Drug X works.\nIt reached the tissue.')])['packets'][0]
        self.value = decision(self.packet)

    def parse(self, value=None, packet=None):
        return v21.parse_decision(json.dumps(value or self.value), packet or self.packet)

    def test_exact_response_semantics_unchanged_with_provenance(self):
        before = v2.parse_decision(json.dumps(self.value), self.packet)
        after = self.parse()
        for field in ('packet_id', 'claim_id', 'verdict', 'reason_code', 'effective_checks', 'guard_codes'):
            self.assertEqual(before[field], after[field])
        self.assertEqual(after['version'], v21.VERSION)
        self.assertEqual(after['input_contract_version'], v2.VERSION)
        self.assertFalse(after['semantic_verified']); self.assertFalse(after['human_verified'])

    def test_newline_alignment_retains_model_quote_and_raw_hash(self):
        self.value['checks']['content']['citations'][0]['quote'] = 'Drug X works. It reached the tissue.'
        raw = json.dumps(self.value); saved = copy.deepcopy(self.packet)
        result = v21.parse_decision(raw, self.packet)
        cite = result['checks']['content']['citations'][0]
        self.assertEqual(cite['quote'], 'Drug X works.\nIt reached the tissue.')
        self.assertEqual(cite['model_quote'], 'Drug X works. It reached the tissue.')
        self.assertEqual(cite['match_mode'], 'whitespace_only')
        self.assertEqual(result['raw_response_sha256'], hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(saved, self.packet)
        with self.assertRaises(ValueError): v2.parse_decision(raw, self.packet)

    def test_duplicate_resolved_span_rejected_even_different_quote_whitespace(self):
        self.value['checks']['content']['citations'].append(dict(anchor_id='S1:E0001', quote='Drug X works. It reached the tissue.'))
        with self.assertRaises(ValueError): self.parse()

    def test_cross_anchor_and_foreign_sources_rejected(self):
        p = plan(docs=[dict(chunk_text='Alpha unique.'), dict(chunk_text='Beta unique.')])['packets'][0]
        value = decision(p)
        for anchor, quote in (('S1:E0001', 'Alpha unique. Beta unique.'), ('S2:E0001', 'Beta unique.')):
            value['checks']['content']['citations'][0] = dict(anchor_id=anchor, quote=quote)
            with self.assertRaises(ValueError): self.parse(value, p)

    def test_unknown_fields_ids_and_metadata_still_rejected(self):
        for kind in ('packet', 'claim', 'missing_check', 'extra_check', 'overall', 'citation_field', 'basis', 'status'):
            value = copy.deepcopy(self.value)
            if kind == 'packet': value['packet_id'] = 'wrong'
            if kind == 'claim': value['claim_id'] = 'C002'
            if kind == 'missing_check': del value['checks']['scope']
            if kind == 'extra_check': value['checks']['extra'] = {}
            if kind == 'overall': value['verdict'] = 'supported'
            if kind == 'citation_field': value['checks']['content']['citations'][0]['start'] = 0
            if kind == 'basis': value['checks']['scope']['basis'] = 'guess'
            if kind == 'status': value['checks']['content']['status'] = []
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.parse(value)

    def test_all_strict_json_bounds_preserved(self):
        raw = json.dumps(self.value)
        for bad in (None, '[]', raw + '{}', raw[:-1] + ',"checks":{}}',
                    '[' * 2000 + '0' + ']' * 2000, ' ' * 24001 + raw,
                    raw.replace('"entailed"', 'NaN', 1)):
            with self.assertRaises(ValueError): v21.parse_decision(bad, self.packet)

    def test_required_citations_and_reason_bounds_preserved(self):
        for kind in ('empty', 'many', 'untyped', 'long_reason', 'long_quote'):
            value = copy.deepcopy(self.value); c = value['checks']['content']
            if kind == 'empty': c['citations'] = []
            if kind == 'many': c['citations'] *= 4
            if kind == 'untyped': c['citations'] = None
            if kind == 'long_reason': c['reason'] = 'r' * 601
            if kind == 'long_quote': c['citations'][0]['quote'] = 'q' * 1201
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.parse(value)

    def test_scope_and_conditions_are_not_repaired_by_quote_alignment(self):
        for field, val, verdict in (('basis', 'single_example', 'unsupported'), ('relation', 'unknown', 'uncertain')):
            value = copy.deepcopy(self.value); value['checks']['scope'][field] = val
            self.assertEqual(self.parse(value)['verdict'], verdict)
        for state, verdict, code in (('missing', 'unsupported', 'not_in_evidence'),
                                     ('uncertain', 'uncertain', 'ambiguous_evidence'),
                                     ('contradicted', 'unsupported', 'contradicted')):
            value = copy.deepcopy(self.value); value['checks']['conditions']['status'] = state
            result = self.parse(value)
            self.assertEqual((result['verdict'], result['reason_code']), (verdict, code))

    def test_all_scope_state_basis_relation_combinations_preserve_v2_decisions(self):
        for state in sorted(v2.STATES):
            for basis in sorted(v2.BASES):
                for relation in sorted(v2.RELATIONS):
                    value = copy.deepcopy(self.value)
                    value['checks']['scope'].update(status=state, basis=basis, relation=relation)
                    before = v2.parse_decision(json.dumps(value), self.packet)
                    after = self.parse(value)
                    for field in ('verdict', 'reason_code', 'effective_checks', 'guard_codes'):
                        self.assertEqual(after[field], before[field], (state, basis, relation, field))

    def test_tampered_packet_cannot_be_laundered_by_alignment(self):
        packet = copy.deepcopy(self.packet)
        packet['base_packet']['selected_anchors'][0]['text'] += ' changed'
        with self.assertRaises(ValueError): self.parse(packet=packet)

    def test_real_failure_replays_without_changing_original(self):
        base = ROOT / 'output/qualified-claim-support-live-v2'
        entry = json.loads((base / 'entries.json').read_text(encoding='utf-8'))[0]
        file = base / f"result-{entry['key']}.json"
        before = file.read_bytes(); row = json.loads(before)
        with self.assertRaisesRegex(ValueError, 'missing_or_ambiguous_quote'):
            v2.parse_decision(row['raw_content'], entry['packet'])
        result = v21.parse_decision(row['raw_content'], entry['packet'])
        self.assertEqual(result['verdict'], 'unsupported')
        self.assertEqual(result['reason_code'], 'not_in_evidence')
        citations = [c for check in result['checks'].values() for c in check['citations']]
        self.assertEqual(sum(c['match_mode'] == 'whitespace_only' for c in citations), 1)
        self.assertEqual(sum(c['match_mode'] == 'exact' for c in citations), 5)
        anchors = {a['anchor_id']: a for a in entry['packet']['base_packet']['selected_anchors']}
        for citation in citations:
            anchor = anchors[citation['anchor_id']]
            self.assertEqual(anchor['text'][citation['source_start'] - anchor['start']:
                                             citation['source_end'] - anchor['start']], citation['quote'])
        self.assertEqual(file.read_bytes(), before)
        self.assertEqual(row['status'], 'error')


if __name__ == '__main__':
    unittest.main()
