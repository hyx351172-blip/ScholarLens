"""Real official scorer at the v14 output/fallback seam, no model inference."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from score_table_records import ROOT,read,write,run
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'backend/data/benchmarks/model_cache/matplotlib'))

class RecordScoringTests(unittest.TestCase):
    def fixture(self,td,changed=True,drift=False):
        root=Path(td)/'new';source=Path(td)/'previous';gold=Path(td)/'labels';gold.mkdir()
        new=root/'final/case';new.mkdir(parents=True)
        old=source/'final/case';old.mkdir(parents=True);(source/'scored').mkdir()
        table=lambda x:'<table><tr><td>'+x+'</td></tr></table>'
        (old/'effective.html').write_text(table('41'),encoding='utf-8')
        (new/'previous-effective.html').write_text(table('41'),encoding='utf-8')
        (new/'candidate.html').write_text(table('42' if changed else '41'),encoding='utf-8')
        (new/'effective.html').write_text(table('bad' if drift else '42' if changed else '41'),encoding='utf-8')
        write(source/'summary.json',{'source':str(gold)})
        write(gold/'scoring-only-gold.json',{'case':{'html':table('42')}})
        write(source/'scored/results.json',{'results':[{'id':'case','effective_v13':{'teds':.25,'structure_teds':1.,'missing_output':False}}]})
        write(root/'input-integrity.json',{})
        write(root/'summary.json',{'source':str(source),'artifact_sha256':{},'results':[{'id':'case',
            'status':'reconstructed' if changed else 'unchanged','gate':{'passed':True},'effective_source':'candidate'}]})
        return root
    def test_changed_table_scored_and_cell_diagnostics_saved(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.fixture(td);run(root)
            r=read(root/'scored/results.json')['results'][0]
            self.assertEqual(r['effective_v14']['teds'],1.)
            self.assertFalse(r['score_reused_byte_identical'])
            self.assertTrue((root/'scored/case/cell-diagnostics.json').is_file())
    def test_unchanged_table_reuses_only_identical_html(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.fixture(td,False);run(root)
            r=read(root/'scored/results.json')['results'][0]
            self.assertTrue(r['score_reused_byte_identical'])
            self.assertEqual(r['effective_v14']['teds'],.25)
    def test_gate_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'gate/output drift'):run(self.fixture(td,drift=True))

if __name__=='__main__':unittest.main()
