"""Acceptance-to-executed-test map.

AC-2001: tests/test_table_cell_ocr_reread.py::test_geometry_selection
         tests/test_table_cell_ocr_reread.py::test_ineligible_noop
AC-2002: tests/test_table_cell_ocr_reread.py::test_replacement_provenance_no_duplicates_no_mutation
AC-2003: tests/test_table_cell_ocr_reread.py::test_bad_rereads_fail_closed
         tests/test_table_cell_ocr_reread.py::test_valid_synthetic_reread_can_pass_existing_guards
AC-2004: tests/test_table_cell_ocr_reread.py::test_existing_output_refused_before_models
         tests/test_table_cell_ocr_reread.py::test_real_frozen_run_rejects_low_confidence_and_retains_all_fallbacks
AC-2005: tests/test_table_cell_ocr_reread.py::test_diagnostic_keeps_low_confidence_without_altering_unselected_cells
         scripts/score_cell_ocr_reread.py and scripts/audit_cell_ocr_text.py actual official scoring.
"""
