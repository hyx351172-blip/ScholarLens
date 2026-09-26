# Frozen unseen-page table evaluation v12

Offline evaluation only, retaining the dirty checkout and all prior experiments.
No production edits, model downloads, paid API calls, annotation edits or commits.

## Acceptance criteria

- AC-1501: Select 20 distinct previously unused pages deterministically, stratified
  by metadata subset, at most one table/page. Exclude the union of prior selected
  annotations. Selection uses category, bbox and metadata, never gold HTML/text.
  Save crop/manifest hashes and scoring-only gold separately; crop padding is 12 px.
- AC-1502: Freeze v8 extended model clones and v10/v11 algorithm hashes before
  inference. Run fresh local OCR and structure recognition with the existing
  four-thread CPU configuration. Compare with accurate Docling + EasyOCR on the
  same losslessly wrapped crop PDF; no formula enrichment, no downloads.
- AC-1503: Instrument only child processes. Enforce 240-second per-case timeout,
  zero retries, fresh output directories and input integrity. Largest-area native
  Docling table is the predeclared baseline selection rule; multiple tables remain
  in raw output. Paddle requires exactly one table. Strict invalid or rejected
  v11 output retains baseline, even if a rejected raw candidate scores better.
- AC-1504: Score only after output freezing, using official normalized TEDS and
  structure TEDS. All 20 cases remain in denominator, including failures. Record
  accepted/regressed/improved counts, raw diagnostics, gate reasons, cell errors,
  per-case latency and separate scoring errors. Never select output using gold.
- AC-1505: RED/GREEN boundary tests, actual 20-case local runs, read-only frozen
  algorithm regression, traceability and report with reproducible artifacts.
  This is oracle-crop, page-held-out component testing, not paper-disjoint testing
  or full-page/production RAG evaluation. Public training overlap is unknown.

## Plan

1. Test metadata selection, exclusion, no-gold inference manifest, baseline selection,
   gate/fallback decision and denominator policy before implementing the adapter.
2. Freeze inputs and create new v12 artifacts. Run separate bounded subprocesses
   per case; run the two independent arms concurrently on 16 logical CPU threads.
3. Replay frozen v11 geometry/header rules without adjustment. Freeze outputs,
   then run separate offline scoring (two independent scoring workers, 300 seconds
   per case; scoring failures withhold the aggregate, not masquerade as model zeros).
   Inspect new failures without retuning.
4. Review isolation, failure handling, provenance, denominator, regression and report.
   Downstream question answering remains a separate experiment, not inferred from TEDS.

## Adapter-only incident (before gold scoring)

The installed distribution is `docling-slim`, not `docling`. Conversion completed
and native JSON was saved, but optional package-version reporting raised
`PackageNotFoundError` before HTML export. Keep the frozen worker/source/results
unchanged. `finalize_unseen_table_outputs.py` recovers only that exact reporting
error by applying the predeclared largest-area/native-cell export to saved JSON.
All other failures/timeouts remain failures; no model calls or case retries.
Record both original status and export status, and test the narrow recovery guard.

## Completed / review outcome

- [x] Metadata-only deterministic selection and exclusion; 20 distinct new pages.
- [x] Frozen 120 input hashes, fresh 20 + 20 local inference attempts, no paid APIs.
- [x] Immutable native artifacts recovered through the exact version-metadata error
  guard; 17 baseline tables, 3 no-table; Paddle 18 completed, 2 timed out.
- [x] Frozen v11 replay: 2 existing-v10 successes, 18 fallbacks, 0 new header repairs.
- [x] Official scoring 20/20, 1 improvement and 1 regression; original values kept.
  One negative TEDS independently reproduced and documented, no silent clipping.
- [x] 317 regression/unit + 3 real scorer integration tests pass; traceability passes.
- [x] Review: no gold-based admission, no hidden failure exclusion, exact output/gate
  validation, safe HTML previews and bounded workers. Remaining algorithm weaknesses
  are evaluation findings, not silently fixed on held-out results.
- [x] Report: `docs/evaluation/omnidocbench-table-unseen-v12.md`.

No production integration, downstream RAG claim, commit or push. Reuse of this cohort
for subsequent tuning makes it development/regression data, not a fresh held-out test.
