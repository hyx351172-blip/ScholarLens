"""Actual official evaluator, synthetic admission/reuse seams; no model calls."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from score_table_safety import ROOT,read,write,sha,run
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'backend/data/benchmarks/model_cache/matplotlib'))

class SafetyScoringTests(unittest.TestCase):
    def fixture(self,td,changed=True,drift=False):
        root=Path(td)/'new';src=Path(td)/'old';case='sample'
        old=src/'final'/case;old.mkdir(parents=True)
        new=root/'final'/case;new.mkdir(parents=True)
        table=lambda v:'<table><tr><td>'+v+'</td></tr></table>'
        text=table('42' if changed else '41')
        (old/'effective.html').write_text(table('41'),encoding='utf-8')
        (new/'effective.html').write_text(text,encoding='utf-8')
        (new/'baseline.html').write_text(table('mismatch') if drift else text,encoding='utf-8')
        write(src/'scoring-only-gold.json',{case:{'html':table('42')}})
        score={'teds':.25,'structure_teds':1.,'missing_output':False}
        (src/'scored').mkdir()
        write(src/'scored/results.json',{'results':[{'id':case,'baseline':score,'effective':score}]})
        write(root/'input-integrity.json',{})
        write(root/'summary.json',{'source':str(src),'artifact_sha256':{},'results':[{'id':case,'angle_ccw':0,
            'gate':{'passed':False,'reasons':['rejected']},'effective_source':'baseline'}]})
        return root
    def test_changed_html_gets_fresh_official_score(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.fixture(td);run(root);r=read(root/'scored/results.json')['results'][0]
            self.assertFalse(r['score_reused_byte_identical'])
            self.assertEqual(r['effective_v13']['teds'],1.)
    def test_byte_identical_only_reuses_frozen_score(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.fixture(td,False);run(root);r=read(root/'scored/results.json')['results'][0]
            self.assertTrue(r['score_reused_byte_identical'])
            self.assertEqual(r['effective_v13']['teds'],.25)
    def test_bad_gate_contract_never_scored(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'gate/output drift'):run(self.fixture(td,drift=True))

if __name__=='__main__':unittest.main()
