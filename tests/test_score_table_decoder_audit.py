"""AC-1104/AC-1105: scoring must preserve failures/regressions and stay offline."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from score_table_decoder_audit import aggregate_structure, score


class StructureScoreTests(unittest.TestCase):
    def test_failure_and_regression_are_not_gold_selected(self):
        def arm(candidate, baseline):
            return dict(valid=candidate is not None, candidate_structure_teds=candidate,
                        fallback_structure_teds=candidate if candidate is not None else baseline)
        rows = [{'arms': {'original': arm(None, .5), 'extended': arm(.3, .5)}},
                {'arms': {'original': arm(None, .9), 'extended': arm(None, .9)}}]
        out = aggregate_structure(rows)
        self.assertEqual(out['extended']['valid_count'], 1)
        self.assertEqual(out['extended']['table_count'], 2)
        self.assertAlmostEqual(out['original']['fallback_structure_teds'], .7)
        self.assertAlmostEqual(out['extended']['fallback_structure_teds'], .6)
        self.assertEqual(out['extended']['valid_candidates_structure_teds'], [.3])

    def test_empty_set_is_not_a_success(self):
        with self.assertRaises(ValueError): aggregate_structure([])

    def test_reused_or_overlapping_output_rejected_before_evaluator(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); evidence = root / 'run'
            with self.assertRaises(ValueError):
                score(root / 'prepared', evidence, root / 'gold.json', root / 'evaluator',
                      root / 'previous.json', evidence / 'overwrite')
            self.assertFalse(evidence.exists())


if __name__ == '__main__':
    unittest.main()
