from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from experiment_table_records import run,select_effective

class RecordAdapterTests(unittest.TestCase):
    def test_rejected_repair_retains_previous_effective_not_a_new_baseline(self):
        self.assertEqual(select_effective('oriented baseline','wrong',{'passed':False}),'oriented baseline')
    def test_passing_missing_candidate_rejected(self):
        with self.assertRaises(ValueError):select_effective('base',None,{'passed':True})
    def test_fresh_output_required(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'Fresh output'):run(Path(td))

if __name__=='__main__':unittest.main()
