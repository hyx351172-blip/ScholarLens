import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('review',Path(__file__).parent/'integration/build_semantic_review.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SemanticReviewTests(unittest.TestCase):
    def test_no_draft_becomes_gold(self):
        with self.assertRaises(ValueError):
            m.require_approved([{'review':{'status':'pending','reviewer':'','decision':None}}])

    def test_approval_needs_identity_and_decision(self):
        for review in ({'status':'approved','reviewer':'','decision':'answerable'},
                       {'status':'approved','reviewer':'human','decision':None}):
            with self.assertRaises(ValueError):
                m.require_approved([{'review':review}])

    def test_unmapped_evidence_never_gets_fake_source(self):
        result=m.map_evidence(['invented'],{'S1':'real'})
        self.assertEqual(result,[{'text':'invented','source_ids':[]}])

    def test_all_reference_variants_retained(self):
        refs=[{'evidence':['same']},{'evidence':['other','same']}]
        mapped=m.map_evidence([e for r in refs for e in r['evidence']],{'S2':'same','S3':'other'})
        self.assertEqual(len(mapped),2)
        self.assertEqual(mapped[0]['source_ids'],['S2'])
