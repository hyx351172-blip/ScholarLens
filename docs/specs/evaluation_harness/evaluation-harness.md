# Evaluation Harness

## Goal

Provide one reproducible entry point for ScholarLens evaluation so parser,
retrieval, answer-citation and entailment experiments produce comparable run
artifacts instead of disconnected ad-hoc reports.

## Acceptance criteria

- **AC-501.1** — A versioned JSON configuration can declare replay or command
  stages, metrics, quality gates, required environment variables and service
  health checks; invalid or duplicate declarations fail before execution.
- **AC-501.2** — Every run writes an immutable directory containing a sanitized
  config snapshot, copied/generated evaluator artifacts, stage logs, `run.json`
  and a human-readable Markdown report without serializing secret values.
- **AC-501.3** — The runner normalizes heterogeneous evaluator results into
  PASS/FAIL/ERROR, returns a non-zero process exit for failed gates or runtime
  errors, and treats explicitly allowed evaluator exit codes as quality results
  rather than infrastructure failures.
- **AC-501.4** — Two completed runs with matching stage/metric identifiers can
  be compared with direction-aware deltas that identify improvements,
  regressions and unchanged metrics.
- **AC-501.5** — `python -m harness` exposes validate, run, report and compare
  commands; a zero-cost replay configuration passes locally and a documented
  live configuration can run the existing ScholarLens evaluators without
  rewriting their metric logic.

## Compatibility

The Harness is an additive orchestration layer. Existing evaluator scripts,
datasets, JSON result contracts and application services remain unchanged.

## Out of scope

- Replacing the existing evaluator implementations or their human-reviewed
  Gold datasets.
- Automatically running paid model evaluations in tests or CI.
- Adding a browser dashboard or distributed job queue in the MVP.

