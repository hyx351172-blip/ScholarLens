# Historical parser acceptance: canonical-definition index

This is a traceability routing index, not a new feature or a redefinition of old
requirements. The definitions remain in [PDF parsing design, section 8.1](../../technical/PDF_PARSING_DESIGN.md).
It fixes the previous `docs/specs` scan omitting IDs referenced by existing tests.

- AC-101: Canonical definition in the linked design: saved parser artifacts for the original four-paper experiment. Unit coverage: `tests/test_docling_parser.py::test_save_writes_parse_artifacts_but_never_chunks`. The fixture test does not rerun four real papers.
- AC-102: Canonical definition in the linked design: original 71-page metadata observation. Unit coverage: Docling metadata/identity fixtures in `tests/test_docling_parser.py`; 71/71 remains a historical measurement, not inferred from unit success.
- AC-103: Canonical definition in the linked design: page/BBox provenance coverage. Unit coverage: the same metadata/page-provenance fixture. Original all-page coverage remains a separate historical observation.
- AC-104: Canonical definition in the linked design: parse-only artifacts do not include `chunks.json`. Unit coverage: `save_parse_result` persistence fixture. This describes the parser helper/early stage, NOT today's upload pipeline, which now creates structured chunks.
- AC-105: Canonical definition in the linked design: independent physical tables, logical bindings and Figure-caption reclassification. Unit coverage: table structure fixtures in `tests/test_docling_parser.py` and `tests/test_table_postprocessor.py`.

No historical metric, Gold label or frozen source fingerprint is edited here.
Do not treat a traceability pass as proof of the original data metrics or
complete production acceptance. Other historical parser criteria retain their
existing technical-design/spec/test entries.
