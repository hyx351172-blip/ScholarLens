# Frozen new-page record validation v15

Scope: offline verification of the frozen v14 record postprocessor, not new
repair rules, deployment, or a full RAG evaluation. Existing dirty changes remain.

- AC-1801: Exclude prior prepared manifests and selected annotation pages before
  deterministic selection. Keep all selected cases, including failures.
- AC-1802: Require fresh output directories; preserve prior experiments.
- AC-1803: Both arms share the same parsed input and baseline; rejected repairs
  cannot change the effective fallback and missing results cannot disappear.
- AC-1804: Metadata compatibility may map only missing `docling` distribution
  metadata to installed `docling-slim`; never mask other package errors.

Frozen prospective cohort: 12 pages from the 18 remaining table-containing pages
in the downloaded 100-page subset; exclude 30 previously used pages. Uses oracle
table crops, frozen v12 selection ranking and no outcome-based replacement.
New-page independence is not proof of document or model-training disjointness.

Local CPU Docling and Paddle parsers, no paid calls. Docling uses an explicit
metadata-only compatibility adapter after the first attempt failed on installed
distribution naming. The failed attempt is retained, not silently reclassified.
No orientation correction is added: compare guard-v13 versus guard-v13+record-v14
under the same pipeline, not the full earlier orientation experiment.

Test routing: Python backend/artifact contract. No database, frontend or newly
connected user journey; no new E2E or CI gate. Main P1 risk is false record
splitting. Passing generic regressions or bypassing the repair is not evidence
of successful positive-case generalization. Gold is used for crops/score only,
not repair admission. Visual labels are assistant drafts, pending human review.

Deliver model traces, frozen score inputs, baseline/candidate HTML, unchanged
rule hashes, coverage limitations and next action. Stop before production use.

## Completed / acceptance decision

- 12 fixed new pages, no exact image overlap with 30 prior pages.
- Both local model arms finished: 12 Paddle candidates, 11 available Docling
  fallbacks and one no-table result. Original metadata failures preserved.
- All 12 candidates rejected upstream; 0 eligible repairs, 0 reconstructions,
  0 effective changes. Full TEDS 0.681440 and structural TEDS 0.846821 in both arms.
- 29 related tests passed (5 new protocol tests), 4 AC references aligned.
- Protocol execution complete; **positive/negative repair coverage not achieved**.
  No production promotion, no statistical false-split/generalization claim.
- Report: docs/evaluation/omnidocbench-table-records-validation-v15.md.
