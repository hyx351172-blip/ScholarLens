import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from table_candidate_safety import guard_candidate


def trace(lines=4, columns=3):
    cells = []
    for c in range(columns):
        ocr = [{'ocr_id': c * lines + i, 'text': f'value {i}',
                'bbox': [c*100+5, 10+i*25, c*100+70, 25+i*25]}
               for i in range(lines)]
        cells.append({'cell_id': c, 'row': 1, 'col': c, 'row_span': 1,
                      'col_span': 1, 'bbox': [c*100,0,c*100+100,120],
                      'ocr': ocr, 'ocr_ids': [x['ocr_id'] for x in ocr]})
    return {'gate': {'passed': True, 'reasons': []}, 'cells': cells, 'html': '<table></table>'}


class CandidateSafetyTests(unittest.TestCase):
    def test_aligned_multiple_records_fail_closed(self):
        t = trace(); old = copy.deepcopy(t); out = guard_candidate(t)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('aligned_multiline_row_ambiguity', out['gate']['reasons'])
        self.assertEqual(t, old)
        self.assertEqual(out['html'], t['html'])
        self.assertEqual(out['cells'], t['cells'])
        self.assertEqual(out['row_safety']['suspicions'][0]['row'], 1)

    def test_two_wrapped_lines_are_not_records(self):
        self.assertTrue(guard_candidate(trace(2))['gate']['passed'])

    def test_only_one_wrapped_column_is_not_rejected(self):
        self.assertTrue(guard_candidate(trace(4,1))['gate']['passed'])

    def test_explicit_header_and_spans_are_not_split(self):
        for flag, val in [('is_header', True), ('row_span', 2), ('col_span', 2)]:
            t = trace()
            for c in t['cells']: c[flag] = val
            self.assertTrue(guard_candidate(t)['gate']['passed'])

    def test_offset_lines_are_not_cross_column_records(self):
        t = trace(3,2)
        for a in t['cells'][1]['ocr']:
            a['bbox'][1] += 12; a['bbox'][3] += 12
        self.assertTrue(guard_candidate(t)['gate']['passed'])

    def test_rejected_candidate_never_promoted(self):
        t = {'gate': {'passed': False, 'reasons': ['existing_failure']}}
        self.assertEqual(guard_candidate(t)['gate'], t['gate'])

    def test_repeated_ocr_id_fails_closed(self):
        t = trace(); t['cells'][1]['ocr'][0]['ocr_id'] = 0
        out = guard_candidate(t)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('invalid_row_provenance', out['gate']['reasons'])

    def test_split_words_on_same_line_not_multiple_rows(self):
        t=trace(3,2)
        for c in t['cells']:
            for a in c['ocr']: a['bbox'][1:4:2] = [10,25]
        self.assertTrue(guard_candidate(t)['gate']['passed'])

    def test_bad_geometry_fails_closed(self):
        t=trace(); t['cells'][0]['ocr'][0]['bbox'][0]=float('nan')
        self.assertFalse(guard_candidate(t)['gate']['passed'])

if __name__ == '__main__': unittest.main()
