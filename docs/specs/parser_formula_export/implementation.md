# Parser formula/export repair

Scope: fix defects exposed by the frozen 10-page OmniDocBench smoke sample.

- AC-PARSE-601: enable local formula recognition in Docling, with an explicit opt-out; persist the setting in parser provenance.
- AC-PARSE-602: export Markdown from the same final ordered blocks used by the chunker. Include actual formula text and mark OCR-only/missing formulas honestly.
- AC-PARSE-603: normalize top-left provenance to the canonical bottom-left coordinate system before geometric sorting; missing page size must fall back safely.
- AC-PARSE-604: preserve table text, split heading levels, formula delimiters and code fences during serialization; refresh service Markdown after VLM repair.

Plan: reproduce export and configuration failures in parser tests, implement a canonical serializer and converter option, then rerun the frozen public sample and existing tests. Raw Docling JSON remains available for auditing. No changes to gold annotations or scoring logic.

Verification: `tests/test_docling_parser.py`, `tests/test_markdown_renderer.py`, `tests/test_docling_chunking_integration.py`; public comparison is recorded in the evaluation report after completion.

This is a parser/export integration change. No database migration or new UI journey is introduced. The real image-PDF to parser to Markdown to official scorer path is the required integration check.

Completed 2026-09-25: all 175 discovered tests passed, and the same frozen 10 pages completed the official evaluator. Formula Edit distance improved from 1.0000 to 0.2547; reading order improved from 0.4842 to 0.2390. Tables were unchanged. See `docs/evaluation/omnidocbench-parser-repair-v3.md` for the export-only ablation, precise scope, provenance, and remaining limitations. Live upload/indexing was not run; existing stored documents are not migrated automatically.
