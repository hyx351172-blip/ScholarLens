# Selected-claim support live review v1

Scope: review the 22 frozen claims from selected-claim-support-v1 exactly once,
using their selected spans only. Two negative controls are local, zero-call.
This is a development judge calibration, not new generation or human Gold.

- AC-4001: Verify all source/artifact hashes and replay the saved packet contract before preparing 22 write-once requests. Preserve original answers, selected evidence, labels, code and all historical experiments; no labels or sibling evidence in judge requests.
- AC-4002: Explicit 22-call approval and an exact frozen protocol are required. Only the configured Aliyun qwen3-vl-plus endpoint may be used, at temperature 0, max_tokens 1000, SDK retries 0 and a 60-second outer deadline. Read credentials only after preflight and never include them in artifacts.
- AC-4003: Use exclusive run and per-claim attempt journals before calls. A completed/error run is read-only on re-entry; an unresolved attempt or interrupted run blocks automatic resume. Concurrent invocations, drift and unexpected result files fail closed without new spending.
- AC-4004: Capture raw output, usage, finish reason and elapsed time; use the existing selected-claim parser. Refusal, truncation, provider errors or invalid decisions stop the batch without retry. Errors remain in the 22-claim denominator; unreviewed and unknown usage are explicit, not zero or success.
- AC-4005: Replay the original conservative gate using only valid reviews, export individual human-review cards with null judgments, and summarize model opinions separately from AI draft notes. No invented semantic accuracy, automatic answer repair, service rollout or default activation.
- AC-4006: Safety and contract tests, full offline regression, traceability, historical integrity and secret-pattern checks pass. No database/service/frontend mutations and no automatic Git publication.

Plan: RED adapter/journal tests → bounded runner → GREEN → freeze requests →
authorized serial run → inspect verdicts against exact selected spans → report.
Stop after this experiment, including on error; no automatic retuning or rerun.
