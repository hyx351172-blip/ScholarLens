# Live Query Planner Evaluation

- Dataset: `scholarlens-evidence-gold-v3-multi-query-dev`
- Model: `qwen3-vl-plus`
- Runs: 6
- Acceptance: **FAIL**

## Summary

- Valid plan rate: 100.00%
- Complete target rate: 100.00%
- Strict evidence Hit@10: 50.00%
- Mean evidence recall: 75.00%
- Evidence-set MRR: 0.0571
- Mean nDCG: 0.5388
- Mean planner latency: 5.133s
- Mean retrieval latency: 2.683s
- Mean end-to-end latency: 7.816s

## Cases

| Case | Plan mode | All targets | Strict evidence hit | Planner | Total |
|---|---|---:|---:|---:|---:|
| MQ01 | comparison | yes | no | 4.769s | 7.375s |
| MQ02 | comparison | yes | no | 4.335s | 7.108s |
| MQ03 | comparison | yes | yes | 4.511s | 7.311s |
| MQ04 | comparison | yes | yes | 3.250s | 5.990s |
| MQ05 | comparison | yes | no | 8.815s | 11.424s |
| MQ06 | comparison | yes | yes | 5.116s | 7.691s |

## Scope

This is a development-set live-provider check. It does not replace the fresh held-out gate.
API keys and raw provider error payloads are not stored in this report.
