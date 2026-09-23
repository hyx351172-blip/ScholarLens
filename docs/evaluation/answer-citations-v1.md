# Answer and Citation Evaluation

- Dataset: `scholarlens-evidence-gold-v3-multi-query-dev`
- Model: `qwen3-vl-plus`
- Acceptance: **FAIL**

## Summary

- Citation syntax valid: 100.00%
- Required-paper citation coverage: 100.00%
- Gold-evidence citation Hit rate: 83.33%
- Mean claim citation completeness: 69.54%
- Mean concept coverage: 100.00%
- Unsupported-claim case rate: 16.67%
- Mean answer pipeline latency: 29.494s

## Cases

| Case | Concepts | Required papers | Gold cited | Claim citations | Unsupported |
|---|---:|---:|---:|---:|---:|
| MQ01 | 100% | 100% | yes | 75% | 0 |
| MQ02 | 100% | 100% | yes | 72% | 1 |
| MQ03 | 100% | 100% | yes | 62% | 0 |
| MQ04 | 100% | 100% | yes | 67% | 0 |
| MQ05 | 100% | 100% | yes | 71% | 0 |
| MQ06 | 100% | 100% | no | 70% | 0 |

## Scope

Concept coverage and unsupported claims use the configured LLM as a development-time judge.
Citation syntax, source coverage, claim citation presence, and Gold chunk coverage are deterministic.
This development evaluation does not replace human review or a fresh held-out gate.
