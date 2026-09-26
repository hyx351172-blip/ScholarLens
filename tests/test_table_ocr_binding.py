import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from table_ocr_binding import audit_binding, aligned_metrics, structure_signature, binding_gate, label_anchored_metrics


def capture():
    return {'match': {'cell_boxes': [[0, 0, 10, 10], [10, 0, 20, 10]],
                      'ocr_boxes': [[1, 1, 9, 9], [11, 1, 19, 9]],
                      'group_starts': [0, 2], 'groups': [{'0': [0], '1': [1]}]},
            'render': {'groups': [{'0': [0], '1': [1]}], 'texts': ['1 V', '2 V'],
                       'breaks': [0, 2]}}


STRUCTURE = '<table><tr><td></td><td></td></tr></table>'
FILLED = '<table><tr><td>1 V</td><td>2 V</td></tr></table>'


class BindingTests(unittest.TestCase):
    def test_trace_preserves_logical_and_physical_provenance(self):
        c = capture(); old = copy.deepcopy(c)
        result = audit_binding(STRUCTURE, FILLED, c)
        self.assertEqual(result['cells'][1]['col'], 1)
        self.assertEqual(result['cells'][1]['ocr_ids'], [1])
        self.assertEqual(result['cells'][1]['geometry_id'], 1)
        self.assertEqual(result['cells'][1]['ocr'][0]['text'], '2 V')
        self.assertEqual(result['unassigned_ocr_ids'], [])
        self.assertEqual(c, old)

    def test_duplicates_and_lost_ocr_are_visible(self):
        c = capture()
        c['render']['groups'] = c['match']['groups'] = [{'0': [0], '1': [0]}]
        got = audit_binding(STRUCTURE, '<table><tr><td>1 V</td><td>1 V</td></tr></table>', c)
        self.assertEqual(got['duplicated_ocr_ids'], [0])
        self.assertEqual(got['unassigned_ocr_ids'], [1])

    def test_out_of_range_and_negative_indices_fail(self):
        for index in (-1, 2, 1.5, True):
            c = capture(); c['render']['groups'][0]['0'] = [index]
            with self.subTest(index=index), self.assertRaises(ValueError): audit_binding(STRUCTURE, FILLED, c)

    def test_structure_change_is_not_silently_accepted(self):
        with self.assertRaises(ValueError): audit_binding(STRUCTURE, '<table><tr><td>both</td></tr></table>', capture())

    def test_empty_list_renderer_continue_hazard_rejected(self):
        c = capture(); c['render']['groups'][0]['0'] = []
        with self.assertRaises(ValueError): audit_binding(STRUCTURE, FILLED, c)

    def test_missing_mapping_and_low_overlap_are_audited(self):
        c = capture(); c['render']['groups'][0].pop('1'); c['match']['ocr_boxes'][0] = [100, 100, 110, 110]
        out = audit_binding(STRUCTURE, '<table><tr><td>1 V</td><td></td></tr></table>', c)
        self.assertEqual(out['unassigned_ocr_ids'], [1])
        self.assertEqual(out['low_overlap_assignments'], [{'cell_id': 0, 'ocr_id': 0, 'coverage': 0.0}])

    def test_span_signature_and_escaping(self):
        raw = '<table><tr><th colspan="2">&lt;script&gt;</th></tr><tr><td>1</td><td>2</td></tr></table>'
        self.assertEqual(structure_signature(raw)[0], (0, 0, 1, 2))
        with self.assertRaises(ValueError): structure_signature('<table><tr><td><script>x</script></td></tr></table>')

    def test_unused_terminal_boundary_is_flagged_not_used_to_shift_text(self):
        c = capture()
        c['match']['groups'] = c['render']['groups'] = [{'0': [0]}, {'0': [1]}]
        c['match']['group_starts'] = [0, 1, 2]
        c['render']['breaks'] = [0, 1, 0]
        got = audit_binding(STRUCTURE, FILLED, c)
        self.assertTrue(got['terminal_boundary_anomaly'])
        self.assertEqual(got['cells'][1]['ocr_ids'], [1])
        self.assertFalse(binding_gate(got)['passed'])

    def test_binding_gate_rejects_uncertainty_not_just_bad_html(self):
        got = audit_binding(STRUCTURE, FILLED, capture())
        self.assertTrue(binding_gate(got)['passed'])
        got['geometry_count_matches'] = False
        self.assertFalse(binding_gate(got)['passed'])

    def test_invalid_geometry_fails(self):
        c = capture(); c['match']['cell_boxes'][0] = [0, 0, float('nan'), 1]
        with self.assertRaises(ValueError): audit_binding(STRUCTURE, FILLED, c)


class CoordinateMetricsTests(unittest.TestCase):
    def test_swapped_numbers_fail_even_when_bag_matches(self):
        pred = '<table><tr><td>2 V</td><td>1 V</td></tr></table>'
        got = aligned_metrics(pred, FILLED)
        self.assertEqual(got['numeric_cells']['total'], 2)
        self.assertEqual(got['numeric_cells']['exact'], 0)
        self.assertEqual(got['unit_bearing_cells']['exact'], 0)

    def test_exact_and_whitespace_normalization(self):
        got = aligned_metrics(FILLED.replace('1 V', ' 1\nV '), FILLED)
        self.assertEqual(got['nonempty_gold_cells']['exact'], 2)
        self.assertEqual(got['numeric_cells']['accuracy'], 1.0)

    def test_empty_cells_do_not_inflate_nonempty_score(self):
        got = aligned_metrics(STRUCTURE, FILLED)
        self.assertEqual(got['nonempty_gold_cells']['total'], 2)
        self.assertEqual(got['nonempty_gold_cells']['exact'], 0)

    def test_missing_span_is_in_denominator(self):
        gold = '<table><tr><th colspan="2">12 V</th></tr></table>'
        got = aligned_metrics(FILLED, gold)
        self.assertEqual(got['matched_span_cells'], 0)
        self.assertEqual(got['numeric_cells']['total'], 1)
        self.assertEqual(got['explicit_header_cells']['exact'], 0)

    def test_wrong_unit_not_hidden_by_correct_number(self):
        got = aligned_metrics(FILLED.replace('1 V', '1 A'), FILLED)
        self.assertEqual(got['numeric_cells']['exact'], 2)
        self.assertEqual(got['unit_bearing_cells']['exact'], 1)

    def test_absent_subset_is_unavailable_not_perfect(self):
        got = aligned_metrics(STRUCTURE, STRUCTURE)
        self.assertIsNone(got['numeric_cells']['accuracy'])
        self.assertIsNone(got['explicit_header_cells']['accuracy'])

    def test_label_anchor_exposes_header_shift_without_hiding_column_swap(self):
        gold = '<table><tr><td>Method</td><td>Score</td></tr><tr><td>A</td><td>12</td></tr></table>'
        pred = '<table><tr><td>A</td><td>12</td></tr></table>'
        self.assertEqual(aligned_metrics(pred, gold)['numeric_cells']['exact'], 0)
        self.assertEqual(label_anchored_metrics(pred, gold)['body_numeric_cells']['exact'], 1)

    def test_ambiguous_labels_are_not_guessed(self):
        raw = '<table><tr><td>A</td><td>1</td></tr><tr><td>A</td><td>2</td></tr></table>'
        got = label_anchored_metrics(raw, raw)
        self.assertEqual(got['matched_label_rows'], 0)
        self.assertEqual(got['ambiguous_gold_labels'], ['A'])
        self.assertIsNone(got['body_numeric_cells']['accuracy'])

    def test_missing_label_rows_stay_in_numeric_denominator(self):
        gold = '<table><tr><td>A</td><td>1</td></tr><tr><td>B</td><td>2</td></tr></table>'
        pred = '<table><tr><td>A</td><td>1</td></tr></table>'
        got = label_anchored_metrics(pred, gold)
        self.assertEqual(got['body_numeric_cells']['total'], 2)
        self.assertEqual(got['body_numeric_cells']['exact'], 1)


if __name__ == '__main__': unittest.main()
