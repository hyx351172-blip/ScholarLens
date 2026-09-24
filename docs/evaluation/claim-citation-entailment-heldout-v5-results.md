# Claim-to-citation Entailment Development Evaluation

- Dataset: `scholarlens-claim-citation-entailment-heldout-v5`
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
| CCHV5-01 | correct_single_real_evidence | PASS |
| CCHV5-02 | wrong_citation_correct_real_evidence_elsewhere | PASS |
| CCHV5-03 | grouped_citations_one_real_source_supports | PASS |
| CCHV5-04 | uncited_claim_real_evidence_available | PASS |
| CCHV5-05 | invalid_source_id_real_evidence_available | PASS |
| CCHV5-06 | real_evidence_contradicts_claim | PASS |
| CCHV5-07 | same_real_source_mixed_claims | PASS |
| CCHV5-08 | same_real_source_supported_and_fabricated_detail | PASS |
| CCHV5-09 | wrong_method_attribution | PASS |
| CCHV5-10 | partially_supported_composite_claim | PASS |
| CCHV5-11 | correct_downstream_output_contract | PASS |

## Scope

This is a synthetic development contract set, not a held-out release benchmark.
Each claim is evaluated only against the source snippets addressed by its own citations.
