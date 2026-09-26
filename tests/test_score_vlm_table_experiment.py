import unittest

from scripts.score_vlm_table_experiment import safe_table, numeric_diagnostic, aggregate_pairs, inspect_response


class VLMTableScoringTests(unittest.TestCase):
    def test_preview_does_not_execute_gold_or_model_markup(self):
        """AC-VTABLE-806: untrusted HTML is reconstructed, not passed through."""
        raw = '<table onclick="bad()"><tr><td colspan="2">&lt;value&gt;<script>bad()</script><img src=x onerror=bad()>0.18</td></tr></table>'
        result = safe_table(raw)
        self.assertIn('colspan="2"', result)
        self.assertIn('&lt;value&gt;', result)
        for danger in ('onclick', '<script', '<img', 'bad()'):
            self.assertNotIn(danger, result)

    def test_numeric_multiset_is_not_a_row_alignment_metric(self):
        """AC-VTABLE-805: repeated/dropped values count, reordering does not."""
        pred = '<table><tr><td>0.18</td><td>0.25</td></tr></table>'
        gold = '<table><tr><td>0.18</td><td>0.18</td></tr></table>'
        score = numeric_diagnostic(pred, gold)
        self.assertEqual(score['precision'], 0.5)
        self.assertEqual(score['recall'], 0.5)
        self.assertEqual(score['missing'], {'0.18': 1})
        self.assertEqual(numeric_diagnostic(pred, pred)['f1'], 1.0)

    def test_failed_candidate_is_not_dropped_from_denominator(self):
        """AC-VTABLE-805: report candidate failures and fallback separately."""
        pairs = [
            {'baseline': {'teds': .2}, 'candidate': {'teds': .8}, 'effective': {'teds': .8}},
            {'baseline': {'teds': .9}, 'candidate': None, 'effective': {'teds': .9}},
        ]
        result = aggregate_pairs(pairs)
        self.assertEqual(result['candidate_valid_count'], 1)
        self.assertAlmostEqual(result['candidate_teds_failed_as_zero'], .4)
        self.assertAlmostEqual(result['baseline_teds'], .55)
        self.assertAlmostEqual(result['fallback_teds'], .85)

    def test_rejected_grid_diagnostics_do_not_repair_it(self):
        """AC-VTABLE-805/806: rejected responses stay visible and auditable."""
        raw = '{"rows":2,"cols":2,"cells":[[0,0,2,1,"a",true,false],[1,0,1,1,"b",false,false],[3,1,1,1,"c",false,false]]}'
        result = inspect_response(raw)
        self.assertEqual(result['overlap_slots'], 1)
        self.assertEqual(result['uncovered_slots'], 2)
        self.assertEqual(result['out_of_bounds_cell_indices'], [2])

    def test_html_diagnostics_are_not_json_errors(self):
        result = inspect_response('<table><tr><td>0.18</td></tr></table>', 'html')
        self.assertTrue(result['html_valid'])
        self.assertEqual(result['cell_count'], 1)
        self.assertEqual(result['uncertain_cells'], [])
        self.assertFalse(inspect_response('<table>', 'html')['html_valid'])

    def test_html_diagnostics_need_no_pdf_or_model_dependencies(self):
        """AC-HTML-906: isolated evaluator must load this pure adapter without PyMuPDF."""
        import subprocess
        import sys
        from pathlib import Path
        result = subprocess.run([sys.executable, '-S', '-c',
            "from scripts.score_vlm_table_experiment import inspect_response; "
            "assert inspect_response('<table><tr><td>x</td></tr></table>', 'html')['html_valid']"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
