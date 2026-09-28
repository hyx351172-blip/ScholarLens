# Frozen multi-paper answer / citation semantic audit

Scope: reuse the 16 frozen document-scope replay answers, not regenerate answers,
modify generation/retrieval, re-upload PDFs, consume held-out sets, or commit/push.
Continue in the existing isolated evaluation workspace to preserve earlier changes.

- AC-3001: Freeze input and evaluator hashes. Validate question identity, response success, and ordered source IDs before judging. Preserve existing outputs and stop on a changed input or uncertain previous attempt.
- AC-3002: Judge each existing sentence/composite claim unit against only its own cited snippets. Retain non-citation bracket tokens such as MASK in the evaluated claim. No valid citation means no support. A composite is supported only when all its assertions are supported; an uncited snippet cannot rescue it.
- AC-3003: Keep exact fixed refusals outside the factual-claim denominator; report refusal correctness separately from semantic support. Failed/missing judgments cannot be counted as passes or silently dropped from coverage. No atomic-claim or human-Gold accuracy claim.
- AC-3004: Run at most 12 provider requests with retries disabled; save raw judge text, validated decisions, usage, and latency without credentials. Preserve invalid/failed outputs; do not regenerate a nicer result. Produce a reviewable evidence bundle and aggregate report.

Plan: frozen-artifact adapter and regression fixtures (RED/GREEN) -> prepare and
inspect bundles -> one bounded live evaluation -> AI review of disputed examples
-> full tests / traceability / limitations report. AI decisions remain provisional;
human review status starts pending. No application API schema changes.
