# Table specialist comparison v7

## Scope

Execute the first step of the approved optimization plan: compare PP-TableMagic
(PaddleOCR TableRecognitionPipelineV2, CPU) and Qwen native `table_parsing` against
the frozen v4 Docling baseline and the already completed v6 HTML experiments.
This is a development experiment, not a production parser change. Two selected
pages are electronic datasheets; only one is a scientific benchmark table.

## Acceptance criteria

- AC-1001: Independent, pinned Paddle environment; production requirements
  and parsers are unchanged. Disable layout/orientation/unwarping for frozen crops.
  Preserve pipeline JSON and use exactly one table result, never gold-guided selection.
- AC-1002: Native DashScope request uses only the image and built-in
  `ocr_options.task=table_parsing`, with no custom prompt or gold. Only recognized
  official HTTPS origins can receive the local key. No redirects/retries; independent
  connect/read/write/pool limits plus total deadline and bounded response size.
- AC-1003: Validate all crop/baseline hashes before inference; journal every
  attempt before invoking the client, maximum three calls per arm. Output paths must
  be fresh and outside inputs. Persist failures/partial text and stop on auth errors.
- AC-1004: Apply the existing strict HTML-to-cell contract without repairing
  gaps, guessing numbers or consulting gold. Invalid/incomplete results retain baseline.
- AC-1005: Run actual model/API seams when available and the unchanged official
  TEDS evaluator. Report validity, TEDS, structural TEDS, numeric multiset diagnostic,
  latency, usage and limitations. Do not equate valid syntax with semantic correctness.
- AC-1006: New regression tests cover request contracts, native HTTP/SSE,
  incomplete/error streams, limits, credential redaction, path/hash safety, raw Paddle
  result normalization, and failure fallback. Preserve old results and source artifacts.

## Implementation order / test routing

1. RED tests for native endpoint/payload/stream and single-arm runner.
2. GREEN offline runner and two adapters; isolated pinned Paddle environment.
3. Real runs (3 local crops + at most 3 native paid API attempts); separate gold scorer.
4. Targeted and related regressions, self-review, report and reproducible commands.

CLI-only feature: backend unit/contract + real transport + offline model/evaluator
slice tests. No frontend, database, migration or application E2E change. Do not commit,
push, auto-deploy, download more datasets, or implement other research proposals here.

## Sources

- https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/table_recognition_v2.html
- https://help.aliyun.com/zh/model-studio/qwen-vl-ocr-api-reference

## Tasks

- [x] Tests and adapters
- [x] Isolated environment and real inference
- [x] Official paired scoring and report
- [x] Regression tests and integrity checks

## Validation / decision

14 new tests; complete suite 227 passed, no failures/errors/skips (24.890 s).
The 14 tests also pass in the isolated Paddle environment. Official scorer tests
were rerun after changing report labels (6 passed). Six ACs pass the traceability
gate. All 15 frozen input/baseline file hashes match.

Native task: 3 complete API responses, 18,064 tokens, 0/3 schema-valid outputs.
Paddle: initial Windows Unicode model-path error preserved, fixed by a relative
ASCII cache path and Python image decoding; 3 real CPU inferences completed,
0/3 schema-valid outputs. No request timeouts or new paid retries.
Each scoring run reproduces v4 baseline. No model passes the conservative smoke
gate; no production replacement or held-out expansion. A 500-token model setting
and approximately 501 structural tokens on two malformed outputs suggest a length
ceiling to investigate, not an established universal root cause.

See `docs/evaluation/omnidocbench-table-specialist-v7.md` for evidence, timings,
limitations, paths and next steps. Remaining research proposals are not implemented.
