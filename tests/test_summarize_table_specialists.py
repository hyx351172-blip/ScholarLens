import copy
import unittest

from scripts.summarize_table_specialists import summarize


def fixture(arm, value):
    baseline = {'teds': .8, 'structure_only': .9}
    candidate = {'teds': value, 'structure_only': .9, 'numeric_token_multiset': {'f1': .7}} if value is not None else None
    return {'arm': arm, 'gold_sha256': 'gold', 'manifest_sha256': 'manifest',
            'evaluator_sha256': {'x': 'y'}, 'baseline_matches_v4_all': True,
            'aggregate': {'fallback_teds': value if value is not None else .8},
            'results': [{'page': 'page.png', 'baseline': baseline, 'candidate': candidate,
                         'effective': candidate or baseline,
                         'runtime': {'status': 'valid_candidate_review_required' if candidate else 'request_failed_baseline_retained',
                                     'latency_seconds': 1, 'usage': None}}]}


class SummaryTests(unittest.TestCase):
    def test_regression_not_gold_selected(self):
        """AC-1005: include regressing candidates, no gold-based replacement."""
        result = summarize([fixture('pp_tablemagic', .6), fixture('qwen_native', None)])
        self.assertEqual(result['arms']['pp_tablemagic']['fallback_teds'], .6)
        self.assertFalse(result['arms']['pp_tablemagic']['smoke_gate_pass'])
        self.assertFalse(result['arms']['qwen_native']['smoke_gate_pass'])
        self.assertIsNone(result['arms']['pp_tablemagic']['known_total_tokens'])
        self.assertEqual(result['arms']['qwen_native']['calls_without_usage'], 1)

    def test_invalid_comparison_rejected(self):
        a, b = fixture('pp_tablemagic', .9), fixture('qwen_native', .9)
        for field, value in [('manifest_sha256', 'other'), ('gold_sha256', 'other'),
                             ('evaluator_sha256', {}), ('baseline_matches_v4_all', False)]:
            bad = copy.deepcopy(b); bad[field] = value
            with self.assertRaises(ValueError):
                summarize([a, bad])
        bad = copy.deepcopy(b); bad['results'][0]['baseline']['teds'] = .7
        with self.assertRaises(ValueError):
            summarize([a, bad])
        with self.assertRaises(ValueError):
            summarize([a, a])


if __name__ == '__main__':
    unittest.main()
