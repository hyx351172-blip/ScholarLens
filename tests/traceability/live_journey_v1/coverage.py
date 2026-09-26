"""AC map; live actions require explicit invocation, not discovery.

AC-2101: tests/test_live_journey_contract.py::test_ingestion_requires_all_stages_nonzero_matching_counts_and_pdf
         tests/integration/run_live_journey_v1.py upload/chat actual HTTP run
AC-2102: tests/test_live_journey_contract.py::test_answer_contract_rejects_missing_unknown_and_wrong_provenance
         tests/test_live_journey_contract.py::test_malformed_marker_is_not_hidden_by_valid_marker
AC-2103: tests/test_live_journey_contract.py::test_unanswerable_contract_does_not_equal_semantic_correctness
         output/e2e-v1/audit.json and original-PDF manual review; grounding failure retained
AC-2104: Browser actual flow recorded in docs/evaluation/end-to-end-live-v1.md;
         source drawer and page-8 link verified; native PDF visual rendering unverified

Traceability is coverage, NOT a claim that all live acceptance conditions passed.
"""
