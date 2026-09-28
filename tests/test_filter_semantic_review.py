import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('filter_review',Path(__file__).parent/'integration/filter_semantic_review.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FilterReviewTests(unittest.TestCase):
    def test_partition_does_not_delete_or_mutate(self):
        cases=[{'id':f'Q{i:02d}'} for i in range(1,21)]
        active,excluded=m.partition(cases,m.EXCLUDED)
        self.assertEqual(len(active),15)
        self.assertEqual({c['id'] for c in excluded},m.EXCLUDED)
        self.assertEqual(len(cases),20)

    def test_unknown_id_fails(self):
        with self.assertRaises(ValueError):
            m.partition([{'id':'Q01'}],{'Q99'})

    def test_summary_uses_filtered_denominator(self):
        rows=[dict(label='answerable',fixed_abstention=True,answer_token_f1=0,guard_status='invalid_structure'),
              dict(label='unanswerable',fixed_abstention=False,answer_token_f1=0,guard_status='passed')]
        s=m.summarize(rows)
        self.assertEqual((s['count'],s['answerable'],s['unanswerable']), (2,1,1))
        self.assertEqual(s['answerable_fixed_refusals'],1)
        self.assertEqual(s['format_failures'],1)
