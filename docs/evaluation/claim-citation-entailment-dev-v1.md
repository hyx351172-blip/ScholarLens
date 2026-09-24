# Claim-to-citation Entailment Development Evaluation

- Dataset: `scholarlens-claim-citation-entailment-dev-v1`
- Model: `qwen3-vl-plus`
- Acceptance: **PASS**

## Summary

- Claim decision accuracy: 100.00%
- Case exact-match rate: 100.00%
- Unsupported-claim recall: 100.00%
- Supported-claim recall: 100.00%

## Cases

| Case | Scenario | Result |
|---|---|---|
| CCE-01-correct-single | correct_single_citation | PASS |
| CCE-02-wrong-citation-global-rescue | wrong_citation_correct_evidence_elsewhere | PASS |
| CCE-03-grouped-citations | grouped_citation_one_source_supports | PASS |
| CCE-04-uncited | uncited_factual_claim | PASS |
| CCE-05-invalid-source-id | invalid_citation_only | PASS |
| CCE-06-contradiction | cited_evidence_contradicts_claim | PASS |
| CCE-07-mixed-multiple-claims | same_source_supports_one_claim_only | PASS |

## Scope

This is a synthetic development contract set, not a held-out release benchmark.
Each claim is evaluated only against the source snippets addressed by its own citations.
