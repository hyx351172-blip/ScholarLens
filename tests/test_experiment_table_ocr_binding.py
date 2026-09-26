"""AC-1201/1203: on-disk provenance/path contracts; no models or network."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from experiment_table_ocr_binding import check_inputs, plain, DEPENDENCIES, MODELS, FILES, sha, candidate_status
from score_table_ocr_binding import score


class BindingRunnerTests(unittest.TestCase):
    def fixture(self, root):
        prepared, v7, v8, cache = [root / x for x in ('prepared', 'v7', 'v8', 'cache')]
        for p in (prepared / 'page', v7 / 'page', v8 / 'extended/page', cache): p.mkdir(parents=True)
        def save(path, obj): path.write_text(json.dumps(obj), encoding='utf-8')
        crop = prepared / 'page/crop.png'; crop.write_bytes(b'image')
        baseline = prepared / 'page/baseline.html'; baseline.write_text('<table><tr><td>1</td></tr></table>')
        save(prepared / 'manifest.json', {'results': [{'id': 'page', 'page': 'page.png', 'crop': 'page/crop.png',
             'crop_sha256': sha(crop), 'baseline_sha256': sha(baseline)}]})
        digest = sha(prepared / 'manifest.json')
        save(v7 / 'summary.json', {'manifest_sha256': digest})
        save(v8 / 'summary.json', {'manifest_sha256': digest, 'original_models_unchanged': True})
        save(v7 / 'page/paddle-raw.json', {})
        save(v7 / 'page/worker-result.json', {'raw_result_sha256': sha(v7 / 'page/paddle-raw.json')})
        save(v8 / 'extended/page/result.json', {'crop_sha256': sha(crop), 'validation': {'valid': True}, 'termination': 'eos'})
        (v8 / 'extended/page/structure.html').write_text('<table><tr><td></td></tr></table>')
        for name in MODELS:
            p = v8 / 'experimental-models' / name; p.mkdir(parents=True)
            for f in FILES: (p / f).write_text('model')
            save(p / 'clone-audit.json', {'clone_sha256': {f: sha(p / f) for f in FILES}})
        for name in DEPENDENCIES.values():
            p = cache / name; p.mkdir(parents=True)
            for f in ('inference.json', 'inference.pdiparams', 'inference.yml'): (p / f).write_text('model')
        return prepared, v7, v8, cache

    def test_preflight_checks_cached_ocr_and_models_before_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); prepared, v7, v8, cache = self.fixture(root)
            digest = sha(v8 / 'experimental-models' / MODELS[0] / 'inference.json')
            with patch('experiment_table_ocr_binding.CACHE', cache), patch('experiment_table_ocr_binding.CLONE_SHA', digest):
                _, eligible, hashes = check_inputs(prepared, v7, v8, root / 'out')
                self.assertEqual(eligible, ['page']); self.assertGreater(len(hashes), 20)
                self.assertFalse((root / 'out').exists())
                (v7 / 'page/paddle-raw.json').write_text('{"changed":true}')
                with self.assertRaises(ValueError): check_inputs(prepared, v7, v8, root / 'out')

    def test_evidence_output_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); prepared, v7, v8, _ = self.fixture(root)
            with self.assertRaises(ValueError): check_inputs(prepared, v7, v8, v8 / 'out')
            with self.assertRaises(ValueError): check_inputs(prepared, v7, v8, prepared)

    def test_score_overlap_fails_before_loading_evaluator_or_gold(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(ValueError):
                score(root / 'prep', root / 'run', root / 'v8', root / 'gold', root / 'eval', root / 'prev', root / 'run/new')

    def test_json_conversion_preserves_match_keys_and_text(self):
        self.assertEqual(plain({0: [1, '<script>', None]}), {'0': [1, '<script>', None]})

    def test_valid_html_with_missing_or_failed_binding_gate_retains_baseline(self):
        self.assertEqual(candidate_status({'candidate_valid': True}), 'binding_rejected_baseline_retained')
        self.assertEqual(candidate_status({'candidate_valid': True, 'binding_integrity': {'passed': False}}),
                         'binding_rejected_baseline_retained')

    def test_passed_gate_is_review_only_not_production_promotion(self):
        self.assertEqual(candidate_status({'candidate_valid': True, 'binding_integrity': {'passed': True}}),
                         'valid_candidate_review_required')


if __name__ == '__main__': unittest.main()
