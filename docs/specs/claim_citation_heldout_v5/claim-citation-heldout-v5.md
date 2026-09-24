# Claim-to-citation Held-out v5 Dataset

## Goal

Create a frozen, human-reviewable held-out dataset that tests whether the
claim-to-citation evaluator judges scientific claims only from their cited,
real ScholarLens corpus chunks. Do not execute or consume the split before the
project owner confirms every case and label.

## Acceptance criteria

- **AC-203.1** — Every source is an exact chunk fetched from the indexed
  ScholarLens corpus, records provenance plus a SHA-256 text hash, and no source
  chunk ID overlaps Gold evidence from v1 through v4.
- **AC-203.2** — Parsed claim IDs, claim text, citation numbers, and bound source
  IDs exactly match the frozen expected-claim annotations.
- **AC-203.3** — The split covers supported citations, wrong-citation global
  rescue, grouped citations, uncited claims, invalid source IDs,
  contradictions, partial support, attribution errors, and mixed claims, with
  both supported and unsupported labels represented.
- **AC-203.4** — The lifecycle starts as `pending_human_review` and blocks
  execution; after explicit owner confirmation it allows exactly one run, then
  freezes as `human_verified`, `consumed=true` and rejects any rerun.
- **AC-203.5** — A review document exposes every question, candidate answer,
  claim label/rationale, and evidence excerpt with explicit owner checkboxes.
- **AC-203.6** — Dataset validation, regression tests, traceability, contract
  review, and secret scan pass without executing or modifying Held-out v4.

## Compatibility

This feature adds dataset-building and validation artifacts only. It does not
change production chat, retrieval, parsing, or frontend contracts.

## Out of scope

- Tuning the evaluator from v5 outcomes.
- Re-running the consumed Held-out v4 split.
