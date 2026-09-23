# Live Query Planner Evaluation

- Dataset: `scholarlens-evidence-gold-v3-multi-query-dev`
- Model: `qwen3-vl-plus`
- Evaluation mode: `live`
- Runs: 6
- Acceptance: **PASS**

## Summary

- Valid plan rate: 100.00%
- Complete target rate: 100.00%
- Strict evidence Hit@10: 100.00%
- Mean evidence recall: 100.00%
- Evidence-set MRR: 0.1852
- Mean nDCG: 0.5949
- Mean planner latency: 3.854s
- Mean retrieval latency: 2.912s
- Mean end-to-end latency: 6.766s

## Cases

| Case | Plan mode | All targets | Strict evidence hit | Planner | Total |
|---|---|---:|---:|---:|---:|
| MQ01 | comparison | yes | yes | 3.438s | 7.514s |
| MQ02 | comparison | yes | yes | 3.264s | 6.038s |
| MQ03 | comparison | yes | yes | 4.708s | 7.240s |
| MQ04 | comparison | yes | yes | 3.719s | 6.360s |
| MQ05 | comparison | yes | yes | 3.518s | 6.346s |
| MQ06 | comparison | yes | yes | 4.474s | 7.095s |

## Scope

This is a development-set live-provider check.
It does not replace the fresh held-out gate.
API keys and raw provider error payloads are not stored in this report.
