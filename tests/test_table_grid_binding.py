import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from table_grid_binding import bind_grid
from table_ocr_binding import structure_signature


def fixture():
    # Deliberately nonuniform columns. Middle cell in the second row is empty
    # and has NO detection; ordinal matching would shift 'D' into it.
    boxes = [[0, 0, 20, 20], [20, 0, 60, 20], [60, 0, 100, 20],
             [0, 20, 20, 40], [60, 20, 100, 40]]
    return ('<table><tr><td></td><td></td><td></td></tr>'
            '<tr><td></td><td></td><td></td></tr></table>',
            {'geometry_reprocessing': {'detected_boxes': boxes},
             'match': {'ocr_boxes': [[2, 2, 18, 18], [62, 22, 98, 38]]},
             'render': {'texts': ['A', 'D']}}, [100, 40])


class GridBindingTests(unittest.TestCase):
    def test_empty_slot_does_not_shift_following_text(self):
        raw, capture, size = fixture()
        out = bind_grid(raw, capture, size)
        self.assertTrue(out['gate']['passed'])
        self.assertEqual(out['cells'][4]['text'], '')
        self.assertEqual(out['cells'][5]['text'], 'D')
        self.assertEqual(out['cells'][5]['ocr_ids'], [1])
        self.assertEqual(out['axes']['x']['boundaries'], [0, 20, 60, 100])
        self.assertEqual(out['empty_cell_ids'], [1, 2, 3, 4])

    def test_input_order_and_values_cannot_change_axes(self):
        raw, capture, size = fixture(); old = copy.deepcopy(capture)
        a = bind_grid(raw, capture, size)
        self.assertEqual(capture, old)
        capture['geometry_reprocessing']['detected_boxes'].reverse()
        capture['render']['texts'] = ['other', '12']
        b = bind_grid(raw, capture, size)
        self.assertEqual(a['axes'], b['axes'])
        self.assertEqual(a['cells'][5]['ocr_ids'], b['cells'][5]['ocr_ids'])

    def test_missing_whole_column_is_rejected_not_interpolated(self):
        raw, capture, size = fixture()
        capture['geometry_reprocessing']['detected_boxes'] = [[0, 0, 60, 20], [60, 0, 100, 20], [0, 20, 60, 40], [60, 20, 100, 40]]
        out = bind_grid(raw, capture, size)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('x_axis_count_mismatch', out['gate']['reasons'])
        self.assertIsNone(out['html'])

    def test_missing_header_row_is_not_compressed_into_body(self):
        raw, capture, size = fixture()
        raw = raw.replace('</table>', '<tr><td></td><td></td><td></td></tr></table>')
        out = bind_grid(raw, capture, size)
        self.assertIn('y_axis_count_mismatch', out['gate']['reasons'])

    def test_spans_are_preserved_and_get_unioned_geometry(self):
        raw = '<table><tr><td rowspan="2"></td><td colspan="2"></td></tr><tr><td></td><td></td></tr><tr><td></td><td></td><td></td></tr></table>'
        boxes = [[0, 0, 20, 40], [20, 0, 60, 20], [20, 20, 40, 40], [40, 20, 60, 40],
                 [0, 40, 20, 60], [20, 40, 40, 60], [40, 40, 60, 60]]
        capture = {'geometry_reprocessing': {'detected_boxes': boxes}, 'match': {'ocr_boxes': [[22, 2, 58, 18]]}, 'render': {'texts': ['heading']}}
        out = bind_grid(raw, capture, [60, 60])
        self.assertTrue(out['gate']['passed'])
        self.assertEqual(out['cells'][1]['bbox'], [20, 0, 60, 20])
        self.assertEqual(structure_signature(raw), structure_signature(out['html']))

    def test_ambiguous_ocr_is_never_duplicated(self):
        raw, capture, size = fixture()
        capture['match']['ocr_boxes'][1] = [50, 22, 70, 38]
        out = bind_grid(raw, capture, size)
        self.assertFalse(out['gate']['passed'])
        self.assertEqual(out['unassigned_ocr_ids'], [1])
        self.assertEqual(out['assignments'][1]['reason'], 'ambiguous_or_low_overlap')
        self.assertNotIn(1, [i for c in out['cells'] for i in c['ocr_ids']])

    def test_text_order_escaping_and_no_value_correction(self):
        raw, capture, size = fixture()
        capture['match']['ocr_boxes'] = [[62, 30, 98, 38], [62, 22, 98, 28]]
        capture['render']['texts'] = ['<script>&', 'O0']
        out = bind_grid(raw, capture, size)
        self.assertEqual(out['cells'][5]['text'], 'O0 <script>&')
        self.assertNotIn('<script>', out['html'])
        self.assertIn('&lt;script&gt;', out['html'])

    def test_outside_table_ocr_is_recorded_not_discarded(self):
        raw, capture, size = fixture(); size = [120, 40]
        capture['match']['ocr_boxes'][1] = [101, 22, 119, 38]
        out = bind_grid(raw, capture, size)
        self.assertEqual(out['unassigned_ocr_ids'], [1])
        self.assertFalse(out['gate']['passed'])

    def test_bad_rectangles_and_lengths_rejected(self):
        for box in ([1, 0, 1, 4], [0, 0, float('nan'), 4], [-1, 0, 4, 4], [0, 0, 200, 4], [True, 0, 4, 4]):
            raw, capture, size = fixture(); capture['match']['ocr_boxes'][0] = box
            with self.subTest(box=box), self.assertRaises(ValueError): bind_grid(raw, capture, size)
        raw, capture, size = fixture(); capture['render']['texts'].pop()
        with self.assertRaises(ValueError): bind_grid(raw, capture, size)

    def test_duplicate_boxes_do_not_inflate_support(self):
        raw, capture, size = fixture()
        capture['geometry_reprocessing']['detected_boxes'] = [capture['geometry_reprocessing']['detected_boxes'][0]] * 50
        out = bind_grid(raw, capture, size)
        self.assertFalse(out['gate']['passed'])

    def test_structure_must_be_empty_strict_and_safe(self):
        raw, capture, size = fixture()
        for bad in (raw.replace('<td></td>', '<td>gold</td>', 1), '<table><tr><td>'):
            with self.subTest(bad=bad), self.assertRaises(ValueError): bind_grid(bad, capture, size)

    def test_uncertain_clustering_is_rejected_even_when_default_count_fits(self):
        boxes = [[x0, y, x1, y + 20] for y in (0, 20, 40) for x0, x1 in ((0, 20), (20, 55), (60, 100))]
        raw = '<table>' + '<tr><td></td><td></td><td></td></tr>' * 3 + '</table>'
        capture = {'geometry_reprocessing': {'detected_boxes': boxes},
                   'match': {'ocr_boxes': [[2, 2, 18, 18]]}, 'render': {'texts': ['A']}}
        out = bind_grid(raw, capture, [100, 60])
        self.assertTrue(out['axes']['x']['count_matches'])
        self.assertIn('x_axis_unstable', out['gate']['reasons'])
        self.assertIsNone(out['html'])

    def test_no_ocr_cannot_pass_by_vacuous_assignment(self):
        raw, capture, size = fixture()
        capture['match']['ocr_boxes'] = []; capture['render']['texts'] = []
        out = bind_grid(raw, capture, size)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('no_ocr_evidence', out['gate']['reasons'])

    def test_excessive_payload_fails_before_mapping(self):
        raw, capture, size = fixture()
        capture['geometry_reprocessing']['detected_boxes'] *= 1001
        with self.assertRaises(ValueError): bind_grid(raw, capture, size)


if __name__ == '__main__': unittest.main()
