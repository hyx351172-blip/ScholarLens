"""Run in OmniDocBench's pinned evaluation environment; no network/model calls."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from score_unseen_tables import ROOT, score_case, read, write
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'backend/data/benchmarks/model_cache/matplotlib'))
os.environ.setdefault('HF_HUB_OFFLINE', '1')


class OfficialScoringTests(unittest.TestCase):
    def fixture(self, directory, baseline='41', candidate='42', gate=False):
        root = Path(directory); final = root / 'final/case-01'; final.mkdir(parents=True)
        out = root / 'scored/case-01'; out.mkdir(parents=True)
        table = lambda v: '<table><tr><td>' + v + '</td></tr></table>'
        write(root / 'scoring-only-gold.json', {'case-01': {'html': table('42')}})
        write(final / 'result.json', {'page': 'synthetic.png', 'gate': {'passed': gate, 'reasons': []},
                                      'baseline_status': 'completed' if baseline else 'failed'})
        for name, value in [('baseline', baseline), ('candidate', candidate), ('effective', candidate if gate else baseline)]:
            if value: (final / (name + '.html')).write_text(table(value), encoding='utf-8')
        return root, out

    def test_official_teds_does_not_promote_rejected_perfect_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            root, out = self.fixture(d)
            score_case(root, 'case-01', out); result = read(out / 'result.json')
            self.assertEqual(result['candidate_diagnostic']['teds'], 1.)
            self.assertLess(result['baseline']['teds'], 1.)
            self.assertEqual(result['effective'], result['baseline'])

    def test_missing_outputs_score_zero(self):
        with tempfile.TemporaryDirectory() as d:
            root, out = self.fixture(d, baseline=None, candidate=None)
            score_case(root, 'case-01', out); result = read(out / 'result.json')
            self.assertEqual(result['baseline']['teds'], 0.)
            self.assertEqual(result['effective']['teds'], 0.)

    def test_effective_artifact_must_match_frozen_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root, out = self.fixture(d)
            (root / 'final/case-01/effective.html').write_text('changed', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'gate/output drift'):
                score_case(root, 'case-01', out)


if __name__ == '__main__': unittest.main()
