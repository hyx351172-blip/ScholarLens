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
- Evidence-set MRR: 0.0630
- Mean nDCG: 0.5251
- Mean planner latency: 4.509s
- Mean retrieval latency: 2.848s
- Mean end-to-end latency: 7.358s

## Cases

| Case | Plan mode | All targets | Strict evidence hit | Planner | Total |
|---|---|---:|---:|---:|---:|
| MQ01 | comparison | yes | no | 4.405s | 7.124s |
| MQ02 | comparison | yes | no | 3.323s | 6.687s |
| MQ03 | comparison | yes | yes | 3.786s | 6.497s |
| MQ04 | comparison | yes | yes | 6.120s | 9.286s |
| MQ05 | comparison | yes | no | 3.855s | 6.396s |
| MQ06 | comparison | yes | yes | 5.564s | 8.160s |

## Scope

This is a development-set live-provider check. It does not replace the fresh held-out gate.
API keys and raw provider error payloads are not stored in this report.
