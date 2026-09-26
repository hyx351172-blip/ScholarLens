# Upstream table diagnosis and lossless wrapper adapter v16

One offline feature: identify failure seams on frozen v15 captures, with one
bounded syntax repair. Do not modify frozen parsers/models/thresholds or production.
Dirty experimental dependencies require this checkout; no automatic worktree,
commit, merge, API call, inference or deployment.

- AC-1901: Valid strict HTML remains byte-identical. A single orphan closing
  tbody immediately after a complete final row and before table close may be
  removed only when no row-group tags otherwise occur and strict validation
  then succeeds. Preserve all other bytes and audit the exact edit.
- AC-1902: Reject missing cell/row closes, duplicate wrappers, scripts, unsafe
  attributes, incomplete grids and excessive input. Do not use browser healing
  or fabricate text/rows. Syntax validity is not candidate admission.
- AC-1903: Persist expected/observed axes, stability, detector counts, original
  OCR and ambiguity evidence without changing capture or frozen effective output.
  Diagnostics distinguish under/over-segmentation from exact agreement.
- AC-1904: The real previously rejected source must pass wrapper parsing but
  retain rejection if any OCR is ambiguous; old strict parser still rejects it.
- AC-1905: Fresh output only, hash-check frozen v15 inputs before/after replay,
  preserve every case, and emit source-linked overlay reports without gold.

Plan: RED unit/seam tests -> new standalone adapter/audit -> GREEN -> 12-case
frozen replay plus previous valid/invalid HTML regression -> source-image review.
P1 risks: silently changing semantics or using syntax repair to bypass geometry.
No DB/frontend contract changes; no new RAG journey or E2E/CI gate.

Review: bounds and escaping; mutation resistance; fallback unchanged; honest
coverage and costs. General grid repair and cell-specific OCR stay separate work.

## Completed

- One orphan tbody repaired without altering other bytes; strict downstream OCR
  guard still rejects the five real cross-column lines. 11 other inputs unchanged.
- 12 overlays and diagnostics; 300 top-k verified from both cached detector graphs.
- 125 related tests passed (12 new); legacy 20-case cohort retains 2 prior timeouts.
- All 12 final artifacts retain v15 byte identity/existence; no metric uplift.
- Five AC references aligned; zero model/API calls, no production promotion.
- Report: docs/evaluation/omnidocbench-table-geometry-audit-v16.md.
