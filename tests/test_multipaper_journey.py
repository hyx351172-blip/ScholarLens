import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('journey',Path(__file__).parent/'integration/run_multipaper_journey.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MultiPaperJourneyTests(unittest.TestCase):
    def response(self):
        return {'success':True,'answer':'result [S1]','sources':[{'source_id':'S1','file_id':'f1',
          'chunk_text':'evidence','metadata':{'chunk_id':'c1','page_start':2,'page_end':2}}]}

    def test_provenance_checks_exact_file_and_chunk(self):
        detail={'f1':{'pages':3,'chunks':{'c1':{'retrieval_text':'evidence','page_start':2,'page_end':2}}}}
        self.assertTrue(m.check_response(self.response(),detail,{'f1'},True)['contract_passed'])
        self.assertFalse(m.check_response(self.response(),detail,{'other'},True)['contract_passed'])
        bad=self.response();bad['sources'][0]['chunk_text']='altered'
        self.assertFalse(m.check_response(bad,detail,{'f1'},True)['contract_passed'])

    def test_answerable_cannot_pass_empty_sources(self):
        self.assertFalse(m.check_response({'success':True,'answer':'text','sources':[]},{},set(),True)['contract_passed'])

    def test_unknown_and_malformed_citations_fail(self):
        detail={'f1':{'pages':3,'chunks':{'c1':{'retrieval_text':'evidence','page_start':2,'page_end':2}}}}
        for answer in ('text [S99]','text [S母公司]','text [S1'):
            r=self.response();r['answer']=answer
            result=m.check_response(r,detail, {'f1'},True)
            self.assertFalse(result['contract_passed'])
            self.assertTrue(result['unknown_citations'] or result['malformed'])

    def test_cross_paper_coverage_is_not_just_valid_citations(self):
        detail={'f1':{'pages':3,'chunks':{'c1':{'retrieval_text':'evidence','page_start':2,'page_end':2}}}}
        result=m.check_response(self.response(),detail,{'f1','f2'},True)
        self.assertTrue(result['contract_passed'])
        self.assertFalse(result['cross_paper_coverage'])

    def test_empty_kb_refusal_has_no_sources(self):
        result=m.check_response({'success':True,'answer':'当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。','sources':[]},{},set(),False)
        self.assertTrue(result['contract_passed'])
        self.assertTrue(result['fixed_refusal'])
        self.assertEqual(result['source_count'],0)
