# Target-grounded retrieval test coverage

- `tests/test_multi_query_retrieval.py::TargetFilenameResolutionTests`
  covers **AC-201.1**.
- `tests/test_kb_chat_multi_query.py::test_resolved_targets_are_pushed_down_as_filename_filters`
  covers **AC-201.2** and **AC-201.4**.
- `tests/test_kb_chat_multi_query.py::test_catalog_failure_preserves_unfiltered_retrieval`
  covers **AC-201.3**.
- `tests/test_paper_target_resolution_dataset.py` and
  `scripts/evaluate_target_grounded_retrieval.py` cover **AC-201.5**.
