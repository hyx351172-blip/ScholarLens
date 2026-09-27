# Target-grounded Multi-query Retrieval

## Goal

When the query planner identifies comparison targets, constrain each target
subquery to the uniquely resolved paper filename when that mapping is safe.
Never guess a filename when the mapping is weak, ambiguous, or unavailable.

## Acceptance criteria

- **AC-201.1** — The resolver removes repository identifiers and generic words,
  supports meaningful acronym expansion, and maps a target only when one corpus
  filename clears both the confidence threshold and ambiguity margin.
- **AC-201.2** — A resolved target is sent to the existing Milvus `/search`
  endpoint as an escaped document filter. Updated by AC-2902: explicitly scoped
  originals are filtered too; file IDs are preferred, with legacy filename fallback.
- **AC-201.3** — Never guess an unresolved target. Updated by AC-2904: catalog
  failure returns a service error; unresolved planner branches cannot expand an
  explicit document scope. Collection-wide fallback remains only for unscoped queries.
- **AC-201.4** — Retrieval trace records the overall resolution state and each
  target's status, filename, confidence score, and reason.
- **AC-201.5** — The development dataset contains positive aliases, safe
  unresolved cases, known corpus exclusions, and live two-paper retrieval
  cases; all deterministic and live development checks pass.

## Compatibility

The public chat request and response schemas do not change. Retrieval trace only
gains additive fields. The Milvus `/search` contract already supports the
optional `filter_expr` field.

## Out of scope

- Fixing the two known filename/content mismatches during ingestion.
- Hard-coding paper aliases in application code.
- Claim-to-citation entailment evaluation; that is a separate feature.
- Re-running the consumed Held-out Gold v4 split.
