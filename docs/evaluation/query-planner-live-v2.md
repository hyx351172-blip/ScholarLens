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
- Evidence-set MRR: 0.0537
- Mean nDCG: 0.5266
- Mean planner latency: 4.433s
- Mean retrieval latency: 2.845s
- Mean end-to-end latency: 7.278s

## Cases

| Case | Plan mode | All targets | Strict evidence hit | Planner | Total |
|---|---|---:|---:|---:|---:|
| MQ01 | comparison | yes | no | 3.739s | 6.330s |
| MQ02 | comparison | yes | no | 5.593s | 8.461s |
| MQ03 | comparison | yes | yes | 4.241s | 7.526s |
| MQ04 | comparison | yes | yes | 3.682s | 6.307s |
| MQ05 | comparison | yes | no | 4.019s | 6.822s |
| MQ06 | comparison | yes | yes | 5.323s | 8.223s |

## Scope

This is a development-set live-provider check. It does not replace the fresh held-out gate.
API keys and raw provider error payloads are not stored in this report.
