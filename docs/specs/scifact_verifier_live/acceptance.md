# SciFact verifier live v1

Scope: execute the already frozen 30 SciFact dev requests once after the user's
2026-09-27 approval. No new sampling, answer generation, retrieval, prompt tuning
or changes to the frozen offline adapter. Stop after this experiment.

- AC-4201: Verify the offline dataset, all historical/source hashes and exact 30 requests before preparing write-once live artifacts. Never include gold labels/rationales in requests. Freeze new runner/tests/spec/trace files separately without modifying the old manifest.
- AC-4202: Require explicit approval and an exact 30-call ceiling before loading credentials. Use the existing configured Aliyun qwen3-vl-plus client, temperature 0, max_tokens 1000, zero retries, 60-second outer deadline. Preserve the previously approved request bodies.
- AC-4203: Exclusive persistent run and per-call journals precede provider calls. Interrupted/orphan/drifted runs cannot automatically resume; completed/error runs only replay saved verified artifacts, without initializing a client. Concurrent invocations cannot double-spend.
- AC-4204: Reuse strict packet-bound response parsing; truncation/refusal/invalid output/provider errors stop the batch without retry. Preserve raw output, latency, usage and finish reason, redact credentials, and never invent token usage. Missing/error cases remain in the 30-case denominator.
- AC-4205: Apply the frozen offline scorer without label changes. Export metrics, all raw results and review cards with gold rationale text available only locally, null human judgments, and explicit smoke/dev/non-RAG limitations. No second model judge or automatic answer repair.
- AC-4206: Offline failure-injection tests, full regression and AC traceability pass; verify historical integrity after the run and produce an evidence-backed report. No production default changes, DB mutations, automatic commits or pushes.

Plan: RED bounded-run tests → GREEN runner → freeze → one authorized serial run
→ deterministic scoring → review disagreement cases → report. Any further model
calls, retries, re-sampling or follow-up experiment require new authorization.
