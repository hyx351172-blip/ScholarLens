import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_table_decoder import ROOT,read
from table_cell_ocr_reread import plan_reread, apply_reread
from table_grid_binding import bind_grid
from audit_cell_ocr_text import compose_diagnostic


class CellRereadTests(unittest.TestCase):
    def setUp(self):
        root=ROOT/'output/benchmarks/omnidocbench-table-geometry-audit-v16/case-10'
        self.grid=read(root/'diagnostics.json')['grid']
        self.structure=(root/'normalized-structure.html').read_text(encoding='utf-8')
        self.capture=read(ROOT/'output/benchmarks/omnidocbench-table-records-validation-v15/paddle/case-10/binding-capture.json')

    def test_geometry_selection(self):
        old=copy.deepcopy(self.grid);p=plan_reread(self.grid)
        self.assertEqual(p['status'],'eligible')
        self.assertEqual([c['cell_id'] for c in p['cells']],[21,22,28,29,30,33,34,37,38])
        self.assertEqual(p['ambiguous_ids'],[72,96,103,118,129])
        self.assertEqual(self.grid,old)

    def test_ineligible_noop(self):
        for reason in ('x_axis_unstable','x_axis_count_mismatch'):
            grid=copy.deepcopy(self.grid);grid['gate']['reasons'].append(reason)
            self.assertEqual(plan_reread(grid)['status'],'ineligible')
        grid=copy.deepcopy(self.grid);grid['gate']={'passed':True,'reasons':[]}
        self.assertEqual(plan_reread(grid)['status'],'ineligible')

    def fake_results(self,p):
        return {c['cell_id']:{'lines':[{'text':'test','score':.99,'bbox':[c['crop_bbox'][0]+5,c['crop_bbox'][1]+5,c['crop_bbox'][0]+40,c['crop_bbox'][1]+20]}]} for c in p['cells']}

    def test_replacement_provenance_no_duplicates_no_mutation(self):
        p=plan_reread(self.grid);old=copy.deepcopy(self.capture)
        result=apply_reread(self.structure,self.capture,self.grid,p,self.fake_results(p))
        self.assertEqual(self.capture,old)
        retained=[x['old_ocr_id'] for x in result['provenance'] if x['source']=='original']
        self.assertEqual(sorted(retained+result['removed_old_ids']),list(range(len(self.grid['assignments']))))
        self.assertEqual(len(set(retained)),len(retained))
        self.assertTrue(set(p['ambiguous_ids']).issubset(result['removed_old_ids']))
        self.assertEqual(len(result['provenance']),len(result['trace']['assignments']))
        self.assertEqual(result['trace']['unassigned_ocr_ids'],[])
        self.assertFalse(result['gate']['passed'])  # invented replacements lose original numbers
        self.assertIn('assigned_numeric_evidence_lost',result['gate']['reasons'])

    def test_bad_rereads_fail_closed(self):
        p=plan_reread(self.grid)
        for mode in ('missing','empty','low','nan','outside','duplicate'):
            results=self.fake_results(p);first=p['cells'][0]['cell_id']
            if mode=='missing':results.pop(first)
            elif mode=='empty':results[first]['lines']=[]
            elif mode=='low':results[first]['lines'][0]['score']=.1
            elif mode=='nan':results[first]['lines'][0]['score']=float('nan')
            elif mode=='outside':results[first]['lines'][0]['bbox']=[0,0,1,1]
            else:results[first]['lines']*=2
            out=apply_reread(self.structure,self.capture,self.grid,p,results)
            self.assertFalse(out['gate']['passed'],mode)
            self.assertIsNone(out['trace'],mode)

    def test_valid_synthetic_reread_can_pass_existing_guards(self):
        structure='<table><tr><td></td><td></td></tr><tr><td></td><td></td></tr></table>'
        cap={'geometry_reprocessing':{'detected_boxes':[[0,0,50,50],[50,0,100,50],[0,50,50,100],[50,50,100,100]]},
             'match':{'ocr_boxes':[[5,5,20,15],[55,5,70,15],[40,60,60,70]]},
             'render':{'texts':['Head A','Head B','AB']}}
        grid=bind_grid(structure,cap,[100,100]);plan=plan_reread(grid)
        result=apply_reread(structure,cap,grid,plan,{
            2:{'lines':[{'text':'A','score':.99,'bbox':[10,60,20,70]}]},
            3:{'lines':[{'text':'B','score':.99,'bbox':[60,60,70,70]}]}})
        self.assertTrue(result['gate']['passed'])
        self.assertEqual([c['text'] for c in result['trace']['cells']],['Head A','Head B','A','B'])
        self.assertEqual(result['removed_old_ids'],[2])

    def test_diagnostic_keeps_low_confidence_without_altering_unselected_cells(self):
        from audit_table_decoder import parse_html_table
        p=plan_reread(self.grid);results=self.fake_results(p)
        first=p['cells'][0]['cell_id'];results[first]['lines'][0]['score']=.1
        results[first]['lines'][0]['text']='low-confidence evidence'
        text=compose_diagnostic(self.grid['html'],p,results)
        cells=parse_html_table(text)[0]['table_cells'];selected=set(results)
        self.assertEqual(cells[first]['text'],'low-confidence evidence')
        for i,c in enumerate(cells):
            if i not in selected:self.assertEqual(c['text'],self.grid['cells'][i]['text'])
        results.pop(first)
        with self.assertRaises(ValueError):compose_diagnostic(self.grid['html'],p,results)

    def test_existing_output_refused_before_models(self):
        import tempfile
        from experiment_cell_ocr_reread import run
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'Fresh output'):run(Path(d))

    def test_real_frozen_run_rejects_low_confidence_and_retains_all_fallbacks(self):
        from audit_table_decoder import sha
        root=ROOT/'output/benchmarks/omnidocbench-table-cell-ocr-v17-replay'
        summary=read(root/'summary.json');self.assertEqual(summary['local_ocr_calls'],9)
        self.assertEqual(summary['paid_api_calls'],0)
        for row in summary['results']:
            self.assertFalse(row['gate']['passed'])
            a=root/row['id']/'effective.html';b=root/row['id']/'previous-effective.html'
            self.assertEqual(a.is_file(),b.is_file())
            if a.is_file():self.assertEqual(sha(a),sha(b))
        result=read(root/'text-diagnostics-replay/results.json')['results'][0]
        self.assertLess(result['scores']['reread_diagnostic_only']['teds'],result['scores']['previous_effective']['teds'])
        self.assertGreater(result['scores']['reread_diagnostic_only']['teds'],result['scores']['old_grid_partial']['teds'])


if __name__=='__main__':unittest.main()
