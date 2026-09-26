import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from experiment_unseen_tables import select_cases, choose_baseline_table, choose_effective, aggregate_scores


def page(name, subset='table_hard', html='SECRET'):
    return {'page_info': {'image_path': name, 'page_attribute': {'subset': subset}},
            'layout_dets': [{'category_type': 'table', 'anno_id': 'a',
                             'poly': [0, 0, 100, 0, 100, 80, 0, 80], 'html': html}]}


class UnseenTableTests(unittest.TestCase):
    def test_selection_excludes_and_is_deterministic(self):
        pages = [page(f'{i}.png', 'a' if i % 2 else 'b') for i in range(12)]
        a = select_cases(pages, {'0.png', '2.png'}, 6)
        self.assertEqual(a, select_cases(list(reversed(pages)), {'0.png', '2.png'}, 6))
        self.assertEqual(len({x['page'] for x in a}), 6)
        self.assertFalse({'0.png', '2.png'} & {x['page'] for x in a})
        self.assertEqual({x['subset'] for x in a}, {'a', 'b'})

    def test_gold_and_ignored_objects_cannot_affect_selection(self):
        pages = [page(f'{i}.png') for i in range(4)]
        a = select_cases(pages, set(), 3)
        for p in pages:
            p['layout_dets'][0]['html'] = 'CHANGED'
            p['layout_dets'][0]['text'] = 'HIDDEN'
            p['layout_dets'].append({'category_type': 'table', 'ignore': True})
        self.assertEqual(a, select_cases(pages, set(), 3))
        self.assertNotIn('html', str(a))
        self.assertNotIn('HIDDEN', str(a))

    def test_one_table_per_page_largest_area(self):
        p = page('a.png')
        p['layout_dets'].append({'category_type': 'table', 'anno_id': 'b', 'poly': [1,1,2,1,2,2,1,2]})
        self.assertEqual(select_cases([p], set(), 1)[0]['anno_id'], 'a')

    def test_insufficient_pool_fails_without_replacement(self):
        with self.assertRaises(ValueError): select_cases([page('a.png')], set(), 2)
        with self.assertRaises(ValueError): select_cases([page('a.png')], set(), 0)

    def test_baseline_choice_has_no_text_or_gold_matching(self):
        tables = [{'prov': [{'bbox': {'l': 0, 't': 10, 'r': 10, 'b': 0}}]},
                  {'prov': [{'bbox': {'l': 0, 't': 20, 'r': 20, 'b': 0}}]}]
        self.assertEqual(choose_baseline_table(tables), 1)
        self.assertIsNone(choose_baseline_table([]))

    def test_rejection_never_promotes_higher_scoring_candidate(self):
        self.assertEqual(choose_effective('BASE', 'CAND', {'passed': False}), 'BASE')
        self.assertEqual(choose_effective('BASE', 'CAND', {'passed': True}), 'CAND')
        with self.assertRaises(ValueError): choose_effective('BASE', None, {'passed': True})

    def test_failed_cases_remain_in_denominator(self):
        rows = [{'baseline': {'teds': 1., 'structure_teds': 1.},
                 'effective': {'teds': 1., 'structure_teds': 1.}, 'gate_passed': True},
                {'baseline': {'teds': 0., 'structure_teds': 0.},
                 'effective': {'teds': 0., 'structure_teds': 0.}, 'gate_passed': False}]
        summary = aggregate_scores(rows)
        self.assertEqual(summary['cases'], 2)
        self.assertEqual(summary['baseline_teds'], .5)
        self.assertEqual(summary['effective_teds'], .5)


if __name__ == '__main__': unittest.main()
