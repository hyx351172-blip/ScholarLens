import unittest

from scripts.summarize_html_table_ab import summarize


def score(arm, candidate):
    baseline = {'teds': .8, 'structure_only': .9, 'numeric_token_multiset': {'f1': .7}}
    cand = {'teds': candidate, 'structure_only': .95, 'numeric_token_multiset': {'f1': .9}} if candidate is not None else None
    return {'arm': arm, 'gold_sha256': 'gold', 'manifest_sha256': 'manifest', 'baseline_matches_v4_all': True,
            'evaluator_sha256': {'test': 'same'}, 'aggregate': {'candidate_valid_count': int(cand is not None)},
            'results': [{'page': 'page.png', 'baseline': baseline, 'candidate': cand, 'effective': cand or baseline,
                         'candidate_teds_delta': candidate - .8 if cand else None,
                         'runtime': {'status': 'valid_candidate_review_required' if cand else 'request_failed_baseline_retained',
                                     'latency_seconds': 1, 'first_text_seconds': .2,
                                     'usage': {'total_tokens': 10} if cand else None}}]}


class SummaryTests(unittest.TestCase):
    def test_failures_and_regressions_are_not_hidden(self):
        """AC-HTML-905/906: no winner selection; explicit missing usage, strict held-out gate."""
        report = summarize([score('generic_html', .6), score('ocr_html', None)])
        self.assertFalse(report['ready_for_heldout_expansion'])
        self.assertEqual(report['arms']['generic_html']['regression_pages'], ['page.png'])
        self.assertEqual(report['arms']['ocr_html']['attempted_calls_without_usage'], 1)
        self.assertEqual(report['arms']['ocr_html']['known_total_tokens'], 0)
        self.assertEqual(report['tables'][0]['ocr_html']['effective_teds'], .8)

    def test_mismatched_provenance_rejected(self):
        a, b = score('generic_html', .9), score('ocr_html', .95)
        b['gold_sha256'] = 'different'
        with self.assertRaises(ValueError):
            summarize([a, b])
        b = score('ocr_html', .95)
        b['results'][0]['baseline']['teds'] = .7
        with self.assertRaises(ValueError):
            summarize([a, b])


if __name__ == '__main__':
    unittest.main()
