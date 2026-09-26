# Table evidence fidelity and evaluator index repair

Scope: preserve recognized table structure through canonical parsing and export,
while correcting the confirmed zero-index bug in the pinned local evaluator.
No recognition model, gold annotation, retrieval setting, or stored database is changed.

## Acceptance criteria

- AC-TABLE-701: matched prediction index 0 retains its category and position;
  nonzero and unmatched predictions retain existing behavior. Save the minimal
  upstream patch and distinguish locally patched scores from original official scores.
- AC-TABLE-702: canonical table blocks retain recognized cell text, row/column
  offsets, spans, header flags and original bounding-box coordinate provenance.
  Existing Markdown text and old JSON loading remain compatible.
- AC-TABLE-703: export validated table structure as escaped HTML with spans;
  malformed/overlapping/out-of-bounds grids fall back to existing Markdown with
  an explicit warning. No guessed merge, value correction or empty-cell content.
- AC-TABLE-704: table caption bindings and chunk content/provenance stay unchanged;
  legacy and reclassified objects remain readable. Saved native Docling artifacts
  can be replayed without model inference into a separate output directory.
  The service's existing Markdown view remains Markdown-only; an additive
  `structured_markdown` export and saved `.structured.md` preserve HTML spans,
  without enabling arbitrary HTML in the frontend.
- AC-TABLE-705: rescore baseline, export-only and formula-fixed predictions with
  the same pinned patch, then compare structure-preserving export under that same
  scoring version. Preserve all historical results and record hashes and limitations.

## Plan and tasks

1. Write failing zero-index and structure-contract tests.
2. Apply and record the two-line evaluator fix; run isolated evaluator regression.
3. Add an optional structure payload, validated HTML rendering and adapter mapping.
4. Replay the frozen ten saved documents; assert unchanged text and downstream chunks.
5. Run project tests and official evaluator entry point with explicit patch provenance.

## Test routing

This is a backend/cross-module contract change. Required seams are native Docling
JSON -> canonical blocks -> Markdown export and canonical blocks -> table grouping
-> chunker. A real saved-artifact replay plus evaluator is required beyond mocked
unit tests. No DB migration, authentication or new frontend behavior is in scope.
Live upload/indexing is not implied by this offline experiment. Test routing is
guidance; executed assertions and result artifacts are the evidence.

Implementation remains in the current dirty worktree to preserve the user's
existing parser fixes. No automatic commit, merge or push is part of this task.

## Verification completed 2026-09-25

- AC-TABLE-701: RED then GREEN in `tests/test_omnidocbench_index_patch.py`;
  minimal pinned upstream patch saved and three historical variants rescored.
- AC-TABLE-702/703: `tests/test_table_structure.py` validates mapping, spans,
  escaping, saved JSON, malformed grids, empty slots and revalidation.
- AC-TABLE-704: service compatibility and chunk assertions pass; replay of all
  ten native documents preserved legacy blocks, bindings and all 49 chunks.
- AC-TABLE-705: output safety in `tests/test_replay_docling_table_export.py`;
  four patched-evaluator runs completed without matching/TEDS timeouts/errors.
- Full suite: 185 passed, zero failures/skips. No DB or live-browser test claimed.
- Review: no model/prompt/gold edits; invalid grids fall back with warnings;
  escaped structured export is separate from the HTML-disabled frontend view.
  Small TEDS improvement and structure-only regression are both reported.

See `docs/evaluation/omnidocbench-table-fidelity-v4.md` and its companion JSON.
