# Qualified claim support v2 — authorized paired experiment

Run the already frozen 30 SciFact and 22 selected-claim packets once with the
approved v2 requests. Reuse every v1 response. Do not change prompts, samples,
labels, evidence, production services or Git publication state.

- AC-4401: Freeze the runner and exact 52 prepared request bodies separately. Verify historical hashes and ordered identities; labels and review notes remain local, outside all requests.
- AC-4402: Require explicit approval for exactly 52 maximum calls before reading credentials. Use the validated Aliyun endpoint/model, 1,500 output tokens, temperature zero, zero retries, serial execution and a 60-second per-call deadline.
- AC-4403: Persist an exclusive run marker and attempt before sending each request. Stop on the first API, truncation, refusal or contract error; never retry or resume an interrupted run. Concurrent invocations and cached runs cannot double spend.
- AC-4404: Save raw responses, finish reasons, token usage and elapsed times; validate the v2 contract without repairing responses. Redact any credential echo and exclude it from successful results. Reparse raw output for scoring rather than trusting cached decisions.
- AC-4405: Score only the fixed 30 SciFact labels, including errors, uncertainty and missing cases in full denominators. Compare against saved v1 results without new v1 calls. Report the other 22 as verdict transitions with null accuracy and null human judgments, never as pooled semantic accuracy.
- AC-4406: Preserve write-once artifacts, review cards and deterministic cache replay. Pass RED/GREEN budget/error/concurrency/scoring tests, full regression, traceability and history checks. Report partial runs honestly; no production rollout from this experiment.

Sequence: contract tests → bounded runner → regression → freeze → one approved
live run → local comparison/review/report. No prompt tuning during the run.
