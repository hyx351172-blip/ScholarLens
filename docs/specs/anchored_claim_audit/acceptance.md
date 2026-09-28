# Anchored, subject-aware claim audit v3

Scope: one evaluation feature in the existing isolated evaluation checkout. No
production changes, baseline relabeling, commit/push, or paid calls in this turn.
V2 input text, unit IDs, citation groups, and results remain immutable. Python
unittest is the existing test framework; no new dependencies are needed.

- AC-3201: Preserve each v2 unit and its citation set. Extract conservative subject hints only from earlier clauses in the same sentence, as verbatim answer spans. Reset on sentence/newline boundaries and explicit subject changes. Never send sibling predicates, whole paragraphs, or sibling citations as context. Ambiguous/unrecognized subjects remain reviewable, not invented.
- AC-3202: Deterministically partition every cited snippet into numbered anchors with exact Unicode character offsets, covering its full original text without normalization or omission. Preserve decimals, math, and tokens where possible; long forced splits are disclosed. IDs and offsets are request-local and reproducible.
- AC-3203: The judge selects anchor IDs rather than copying quotations. Strict JSON validates expected claim ID, verdict/reason-code consistency, nonempty reasons, unique own-anchor selections, and at least one anchor for support. The application resolves anchors to exact original text and coordinates. Unknown anchors, text-based substitutes, duplicate keys, and nonfinite JSON fail closed. Anchors prove location, not entailment.
- AC-3204: Keep one-claim isolation; subject hints resolve identity only and are not factual evidence. Preserve unsupported qualifiers and ambiguous math policies. Distinguish subject/evidence ambiguity from contradiction or missing support; do not require one claim to answer the whole question. Raw decisions and errors are retained, not repaired or re-voted.
- AC-3205: Preparation is offline and write-once, with frozen code/input/result hashes and human review pending. Live calls require a new finite budget, use max_retries=0, and journal each attempt before sending. Validate all cached records and request fingerprints before spending; incomplete attempts stop execution. Failed results are not retried. All 85 units remain in the denominator; only complete support passes the semantic gate.

Plan / tasks:

1. RED: fixtures for missing W0/encoder/BERT subjects, model changes, citation leakage, math/whitespace anchors, foreign IDs, ambiguous reason codes, budget/cache safety.
2. GREEN: independent v3 helper and prepare/run entry point; do not edit frozen v2 helpers.
3. Prepare and inspect all frozen units offline, retaining heuristic limitations and no new semantic scores.
4. Run regressions, traceability, integrity checks, and record a handoff report. Live model validation remains a separately authorized experiment.
