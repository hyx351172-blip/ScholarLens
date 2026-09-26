"""AC-1101..AC-1105: real tensor semantics and conservative offline experiment."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_table_decoder import (inspect_probabilities, patch_graph, graph_audit,
                                 validate_output, preflight, pair_summary, clone_model, sha, FILES)


def fixture_graph():
    def op(kind, out, inputs=(), **attrs):
        return {'#': ('0.' if kind == 'combine' else '1.') + kind, 'I': [{'%': v} for v in inputs],
                'O': [{'%': out}], 'A': [{'N': k, 'AT': {'D': v}} for k, v in attrs.items()]}
    ops = [op('full', v, value=501.0) for v in (2367, 2373, 2379)]
    ops += [op('combine', out, ins) for out, ins in
            ((2369, [2361, 2367, 2368]), (2375, [2361, 2373, 2374]), (2380, [2361, 2379]))]
    ops += [op('assign_value_', 2389, [2388], values=[{'D': 500.0}]),
            op('scale', 2393, [2389, 2392], bias=1.0),
            op('less_than', 2394, [2391, 2393])]
    return {'program': {'regions': [{'blocks': [{'ops': ops}]}]}}


class DecoderTests(unittest.TestCase):
    def probs(self, ids):
        return np.eye(4, dtype=np.float32)[[ids]]

    def test_natural_eos(self):
        got = inspect_probabilities(self.probs([1, 2, 3]), ['sos', '<tr>', '</tr>', 'eos'], 3, 500)
        self.assertEqual(got['termination'], 'eos')
        self.assertEqual(got['eos_index'], 2)
        self.assertFalse(got['hit_step_cap'])

    def test_missing_eos_at_exact_cap(self):
        got = inspect_probabilities(self.probs([1] * 501), ['sos', 'x', 'y', 'eos'], 3, 500)
        self.assertEqual(got['termination'], 'length_limit')
        self.assertEqual(got['steps'], 501)

    def test_short_no_eos_and_position_zero(self):
        self.assertEqual(inspect_probabilities(self.probs([1]), ['sos', 'x', 'y', 'eos'], 3, 500)['termination'], 'unknown')
        self.assertEqual(inspect_probabilities(self.probs([3]), ['sos', 'x', 'y', 'eos'], 3, 500)['termination'], 'invalid_eos_at_start')

    def test_invalid_tensors(self):
        for probs in (np.zeros((2, 1, 4)), np.zeros((1, 0, 4)), np.ones((1, 502, 4)),
                      np.ones((1, 1, 4)) * np.nan, np.ones((1, 1, 4)), np.zeros((1, 2, 3))):
            with self.subTest(shape=probs.shape), self.assertRaises(ValueError):
                inspect_probabilities(probs, ['sos', 'x', 'y', 'eos'], 3, 500)

    def test_exact_four_graph_changes_and_no_source_mutation(self):
        original = fixture_graph(); before = copy.deepcopy(original)
        changed = patch_graph(original, 1000)
        self.assertEqual(original, before)
        self.assertEqual(graph_audit(original)['max_text_length'], 500)
        self.assertEqual(graph_audit(changed)['max_text_length'], 1000)
        a = original['program']['regions'][0]['blocks'][0]['ops']
        b = changed['program']['regions'][0]['blocks'][0]['ops']
        self.assertEqual(sum(x != y for x, y in zip(a, b)), 4)

    def test_graph_mismatch_rejected(self):
        bad = fixture_graph(); bad['program']['regions'][0]['blocks'][0]['ops'][0]['A'][0]['AT']['D'] = 500
        with self.assertRaises(ValueError): graph_audit(bad)
        bad = fixture_graph(); bad['program']['regions'][0]['blocks'][0]['ops'][-1]['I'][1]['%'] = 0
        with self.assertRaises(ValueError): patch_graph(bad, 1000)
        for limit in (500, 1001, True, 100000):
            with self.assertRaises(ValueError): patch_graph(fixture_graph(), limit)

    def test_real_pir_parameter_node_uses_single_output_object(self):
        graph = fixture_graph()
        graph['program']['regions'][0]['blocks'][0]['ops'].insert(0, {'#': 'p', 'O': {'%': 1}, 'A': [0, 1]})
        self.assertEqual(graph_audit(graph)['max_steps'], 501)

    def test_html_completion_requires_eos_and_valid_grid(self):
        valid = '<html><body><table><tr><td></td></tr></table></body></html>'
        self.assertTrue(validate_output(valid, {'termination': 'eos'})['valid'])
        self.assertFalse(validate_output(valid, {'termination': 'length_limit'})['valid'])
        self.assertFalse(validate_output(valid.replace('</tr>', ''), {'termination': 'eos'})['valid'])

    def test_preflight_rejects_bad_inputs_before_creating_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); prepared = root / 'in'; prepared.mkdir()
            (prepared / 'manifest.json').write_text(json.dumps({'results': []}))
            with self.assertRaises(ValueError): preflight(prepared, root / 'out')
            self.assertFalse((root / 'out').exists())
            with self.assertRaises(ValueError): preflight(prepared, prepared / 'out')

    def test_pairing_prefix_and_control(self):
        a = {'crop_sha256': 'same', 'model': 'wired', 'weight_sha256': 'weights',
             'preprocess_sha256': 'same', 'vocabulary': ['sos', 'x', 'eos'],
             'token_ids': [1, 1], 'termination': 'length_limit'}
        b = dict(a, token_ids=[1, 1, 2], termination='eos')
        self.assertTrue(pair_summary(a, b)['prefix_identical'])
        self.assertTrue(pair_summary(a, b)['length_limit_resolved'])
        b['weight_sha256'] = 'other'
        with self.assertRaises(ValueError): pair_summary(a, b)

    def test_clone_preserves_originals_and_copied_weights(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / 'model'; source.mkdir()
            for f in FILES: (source / f).write_text('{}', encoding='utf-8')
            (source / 'inference.json').write_text(json.dumps(fixture_graph()), encoding='utf-8')
            hashes = {f: sha(source / f) for f in FILES}
            with patch('audit_table_decoder.GRAPH_SHA', hashes['inference.json']):
                result = clone_model(source, root / 'clone')
                self.assertEqual(result['after']['max_steps'], 1001)
                self.assertEqual(hashes, {f: sha(source / f) for f in FILES})
                self.assertEqual(sha(source / 'inference.pdiparams'), sha(root / 'clone/inference.pdiparams'))
                with self.assertRaises(ValueError): clone_model(source, root / 'clone')
                with self.assertRaises(ValueError): clone_model(source, source / 'nested')

    def test_unknown_graph_never_creates_clone(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'model'; source.mkdir()
            (source / 'inference.json').write_text('{}')
            with self.assertRaises(ValueError): clone_model(source, Path(td) / 'clone')
            self.assertFalse((Path(td) / 'clone').exists())

    def test_frozen_hash_and_path_escape_checks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); prepared = root / 'in'; prepared.mkdir()
            case = prepared / 'page'; case.mkdir()
            crop = case / 'crop.png'; crop.write_bytes(b'fixed-image')
            baseline = case / 'baseline.html'; baseline.write_text('<table></table>')
            item = dict(id='page', page='page.png', crop='page/crop.png',
                        crop_sha256=sha(crop), baseline_sha256=sha(baseline))
            manifest = prepared / 'manifest.json'
            manifest.write_text(json.dumps({'results': [item]}))
            self.assertEqual(len(preflight(prepared, root / 'out')['results']), 1)
            crop.write_bytes(b'changed')
            with self.assertRaises(ValueError): preflight(prepared, root / 'out')
            item['crop'] = '../outside.png'
            manifest.write_text(json.dumps({'results': [item]}))
            with self.assertRaises(ValueError): preflight(prepared, root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_valid_html_with_holes_still_rejected(self):
        raw = '<table><tr><td></td><td></td></tr><tr><td></td></tr></table>'
        got = validate_output(raw, {'termination': 'eos'})
        self.assertFalse(got['valid'])
        self.assertIn('uncovered slots', got['html_validation']['error'])

    def test_nonidentical_prefix_does_not_prove_length_causality(self):
        base = dict(crop_sha256='a', model='w', weight_sha256='b', preprocess_sha256='c',
                    vocabulary=['sos', 'x', 'eos'], token_ids=[1, 1], termination='length_limit')
        changed = dict(base, token_ids=[1, 0, 2], termination='eos')
        self.assertFalse(pair_summary(base, changed)['length_limit_resolved'])


if __name__ == '__main__':
    unittest.main()
