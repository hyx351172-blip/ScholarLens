# Answer and Citation Evaluation

- Dataset: `scholarlens-evidence-gold-v4-answer-citations-heldout`
- Model: `qwen3-vl-plus`
- Acceptance: **FAIL**

## Summary

- Citation syntax valid: 100.00%
- Required-paper citation coverage: 87.50%
- Gold-evidence citation Hit rate: 50.00%
- Mean claim citation completeness: 94.60%
- Mean concept coverage: 93.75%
- Unsupported-claim case rate: 12.50%
- Mean answer pipeline latency: 21.772s

## Cases

| Case | Concepts | Required papers | Gold cited | Claim citations | Unsupported |
|---|---:|---:|---:|---:|---:|
| ACV4-01 | 100% | 100% | yes | 100% | 0 |
| ACV4-02 | 100% | 100% | yes | 100% | 0 |
| ACV4-03 | 100% | 100% | no | 91% | 0 |
| ACV4-04 | 50% | 50% | no | 100% | 2 |
| ACV4-05 | 100% | 100% | no | 100% | 0 |
| ACV4-06 | 100% | 100% | yes | 100% | 0 |
| ACV4-07 | 100% | 100% | no | 91% | 0 |
| ACV4-08 | 100% | 100% | yes | 75% | 0 |

## Scope

Concept coverage and unsupported claims use the configured LLM as a development-time judge.
Citation syntax, source coverage, claim citation presence, and Gold chunk coverage are deterministic.
This development evaluation does not replace human review or a fresh held-out gate.
