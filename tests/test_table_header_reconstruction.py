import copy
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from table_header_reconstruction import repair_header
from audit_table_decoder import parse_html_table


def fixture():
    # Two independent four-column groups, with one wrapped standalone header.
    raw = '<table><tr><td colspan="4"></td><td colspan="4"></td><td rowspan="2"></td></tr>'
    raw += '<tr>' + '<td></td>' * 8 + '</tr>'
    raw += ('<tr>' + '<td></td>' * 9 + '</tr>') * 4 + '</table>'
    xs = list(range(10, 191, 20)); ys = [10, 70, 90, 110, 130, 150]
    boxes = [[xs[c], ys[r], xs[c+1], ys[r+1]] for r in range(1,5) for c in range(9)]
    boxes.append([170, 10, 190, 70])
    boxes.extend([[10,10,90,70],[90,10,170,70]])
    image = np.full((160,200),255,dtype=np.uint8)
    for c,x in enumerate(xs):
        start = 10 if c in (0,4,8,9) else 30 if c in (2,6) else 50
        image[start:151,x] = 0
    ob = []; text = []
    for start in (0,4):
        ob.extend([[xs[start]+25,12,xs[start]+55,26],
                   [xs[start+2]+2,32,xs[start+4]-2,46],
                   [xs[start+1]+2,52,xs[start+2]-2,66],
                   [xs[start+3]+2,52,xs[start+4]-2,66]])
        text.extend(['Parent'+str(start),'Child'+str(start),'L','R'])
    ob.extend([[172,32,188,46],[172,52,188,66]]); text.extend(['wrap','ped'])
    for r in range(4):
        for c in range(9):
            ob.append([xs[c]+3,73+r*20,xs[c+1]-3,87+r*20]); text.append(str(r*9+c))
    capture = {'geometry_reprocessing': {'detected_boxes': boxes}, 'match': {'ocr_boxes': ob}, 'render': {'texts': text}}
    return raw,capture,image


class HeaderReconstructionTests(unittest.TestCase):
    def test_three_levels_spans_and_body_shift(self):
        raw,capture,image=fixture(); out=repair_header(raw,capture,image)
        self.assertTrue(out['gate']['passed'],out['gate'])
        s=parse_html_table(out['html'])[0]
        self.assertEqual(s['num_rows'],7)
        cells={(c['start_row_offset_idx'],c['start_col_offset_idx']):c for c in s['table_cells']}
        self.assertEqual(cells[(0,8)]['row_span'],3)
        self.assertEqual(cells[(0,8)]['text'],'wrap ped')
        self.assertEqual(cells[(1,2)]['col_span'],2)
        self.assertEqual(cells[(1,0)]['text'],'')
        self.assertEqual(cells[(1,1)]['text'],'')
        self.assertEqual(cells[(3,0)]['text'],'0')
        self.assertTrue(out['body_topology_preserved'])
        self.assertEqual(out['unassigned_ocr_ids'],[])
        self.assertEqual(out['header_paths'][3]['texts'],['Parent0','Child0','R'])

    def test_wrapped_standalone_does_not_add_levels(self):
        raw,capture,image=fixture()
        capture['match']['ocr_boxes'].insert(0,[172,15,188,26]); capture['render']['texts'].insert(0,'more')
        out=repair_header(raw,capture,image)
        self.assertTrue(out['gate']['passed'])
        self.assertEqual(out['header_rows_after'],3)

    def test_missing_rule_evidence_rejects_without_fabricating(self):
        raw,capture,image=fixture(); image[:]=255
        out=repair_header(raw,capture,image)
        self.assertFalse(out['gate']['passed'])
        self.assertIsNone(out['html'])

    def test_one_branch_cannot_decide_global_header_depth(self):
        raw,capture,image=fixture()
        for x in (110,130,150): image[:70,x]=255
        out=repair_header(raw,capture,image)
        self.assertFalse(out['gate']['passed'])

    def test_ruling_crossing_a_parent_label_invalidates_parent_span(self):
        raw,capture,image=fixture(); image[10:50,30]=0
        out=repair_header(raw,capture,image)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('ruling_conflicts_with_parent_span',out['gate']['reasons'])

    def test_changed_cells_have_original_structure_provenance(self):
        raw,capture,image=fixture(); out=repair_header(raw,capture,image)
        self.assertTrue(out['gate']['passed'])
        anchor=next(c for c in out['cells'] if c['row']==0 and c['col']==8)
        body=next(c for c in out['cells'] if c['row']==3 and c['col']==0)
        self.assertEqual(anchor['origin']['operation'],'extend_rowspan')
        self.assertEqual(body['origin']['source_coordinates'],[2,0,1,1])
        self.assertTrue(anchor['is_header']); self.assertFalse(body['is_header'])

    def test_ocr_contradicting_parent_boundary_rejected(self):
        raw,capture,image=fixture()
        capture['match']['ocr_boxes'][1]=[82,32,98,46]
        out=repair_header(raw,capture,image)
        self.assertFalse(out['gate']['passed'])

    def test_regular_success_is_unchanged_and_does_not_require_rulings(self):
        raw='<table><tr><td></td><td></td></tr><tr><td></td><td></td></tr></table>'
        c={'geometry_reprocessing':{'detected_boxes':[[0,0,20,20],[20,0,40,20],[0,20,20,40],[20,20,40,40]]},
           'match':{'ocr_boxes':[[2,2,18,18]]},'render':{'texts':['x']}}
        from table_grid_binding import bind_grid
        old=bind_grid(raw,c,[40,40]); out=repair_header(raw,c,np.full((40,40),255,dtype=np.uint8))
        self.assertEqual(out['html'],old['html'])
        self.assertEqual(out['status'],'unchanged_v10_success')

    def test_source_immutability_and_text_escaping(self):
        raw,capture,image=fixture(); capture['render']['texts'][0]='<script>&'
        old=copy.deepcopy(capture); pixels=image.copy()
        out=repair_header(raw,capture,image)
        self.assertTrue(out['gate']['passed'])
        self.assertEqual(capture,old); np.testing.assert_array_equal(image,pixels)
        self.assertNotIn('<script>',out['html']); self.assertIn('&lt;script&gt;',out['html'])

    def test_invalid_image_and_html_rejected(self):
        raw,capture,image=fixture()
        for bad in (image.astype(float),image[:,:,None],np.zeros((0,10),dtype=np.uint8)):
            with self.subTest(shape=bad.shape),self.assertRaises(ValueError): repair_header(raw,capture,bad)
        with self.assertRaises(ValueError): repair_header('<table><td>',capture,image)


if __name__=='__main__': unittest.main()
