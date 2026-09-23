# Claim-to-citation Held-out v5 Release Evidence

## Acceptance coverage

| Acceptance criterion | Evidence |
|---|---|
| AC-203.1 | Exact source hashes and zero prior-Gold overlap validation |
| AC-203.2 | Parsed claim/citation/evidence binding regression test |
| AC-203.3 | 11 risk scenarios with 5 supported / 8 unsupported labels |
| AC-203.4 | Pending-review execution guard in the benchmark entrypoint |
| AC-203.5 | Generated review document with per-case owner checkboxes |
| AC-203.6 | 152 full regression tests plus traceability and secret gates |

## Verification result

- Full test suite: 152 passed.
- Dataset validation: 11 cases / 13 claims / 11 scenarios.
- Source text hash mismatches: 0.
- Gold chunk overlap with v1–v4: 0.
- Exact question overlap with v1–v4: 0.
- Binding errors: 0.
- Held-out v5 remains unexecuted and unconsumed pending owner review.
- Held-out v4 was neither executed nor modified.
