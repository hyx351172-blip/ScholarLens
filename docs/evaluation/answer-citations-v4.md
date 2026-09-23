# Answer and Citation Evaluation

- Dataset: `scholarlens-evidence-gold-v3-multi-query-dev`
- Model: `qwen3-vl-plus`
- Acceptance: **PASS**

## Summary

- Citation syntax valid: 100.00%
- Required-paper citation coverage: 100.00%
- Gold-evidence citation Hit rate: 100.00%
- Mean claim citation completeness: 97.22%
- Mean concept coverage: 100.00%
- Unsupported-claim case rate: 0.00%
- Mean answer pipeline latency: 21.666s

## Cases

| Case | Concepts | Required papers | Gold cited | Claim citations | Unsupported |
|---|---:|---:|---:|---:|---:|
| MQ01 | 100% | 100% | yes | 100% | 0 |
| MQ02 | 100% | 100% | yes | 100% | 0 |
| MQ03 | 100% | 100% | yes | 83% | 0 |
| MQ04 | 100% | 100% | yes | 100% | 0 |
| MQ05 | 100% | 100% | yes | 100% | 0 |
| MQ06 | 100% | 100% | yes | 100% | 0 |

## Scope

Concept coverage and unsupported claims use the configured LLM as a development-time judge.
Citation syntax, source coverage, claim citation presence, and Gold chunk coverage are deterministic.
This development evaluation does not replace human review or a fresh held-out gate.
