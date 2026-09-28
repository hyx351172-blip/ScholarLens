# Sentence evidence live follow-up v1

Scope: six frozen development cases, candidate-only generation; not paired A/B,
held-out, live retrieval or a deployment gate. Historical answers stay historical.

- AC-3801: Select B01/L01/L03/X02/A04/E01 only, preserving question, source order and text. Freeze actual sentence_v2 production request packets and code before any paid call. Labels/review notes never enter inference.
- AC-3802: Require explicit approval for at most five calls. E01 is local-only. Every call has an exclusive attempt journal, max_tokens=2000, temperature=0, zero retry and 60s SDK / 90s total deadline. Reject protocol/input/code drift and unresolved attempts; never overwrite results or repeat a completed case.
- AC-3803: Call the existing shared production dispatcher using sentence_v2 and the validated configured Aliyun qwen3-vl-plus endpoint. Capture raw response, finish reason, usage, timing, guard and exact binding. Stop on provider/transport error, sanitize exceptions, and never persist the key.
- AC-3804: Retain invalid/truncated/error responses and all six denominators. Report unknown usage separately, not as measured zero. Genuine empty inputs use zero calls; do not retry semantic/format failures.
- AC-3805: Export claim-by-claim review cards with only each claim's explicitly selected exact source spans. Keep human judgments null, semantic_verified=false, and historical comparisons labeled noncontemporaneous. No paid judge or invented semantic score.
- AC-3806: Prepare/run/write-once behavior and safety gates have automated tests; full offline regression and traceability pass. Preserve all prior artifact hashes, defaults, DB, frontend and service state; no automatic commit/push/merge.

Plan: RED safety/dispatch tests → bounded experiment runner → GREEN → prepare
and verify → wait for five-call authorization → single serial run → inspect
claims and publish evidence-bounded report. Stop after this experiment.
