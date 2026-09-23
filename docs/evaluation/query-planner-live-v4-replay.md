# Live Query Planner Evaluation

- Dataset: `scholarlens-evidence-gold-v3-multi-query-dev`
- Model: `qwen3-vl-plus`
- Evaluation mode: `persisted_retrieval_replay`
- Runs: 6
- Acceptance: **PASS**

## Summary

- Valid plan rate: 100.00%
- Complete target rate: 100.00%
- Strict evidence Hit@10: 100.00%
- Mean evidence recall: 100.00%
- Evidence-set MRR: 0.1796
- Mean nDCG: 0.5784
- Mean planner latency: 4.509s
- Mean retrieval latency: 2.848s
- Mean end-to-end latency: 7.358s

## Cases

| Case | Plan mode | All targets | Strict evidence hit | Planner | Total |
|---|---|---:|---:|---:|---:|
| MQ01 | comparison | yes | yes | 4.405s | 7.124s |
| MQ02 | comparison | yes | yes | 3.323s | 6.687s |
| MQ03 | comparison | yes | yes | 3.786s | 6.497s |
| MQ04 | comparison | yes | yes | 6.120s | 9.286s |
| MQ05 | comparison | yes | yes | 3.855s | 6.396s |
| MQ06 | comparison | yes | yes | 5.564s | 8.160s |

## Scope

This is a persisted-retrieval replay after a human-reviewed Gold change; it is not a fresh provider or vector-store run.
It does not replace the fresh held-out gate.
API keys and raw provider error payloads are not stored in this report.
- Re-scores persisted retrieval IDs; it does not call the planner or vector store again.
- A fresh live rerun is still required after local Milvus is restored.
