# OCR binding and content evaluation v9

Continue v8 with one offline feature: reconnect the extended structure model to
PP-TableMagic's cell detection, text splitting and matching, and audit content by
cell coordinates. No production parser, dependency, DB or UI changes. No paid API,
new downloads, commits or pushes. Keep the dirty workspace and all prior evidence.

## Acceptance criteria

- AC-1201: Frozen crops, v7 cached whole-table OCR and v8 model clones must have
  matching provenance/hashes. Only the two v8 strict-valid structures are processed;
  the invalid control remains in the three-case denominator as baseline fallback.
  Reuse whole-table OCR; locally re-recognize text only where the existing pipeline
  splits boxes by the newly detected cells. Gold is not accessible to inference.
- AC-1202: Preserve raw detection/matching/renderer inputs and full HTML. Require
  identical v8 structure before binding. Preserve OCR IDs, boxes, text, logical
  row/column/spans and matched geometry IDs in a trace. Audit duplicated, unassigned,
  low-overlap and geometry/structure count mismatches; don't infer correctness from
  syntactically valid HTML or silently shift cells to fill holes.
- AC-1203: Fresh output outside inputs/cache; verify all inputs before and after;
  at most two CPU workers, 600 seconds each, no retries or network models. Retain
  errors/partial evidence, strict HTML fallback, text escaping and no tag repair.
- AC-1204: Separate official full TEDS / structure TEDS scoring, reproducing v4.
  Add exact-span-coordinate cell text and numeric diagnostics (including missing
  cells); report explicit header/first-column/unit-bearing subsets where available.
  Swapped numeric values must fail coordinate scoring even if global bags agree.
  Valid but regressing candidates remain visible; never choose using gold.
- AC-1205: RED/GREEN contract and failure tests, real local model/OCR/matcher and
  evaluator seams, immutable evidence checks, complete regression, traceability
  and report with limits. No downstream RAG or production acceptance claimed.

## Tasks / test routing

1. Tests for binding index semantics, safety, spans, duplicate/lost OCR, aligned metrics.
2. Instrumented bounded runner using unchanged installed Paddle functions, scoped
   in-process wrappers (no edits to packages), and pure trace/metric adapters.
3. Two real full binding runs and a separate gold-only scoring pass.
4. Review, regressions, integrity and report. Any renderer/matcher errors remain
   errors, not automatically repaired in this experiment.

This newly connects structure → physical cells → OCR → HTML in the local offline
slice; it does not connect an application/user journey. Unit/contract plus actual
model/evaluator slice tests are required; UI/DB/HTTP testing is not in scope.
Traceability is an executed local gate, not a claim of configured CI enforcement.

## Completed tasks and decision

- [x] 25 new unit/contract tests; 270 total passed; 19 pure tests also pass in Paddle venv.
- [x] Two real local binding runs, preserving raw matcher/render inputs and v8 structures.
- [x] Official full/structure TEDS and cell-coordinate diagnostics; baseline reproduced.
- [x] Terminal-boundary behavior reproduced; trace supports diagnosis without changing
  matcher semantics, while the independent integrity gate rejects it.
- [x] Label-anchor scoring-only complement exposes sensitivity to header-row shifts;
  exact unique matching, explicit coverage, no fuzzy matching or column reordering.
- [x] All 38 protected artifacts/models and 15 frozen input artifacts unchanged.
- [x] Review, traceability and report at `docs/evaluation/omnidocbench-table-ocr-binding-v9.md`.

Neither candidate passes the conservative integrity gate. One raw full TEDS improves,
one regresses substantially; effective baseline is unchanged. Final OCR text/boxes
equal cached v7 OCR, so this run validates reuse/binding, not new OCR recognition.
Explicit header/unit validation remains unavailable for the processed cases.
No commit/push/deployment or production promotion; physical-to-logical grid mapping
is the next separate feature.
