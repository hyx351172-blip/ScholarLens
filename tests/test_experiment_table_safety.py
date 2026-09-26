import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from experiment_table_safety import launch, map_geometry, replay_trace, SOURCE
from table_candidate_safety import guard_candidate
from audit_table_decoder import read


class SafetyAdapterTests(unittest.TestCase):
    def test_real_collapsed_records_previous_gate_passes_new_gate_rejects(self):
        # Real v12 parser/OCR seam; no expected HTML or benchmark labels involved.
        trace=read(SOURCE/'final/case-13/grid-trace.json')
        self.assertTrue(trace['gate']['passed'])
        result=guard_candidate(trace)
        self.assertFalse(result['gate']['passed'])
        self.assertEqual(result['cells'],trace['cells'])
        self.assertIn('aligned_multiline_row_ambiguity',result['gate']['reasons'])

    def test_real_formula_control_not_rejected(self):
        t=read(SOURCE/'final/case-09/grid-trace.json')
        self.assertTrue(t['gate']['passed'])
        self.assertTrue(guard_candidate(t)['gate']['passed'])

    def test_real_prior_rejection_not_promoted(self):
        self.assertFalse(replay_trace(SOURCE/'final/case-20')['gate']['passed'])

    def test_rotated_raw_and_bound_boxes_use_separate_ids(self):
        t={'cells':[{'cell_id':7,'bbox':[20,60,60,90],'ocr_ids':[12]}]}
        raw={'res':{'overall_ocr_res':{'rec_boxes':[[20,60,60,90]],'rec_texts':['abc']}}}
        out=map_geometry(t,raw,[100,80],90,[100,200])
        self.assertEqual(out['cells'][0]['original_page_bbox'],[110,220,140,260])
        self.assertEqual(out['cells'][0]['ocr_ids'],[12])
        self.assertEqual(out['raw_ocr'][0]['raw_ocr_id'],0)

    def test_timeout_never_accepts_partial_worker_result(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'run'
            def partial(*args,**kwargs):
                (dest/'result.json').write_text(json.dumps({'status':'completed'}),encoding='utf-8')
                raise subprocess.TimeoutExpired('local-worker',300)
            with patch('experiment_table_safety.subprocess.run',side_effect=partial):
                result=launch('orient',Path(td)/'x.png',dest,{})
            self.assertEqual(result['status'],'timeout')
            self.assertNotIn('decision',result)

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileExistsError):launch('orient',Path(td)/'x',Path(td),{})

if __name__=='__main__':unittest.main()
