# Development merge acceptance — 2026-09-26

Scope: accumulated evaluation harness/parser experiments plus answer-output and
source-display repairs on `codex/evaluation-harness`. User requested merge to main.

## Gate evidence

- Backend discovery: 404 tests passed in 21.378 seconds, no reported skips.
- Frontend: 13 tests passed, no skips; TypeScript/Vite build passed in the preceding
  repair turn (Vite 7.90s). Browser-data age warnings remain.
- Traceability: 109 declared and 109 referenced AC IDs; no orphan/ghost IDs.
- Current diff whitespace check passed; common credential-pattern scan found no
  matches. Environment files and raw run outputs remain ignored. This limited
  scan is not a security audit.
- Previously blocking malformed citations/unsupported abstention explanations
  have guard regressions and four live API-mode checks. See `answer-output-guard-v1.md`.
- Browser smoke: method, conclusion, table and abstention work. Chrome visually
  verified PDF page 8/15. See `frontend-acceptance-20260926.md`.
- The subsequent source-count and loading-text changes passed pure grouping and
  component-wiring tests plus build. They have not had another browser replay.
- HTTP response shapes retained; guard metadata is additive. Streaming now buffers
  content before emission, an intentional documented latency change. The frontend
  consumes it successfully in the preceding real browser tests.

Decision: GO for this bounded development merge, not a production readiness or
general answer-entailment claim. No new CI/hook enforcement was installed; these
are manually executed gates following ai-product-dev-pack.

## Follow-up limitations

Broader multi-paper false-refusal evaluation remains pending. Phrase-based
abstention detection can over-reject; valid source IDs do not prove entailment.
In-app PDF rendering is limited although Chrome page navigation works. Experimental
table candidates remain experiments rather than promoted production replacements.
Trailing blank-line warnings in older checkpoint additions were recorded there;
frozen experiment files were not rewritten merely to change formatting.
