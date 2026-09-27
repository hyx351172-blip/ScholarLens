import unittest
from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from tests.integration.analyze_answer_mode_ab import paired_metrics, rejected_claims


class PairedAnalysisTests(unittest.TestCase):
    # AC-3505 / AC-3506: do not treat transport failure as model quality or speed.
    def test_pair_denominators_exclude_failed_pair_but_keep_empty_and_rejections(self):
        labels=[dict(id=i,answerable=i!='E01') for i in ('A01','A02','E01')]
        rows=[dict(id=i,mode=m,status='ok',provider_calls=int(i!='E01'),seconds=10,
            answer='fact [S1]',citation_ids=['S1'],unknown_citations=[],usage={'total_tokens':100})
              for i in ('A01','A02','E01') for m in ('legacy','claim_bound')]
        rows[0].update(status='error',seconds=.1,answer=None)
        rows[3].update(answer=INSUFFICIENT_EVIDENCE,citation_ids=[])
        for r in rows[4:]:r.update(answer=INSUFFICIENT_EVIDENCE,citation_ids=[],seconds=0)
        result=paired_metrics(labels,rows)
        self.assertEqual(result['excluded_pairs'],['A01'])
        self.assertEqual(result['paired_cases'],2)
        self.assertEqual(result['paired_live_cases'],1)
        self.assertEqual(result['modes']['legacy']['mean_generation_seconds'],10)
        self.assertEqual(result['modes']['legacy']['answerable_nonrefusal_with_citations'],1)
        self.assertEqual(result['modes']['claim_bound']['answerable_fixed_refusals'],1)

    def test_rejected_claim_diagnostic_does_not_rewrite_answer(self):
        case=dict(documents=[dict(chunk_text='a',filename='a.pdf')])
        r=dict(guard_status='invalid_claim_structure',answer=INSUFFICIENT_EVIDENCE,
            raw_content='{"status":"answered","claims":[{"text":"A;B", "evidence_ids":["S1:E0001"]}]}')
        self.assertEqual(rejected_claims(case,r)[0]['claim_index'],1)
        self.assertEqual(r['answer'],INSUFFICIENT_EVIDENCE)


if __name__=='__main__':unittest.main()
