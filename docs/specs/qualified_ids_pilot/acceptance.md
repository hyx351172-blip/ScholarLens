# v3 evidence-ID targeted pilot

Run only the ten explicitly listed frozen v3 packets (six SciFact, four regression)
with fresh approval. This is a diagnostic selection, NOT random held-out data.
Do not alter production, prompts, semantic rules, Gold or frozen history.

- AC-4801: Verify frozen v3 preparation, copy ten unchanged requests in fixed diagnostic order, and save selection reasons and separate labels. Never inherit the preparation's 52-call proposal as approval.
- AC-4802: Require explicit ten-call authorization before credentials. Enforce qwen3-vl-plus HTTPS allowlist, max_tokens 1500, zero retries, sequential calls and 60-second deadlines. Exclusive run/attempt records prevent duplicate spending; stop at first error and never automatically resume.
- AC-4803: Parse actual complete model responses directly with v3, never adapt old quotes or simulated responses. Preserve raw output, parser/request identity, refusal/truncation, usage and failure stage; redact credential echoes and fail closed.
- AC-4804: Reparse saved raw results for reporting; separate invalid, uncertain and missing outcomes. Compare SciFact only on these six keys with v1; report regression transitions with no semantic accuracy or human Gold. No pooled, full-52 or official benchmark score.
- AC-4805: Cached summaries, inputs, code, per-attempt records and aggregate results must agree. Incomplete/failed batches are terminal; cached verification makes no new requests. Preparation and tests never require credentials or network.
- AC-4806: RED/GREEN and full regression precede freezing. Save write-once artifacts, coverage, cost tokens, latency and truthful partial/full completion report. Do not claim semantic improvement from contract success or change production defaults.

Tasks: test missing runner (RED); implement isolated pilot; verify fault injection,
limits and score arithmetic; run full suite; freeze; execute only with fresh
approval; inspect sources offline and publish bounded results.
