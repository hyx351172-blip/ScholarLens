# Controlled merged-record reconstruction v14

Scope: one offline Python feature, using frozen v13 traces/crops, no new model or
API calls. Do not edit frozen v10–v13 modules/artifacts or production parser.
Preserve the dirty working tree; no automatic worktree/commit/push or deployment.

## Acceptance criteria

- AC-1701: Only the v13 `aligned_multiline_row_ambiguity` veto is eligible for
  repair. Other rejections and passing candidates stay byte-identical. Re-run
  validation rather than trusting a supplied suspicion. No case IDs, expected
  row counts, known dates/units, gold HTML, or filename-dependent inference.
- AC-1702: A complete atomic non-header body row needs a short numeric/unit
  anchor column with at least three aligned records, independently corroborated
  by two additional columns with repeated typed record-start patterns. All
  proposed anchors must agree on the OCR grouping. Otherwise retain the veto.
- AC-1703: Continuation lines require clear position plus indentation or preceding
  hyphenation. Ordinary paragraphs, single-column wrapping, header cells,
  spanning cells, conflicting starts, missing evidence and ties must not be
  speculatively split. This is a restricted heuristic, not semantic certainty.
- AC-1704: Every original OCR ID/text/bbox appears exactly once after repair.
  Preserve header cells, column count and unaffected spans; shift later rows
  explicitly. Strictly validate complete HTML topology and source provenance.
  OCR padding may cross inferred boundaries; central vertical evidence cores
  must be disjoint/contained, and full boxes/overlap remain auditable, not clipped.
- AC-1705: Bound input size, row expansion and malformed numeric/geometry data;
  reject atomically on failure. Persist the previous gate, anchor/continuation
  evidence, boundaries, old/new cell mapping, and per-OCR assignment reasons.
- AC-1706: RED/GREEN + real frozen OCR seam + varied synthetic positive/negative
  fixtures. Replay all 20 development cases plus old three controls and protected
  source hashes. Freeze outputs before official TEDS/aligned-cell scoring. Keep
  all failures in the denominator. No held-out, production or RAG success claim.

## Plan / test routing

1. Python unittest regression fixtures for wrapped/merged records and malformed
   traces. Main risk P1: destructive text reassignment or false row splitting.
2. Implement one additional pure postprocessor, no changes to frozen prior logic.
3. Test the real v13 capture→postprocessor→strict HTML seam and failure fallback.
4. Frozen 20-case replay; independent official scorer with byte-identical reuse
   and explicit changed-output scoring. Save diagnostic preview and report.

Single-backend + cross-module artifact contract. No DB, auth, frontend or external
API changes. No newly connected end-to-end RAG journey. Routing is advisory;
actual executed tests and artifact checks provide the evidence, not the skill.

## Completed

- [x] Restricted numeric-anchor + two-label-column reconstruction, atomic fallback.
- [x] OCR ID/text/bbox conservation, continuation evidence, explicit row offsets.
- [x] 24 feature/adapter tests including the real frozen seam and adversarial negatives.
- [x] Final related regression: 369 tests passed (including the 24 above), plus
  9 official-evaluator integration tests passed; 378 tests total, not table samples.
- [x] Frozen 20-case replay: case-13 restored to 5x3; 19 effective outputs unchanged.
- [x] Three older control traces unchanged; zero model/API calls.
- [x] Separate official score: case-13 TEDS 0.288511 -> 0.997500, structure 0.4 -> 1.0.
  Development mean TEDS 0.584332 -> 0.619781; 14/15 cells text-exact, one ellipsis mismatch.
- [x] Review and test-routing scope documented; no production or held-out claim.

Report: `docs/evaluation/omnidocbench-table-records-v14.md`.
Stop this feature for review. HTML wrappers, formula OCR and independent held-out
validation remain separate work; no automatic commit/push/production promotion.
