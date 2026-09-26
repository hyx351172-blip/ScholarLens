import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from finalize_unseen_table_outputs import metadata_only_failure, export_baseline, package_versions


class FinalizeTests(unittest.TestCase):
    def test_recover_only_exact_version_reporting_failure(self):
        r = {'status': 'failed', 'error_type': 'PackageNotFoundError',
             'error': 'No package metadata was found for docling'}
        self.assertTrue(metadata_only_failure(r))
        self.assertFalse(metadata_only_failure(dict(r, error_type='RuntimeError')))
        self.assertFalse(metadata_only_failure(dict(r, error='No package metadata was found for torch')))
        self.assertFalse(metadata_only_failure({'status': 'timeout'}))

    def test_missing_distribution_is_information_not_parse_failure(self):
        self.assertIn('docling-slim', package_versions())

    def test_no_native_table_cannot_be_recovered(self):
        raw, info = export_baseline({'tables': []})
        self.assertIsNone(raw)
        self.assertEqual(info['status'], 'no_table')

    def test_original_native_cells_exported(self):
        cell = {'text': 'A', 'start_row_offset_idx': 0, 'end_row_offset_idx': 1,
                'start_col_offset_idx': 0, 'end_col_offset_idx': 1, 'row_span': 1, 'col_span': 1}
        raw = {'tables': [{'data': {'num_rows': 1, 'num_cols': 1, 'table_cells': [cell]}}]}
        result, info = export_baseline(raw)
        self.assertIn('A', result)
        self.assertEqual(info['selected_table'], 0)


if __name__ == '__main__': unittest.main()
