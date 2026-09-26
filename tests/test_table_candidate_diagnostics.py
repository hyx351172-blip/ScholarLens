import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from table_candidate_diagnostics import normalize_wrapper, diagnose_candidate, axis_diagnosis
from audit_table_decoder import ROOT,read,parse_html_table


class CandidateDiagnosticsTests(unittest.TestCase):
    def test_valid_unchanged_including_legitimate_tbody(self):
        for raw in ('<table><tr><td>x</td></tr></table>',
                    '<table><tbody><tr><td>A &amp; B</td></tr></tbody></table>'):
            out=normalize_wrapper(raw);self.assertEqual(out['status'],'unchanged')
            self.assertEqual(out['html'],raw);self.assertEqual(out['edits'],[])

    def test_only_orphan_wrapper_removed_preserving_bytes(self):
        raw='<html><body><table><tr><td rowspan="1">A &amp; B</td></tr>\n</TBODY> \n</table></body></html>'
        out=normalize_wrapper(raw)
        self.assertEqual(out['status'],'repaired');self.assertEqual(out['html'],raw.replace('</TBODY>',''))
        edit=out['edits'][0];self.assertEqual(raw[edit['start']:edit['end']],'</TBODY>')
        self.assertEqual(parse_html_table(out['html'])[0]['table_cells'][0]['text'],'A & B')
        self.assertEqual(normalize_wrapper(out['html'])['status'],'unchanged')

    def test_refuses_other_malformed_or_unsafe_inputs(self):
        cases=[
            '<table><tr><td>x</tr></tbody></table>',
            '<table><tr><td>x</td></tr></tbody></tbody></table>',
            '<table><thead><tr><td>x</td></tr></thead></tbody></table>',
            '<table><tr><td>x</td></tr></tbody><tr><td>y</td></tr></table>',
            '<table><tr><td onclick="evil()">x</td></tr></tbody></table>',
            '<table><tr><td><script>x</script></td></tr></tbody></table>',
            '<table><tr><td colspan="2">x</td></tr><tr><td>y</td></tr></tbody></table>',
            '',None,'x'*1_000_001]
        for raw in cases:
            with self.subTest(raw=str(raw)[:60]):
                out=normalize_wrapper(raw);self.assertEqual(out['status'],'rejected');self.assertIsNone(out['html'])

    def test_real_wrapper_fix_does_not_bypass_five_cross_column_ocr(self):
        from PIL import Image
        root=ROOT/'output/benchmarks/omnidocbench-table-records-validation-v15'
        raw=(root/'paddle/case-10/structure.html').read_text(encoding='utf-8')
        cap=read(root/'paddle/case-10/binding-capture.json');old=copy.deepcopy(cap)
        with Image.open(root/'prepared/case-10.png') as img:size=list(img.size)
        with self.assertRaises(ValueError):parse_html_table(raw)
        out=diagnose_candidate(raw,cap,size,detector_capacity=300)
        self.assertEqual(out['normalization']['status'],'repaired')
        self.assertEqual(out['structure_shape'],[5,9]);self.assertFalse(out['grid']['gate']['passed'])
        self.assertEqual(out['grid']['gate']['reasons'],['unassigned_or_ambiguous_ocr'])
        self.assertEqual([a['ocr_id'] for a in out['ambiguous_ocr']],[72,96,103,118,129])
        self.assertTrue(all(a['crossed_x_boundaries'] for a in out['ambiguous_ocr']))
        self.assertEqual(cap,old)

    def test_axis_labels_do_not_change_axis_or_equate_deficit_with_missing_truth(self):
        axis={'boundaries':[0,10,20],'expected_boundaries':4,'stable':True,'all_clusters':[],
              'selected_edges':[],'stability_boundaries':[[0,10,20]]}
        old=copy.deepcopy(axis);a=axis_diagnosis(axis)
        self.assertEqual(a['relation'],'fewer_detected_boundaries');self.assertEqual(a['difference'],-1)
        self.assertEqual(axis,old)
        axis['expected_boundaries']=2;self.assertEqual(axis_diagnosis(axis)['relation'],'more_detected_boundaries')
        axis['expected_boundaries']=3;self.assertEqual(axis_diagnosis(axis)['relation'],'equal_counts')

    def test_input_bound_and_no_hidden_geometry_repair(self):
        out=diagnose_candidate('<table><tr><td></td></tr></table>',{},[100,100])
        self.assertEqual(out['status'],'invalid_capture');self.assertIsNone(out['grid'])

    def test_token_like_attribute_content_is_not_a_wrapper(self):
        raw='<table><tr><td style="x:</tbody>">value</td></tr></tbody></table>'
        out=normalize_wrapper(raw)
        self.assertEqual(out['status'],'repaired')
        self.assertIn('style="x:</tbody>"',out['html'])
        self.assertEqual(out['edits'][0]['start'],raw.rindex('</tbody>'))

    def test_old_twenty_case_cohort_preserves_valid_structures_and_missing_failures(self):
        root=ROOT/'output/benchmarks/omnidocbench-table-unseen-v12'
        cases=read(root/'prepared/manifest.json')['cases'];self.assertEqual(len(cases),20)
        paths=[];missing=[]
        for case in cases:
            path=root/'paddle'/case['id']/'structure.html'
            if path.is_file():paths.append(path)
            else:
                self.assertEqual(read(path.parent/'result.json')['status'],'timeout')
                missing.append(case['id'])
        self.assertEqual(missing,['case-02','case-06']);self.assertEqual(len(paths),18)
        for path in paths:
            raw=path.read_text(encoding='utf-8');result=normalize_wrapper(raw)
            try:parse_html_table(raw)
            except ValueError:
                if result['status']=='repaired':
                    self.assertEqual(len(result['edits']),1)
                    e=result['edits'][0]
                    self.assertEqual(result['html'],raw[:e['start']]+raw[e['end']:])
                    parse_html_table(result['html'])
            else:
                self.assertEqual(result['status'],'unchanged');self.assertEqual(result['html'],raw)

if __name__=='__main__':unittest.main()
