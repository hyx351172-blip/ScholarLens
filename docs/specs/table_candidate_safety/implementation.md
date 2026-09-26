# Table candidate safety and orientation v13

Offline Python component repair only. Preserve frozen v10/v11/v12 files and all
existing production edits. No downloads, paid calls, production rollout or commit.

## Acceptance criteria

- AC-1601: Veto previously passing candidates with at least three vertically
  aligned OCR line bands in two independent ordinary cells of one logical row.
  This is ambiguity detection, not proof of distinct records: retain baseline,
  preserve text/IDs and spans, never split on newline or synthesize rows.
- AC-1602: Normal one/two-line wrapping, wrapping in only one column, explicit
  header/rowspan cells and previously rejected candidates remain unchanged.
  Malformed provenance fails closed. Record reason, row, cells and OCR IDs.
- AC-1603: Compare four quarter-turns using local OCR evidence only (bounded
  resolution, no orientation-model download). Accept a nonzero turn only with
  enough readable horizontal text and a margin over both zero and runner-up.
  Ties, insufficient evidence or worker failure retain the original baseline.
- AC-1604: Re-run extraction on the full-resolution oriented crop; never mix old
  OCR coordinates with rotated pixels. Save forward rotation and inverse bbox
  mapping to original crop/page, with tests for all four turns and invalid input.
- AC-1605: Preserve and hash old artifacts, replay all 20 development cases and
  three older controls. Targeted fresh local inference uses case-20 (rotation),
  case-13 (record collapse), case-09 (upright formula control), frozen before
  scoring. Include all 20 in comparisons, retain failures, report model costs,
  RED/GREEN and regression results. These are NOT new held-out observations.

## Plan and limits

1. RED tests for admission, wrapping, provenance, orientation decisions and boxes.
2. New adapters only; conservative veto rather than speculative record splitting.
3. Four 1280-pixel OCR probes per targeted crop; CPU four threads, cached models.
   300-second probe / 240-second extraction subprocess limits, zero retries.
   Only a confidently nonzero turn triggers fresh Docling and Paddle extraction.
   Docling uses its existing accurate configuration and strict native export.
4. Freeze all selected outputs before separate official TEDS scoring. Do not
   choose rotations or fallback by benchmark answers. Preserve raw negative TEDS.
5. Record limitations: possible conservative multiline false rejections; OCR
   confidence is not semantic correctness; table-only crops; no RAG claim.

## Resource-bound follow-up (before any v13 gold scoring)

The full-text orientation probe timed out at 300 seconds on the rotated case;
its first direction alone detected 239 OCR lines. Preserve this complete v13
attempt, including the timeout and its baseline fallback. New v13-bounded output
uses a separate adapter: four local detection passes, at most 24 spatially
distributed horizontal text prefixes per direction, each no wider than 12 times
its height. Non-horizontal detections do not enter recognition. Selection uses
geometry only, never recognized values or gold. Thresholds/margins are unchanged.
The probe has a 240-second overall subprocess deadline and zero retries. Repeat
the same two upright controls as well. Final extraction still receives the full
resolution original crop after rotation, not the prefix samples.

Tests: three bounded-sampling regressions and three native-coordinate tests;
independent official scoring tests enforce exact HTML reuse and gate contracts.
Native Docling BOTTOMLEFT boxes are converted to TOPLEFT before inverse rotation;
missing boxes are listed rather than invented. No production coordinates change.

## Completed / review

- [x] 28 new regression tests, including actual frozen OCR/structure seams.
- [x] 345 related regression + 6 official scorer integration tests pass.
- [x] Original v13 full-text orientation timeout retained; v13-bounded uses
  24 prefixes/angle and correctly retains both upright controls.
- [x] Rotated case re-extracted at full resolution; native 143 boxes mapped.
- [x] All 20 retained; two improvements, no regressions versus v12, 18 unchanged.
  Old three-control outputs unchanged. Raw mean TEDS 0.535640 -> 0.584332.
- [x] Frozen source integrity and no-gold selection verified; traceability passes.
- [x] Scoped resilience/consistency/validation review recorded in evaluation report.

Report: `docs/evaluation/omnidocbench-table-safety-v13.md`.
Residual risk: conservative false rejections for long aligned multiline cells;
merged records are only vetoed, not reconstructed. No production/held-out claim,
no commit or push. Stop at this bounded feature for review.
