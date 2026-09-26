# ScholarLens Evaluation Harness

The Harness turns existing ScholarLens evaluator scripts and frozen result
artifacts into reproducible, comparable runs. It does not replace evaluator
logic or Gold datasets.

## Zero-cost replay

```powershell
python -m harness validate --config harness/configs/validated-replay-v1.json
python -m harness run --config harness/configs/validated-replay-v1.json
```

The replay copies frozen artifacts into a new immutable directory under
`harness/runs/<run-id>/`, applies explicit gates and writes:

- `config.json`: sanitized configuration snapshot;
- `artifacts/*.json`: copied or newly generated evaluator outputs;
- `logs/*.log`: command stdout/stderr with referenced environment values redacted;
- `run.json`: normalized machine-readable result;
- `report.md`: human-readable acceptance report.

## Live answer-quality run

The live configuration invokes the existing target-grounding and
answer-citation evaluators. It uses the configured model API and therefore can
consume paid tokens.

```powershell
$env:SCHOLARLENS_COLLECTION = "kb_your_collection_id"
python -m harness validate --config harness/configs/live-answer-quality-v1.json
python -m harness run --config harness/configs/live-answer-quality-v1.json
```

The Milvus API must be healthy at `http://localhost:8000/health`; model settings
continue to come from the project's ignored `.env`. Secret values are expanded
only in memory and are redacted from command logs.

For the one-paper development knowledge base used while fixing section-aware
retrieval, run the smaller method/conclusion smoke experiment:

```powershell
$env:SCHOLARLENS_COLLECTION = "kb_1790243595007"
python -m harness run --config harness/configs/attention-section-live-v1.json
```

Its two-case annotation is a development draft and must not be presented as an
independent held-out benchmark.

## Reports and comparisons

```powershell
python -m harness report --run <run-id>
python -m harness compare --baseline <baseline-run-id> --candidate <candidate-run-id>
```

Comparisons use stable stage and metric IDs. `higher` metrics improve when they
increase, while `lower` metrics such as latency improve when they decrease.

Process exit codes are `0` for PASS, `2` for a quality-gate FAIL, and `1` for a
configuration, preflight or evaluator runtime ERROR. Paid live runs are never
started by the test suite.
