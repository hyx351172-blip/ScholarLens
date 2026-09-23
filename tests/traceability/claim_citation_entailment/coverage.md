# Claim-to-citation Entailment Release Evidence

## Acceptance coverage

| Acceptance criterion | Evidence |
|---|---|
| AC-202.1 | `test_claim_evidence_bundles_include_only_each_claims_cited_sources` |
| AC-202.2 | Prompt-isolation and wrong-global-evidence regression tests |
| AC-202.3 | Strict judge-schema and deterministic no-evidence policy tests |
| AC-202.4 | `claim-citation-entailment-dev-v1.json`: 7 scenarios / 8 claims |
| AC-202.5 | 147 unit/regression tests, traceability gate, secret scan, and live development report |

## Verification result

- Full test suite: 147 passed.
- Traceability: 5 AC declarations / 5 test references, bidirectionally aligned.
- Live development judge: 7/7 cases and 8/8 claim decisions passed.
- Supported-claim recall: 100%.
- Unsupported-claim recall: 100%.
- Held-out v4 was neither executed nor modified.
