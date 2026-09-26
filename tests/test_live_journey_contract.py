import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).parent/'integration'))
from run_live_journey_v1 import check_answer,check_ingestion


class LiveContractTests(unittest.TestCase):
    def test_ingestion_requires_all_stages_nonzero_matching_counts_and_pdf(self):
        data={s:{'status':'completed'} for s in ('extraction','chunking','storage')}
        data['chunking']['total_chunks']=4
        docs={'total_documents':1,'total_chunks':4};details={'total_chunks':4}
        self.assertTrue(check_ingestion(data,docs,details,True)['passed'])
        self.assertFalse(check_ingestion(data,docs,details,False)['passed'])
        self.assertFalse(check_ingestion(data,docs,{'total_chunks':3},True)['passed'])
        for stage in ('extraction','chunking','storage'):
            bad=copy.deepcopy(data);bad[stage]['status']='failed'
            self.assertFalse(check_ingestion(bad,docs,details,True)['passed'])

    def test_answer_contract_rejects_missing_unknown_and_wrong_provenance(self):
        source={'source_id':'S1','file_id':'f','chunk_text':'evidence','metadata':{'page_start':8,'page_end':8}}
        good={'success':True,'answer':'28.4 [S1]','sources':[source]}
        self.assertTrue(check_answer(good,'f',15,True)['contract_passed'])
        for change in ({'answer':''},{'answer':'28.4 [S9]'},{'sources':[]},{'success':False}):
            self.assertFalse(check_answer({**good,**change},'f',15,True)['contract_passed'])
        self.assertFalse(check_answer(good,'other',15,True)['contract_passed'])
        self.assertFalse(check_answer(good,'f',7,True)['contract_passed'])

    def test_unanswerable_contract_does_not_equal_semantic_correctness(self):
        result=check_answer({'success':True,'answer':'Insufficient evidence','sources':[]},'f',15,False)
        self.assertTrue(result['contract_passed'])
        self.assertNotIn('semantic_correctness',result)

    def test_malformed_marker_is_not_hidden_by_valid_marker(self):
        source={'source_id':'S1','file_id':'f','chunk_text':'evidence','metadata':{'page_start':1}}
        result=check_answer({'success':True,'answer':'Fact [S1] [S母公司]','sources':[source]},'f',15,True)
        self.assertFalse(result['contract_passed'])
        self.assertEqual(result['malformed_citations'],['[S母公司]'])


if __name__=='__main__':unittest.main()
