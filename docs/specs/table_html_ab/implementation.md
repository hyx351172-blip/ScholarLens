# HTML table transcription A/B v6

2026-09-25. Status: implementation and validation complete. Model smoke gate failed;
no production integration or held-out expansion. Offline only.

## Scope and design

The agreed follow-up is a paired experiment on the same three predicted table crops:
`qwen3-vl-plus` + HTML vs. `qwen3.5-ocr` + HTML, compared with frozen Docling v4.
Model-list preflight confirmed both available on the configured endpoint. This does
not prove invocation permission or quality. No production parser, chunker, DB,
frontend, existing artifacts or credentials are modified. No commit/push.

The same prompt, original crop bytes, temperature=0, max_tokens=8192 and streaming
protocol are used in both arms. Only the generic model receives enable_thinking=false;
the OCR task has no thinking option. No JSON response constraint. Gold is scoring-only.
Keep the old JSON experiment as historical context, not a controlled format ablation:
its stream/timeout/prompt/token settings differ too.

## Acceptance criteria

- AC-HTML-901: Strictly parse a single complete HTML table into the existing cells
  contract. Compute indices from physical row order and spans; preserve explicit
  blanks and unknown markers. Reject malformed/nested/multiple tables, excessive
  spans/grid sizes, overlaps, row overflows and holes. Do not guess missing cells.
- AC-HTML-902: Reject executable/linked markup, strip safe presentation attributes,
  render only escaped canonical cells. Do not enable raw model HTML in the frontend.
- AC-HTML-903: Stream with separate connect/read/write/pool limits plus an independent
  async total deadline. Record time to first event/text, largest gaps, completion
  time, usage, finish_reason and partial text on error. Explicitly close streams.
  Incomplete, truncated, refused or timed-out output cannot become a valid candidate.
- AC-HTML-904: Maximum six sequential requests for the three-page smoke run, no SDK
  retry, persistent attempted journal before network, fresh outputs only, verify
  input hashes and paths. Stop an arm on authentication/model-availability errors;
  skipped/failed cases stay in the denominator. Never print credentials or raw errors.
- AC-HTML-905: Each arm preserves original responses and candidates separately; only
  syntactic validation controls offline fallback. Score with pinned official TEDS,
  structure-only, numeric token diagnostics, per-table regressions and latency.
  No gold-based best-of selection or claim that schema validity proves accuracy.
- AC-HTML-906: Save a joint report with reproducible settings, source hashes, all
  failures, costs/usage uncertainty and baseline comparison. Add real local SSE
  transport and HTML round-trip tests beyond mocks; do not claim DB/UI coverage.

## Tasks / routing

1. RED tests for deterministic HTML geometry and hostile/truncated markup.
2. Implement a separate converter reused only by offline experiments.
3. RED streaming/deadline, partial capture, budget, integrity and SDK-contract tests.
4. Implement a bounded two-arm runner, using existing v5 prepared crop artifacts.
5. GREEN tests; run at most six requests. Score each arm and generate joint report.
6. Review all failures and normal-table regressions. Expand to fresh held-out pages
   only after the smoke pipeline is viable; do not silently launch large paid runs.

Existing uncommitted parser/evaluation work is retained in the current checkout.
Test routing is guidance, not proof: backend unit tests, script slices, real local
SSE transport, live six-request seam and actual scorer outputs are separate evidence.

## Validation record

- RED module-not-found tests preceded converter, streaming runner and summary implementation.
- AC-HTML-901/902: 4 converter tests; spans, empty cells, safe rendering, hostile/malformed markup.
- AC-HTML-903/904/906: 9 runner tests including SDK timeout wiring, total deadline,
  usage-only stream events, real local HTTP/SSE, partial output, redaction, auth stop,
  pre-call journal, budgets, immutable hashes and duplicate cases.
- AC-HTML-905/906: 2 additional scorer tests (HTML diagnostics and a pure stdlib
  subprocess without PDF dependencies), plus 2 joined-report tests for regression,
  missing usage and mismatched provenance. Existing v5 tests still pass.
- Full suite: 213 passed, 0 failures/skips; 18.945 seconds.
- Live experiment: 6/6 complete API responses, 1/3 valid generic candidates, 0/3 OCR.
  Valid generic control TEDS 0.959662 → 1.0; complex table failed in both arms.
- Both arms rescored with pinned official metrics; every baseline matches v4.
  A scoring import error was fixed locally and rescored, without new paid calls.
- The conservative expansion gate requires at least one arm with all three valid
  candidates and no TEDS regression. It failed; no additional paid data requested.
- See `docs/evaluation/omnidocbench-table-html-v6.md` for exact results, limitations,
  token accounting, artifact links and reproduction. No production writes or commit/push.
