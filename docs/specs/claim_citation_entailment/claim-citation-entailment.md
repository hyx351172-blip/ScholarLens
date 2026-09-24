# Claim-to-citation Entailment Evaluation

## Goal

Evaluate each factual answer claim only against the source snippets cited by
that claim. Evidence retrieved for another claim must not rescue a wrong,
missing, or invalid citation.

## Acceptance criteria

- **AC-202.1** — Every factual claim receives a stable request-local claim ID,
  its citation numbers, valid/invalid citation numbers, and only the evidence
  addressed by its own valid citations.
- **AC-202.2** — The semantic judge receives claim-scoped evidence bundles and
  explicit instructions never to borrow evidence from another claim; uncited
  or invalid-only claims receive no evidence.
- **AC-202.3** — Structured judge output reports every required concept and
  every expected claim exactly once, with a boolean support decision and a
  reason, and exposes claim entailment metrics without removing legacy fields.
- **AC-202.4** — A versioned development dataset covers correct citations,
  wrong citations with the correct evidence elsewhere, grouped citations,
  uncited claims, invalid source IDs, and contradictions.
- **AC-202.5** — Deterministic tests, the development evaluator, full regression
  suite, traceability gate, and secret scan pass without consuming or modifying
  the held-out v4 dataset.

## Compatibility

The production answer and source schemas do not change. Evaluation reports gain
additive claim-level fields. Existing deterministic citation metrics remain
unchanged.

## Out of scope

- Re-running or tuning against the consumed Held-out Gold v4 split.
- Replacing the development-time LLM judge with human adjudication.
- Changing retrieval, generation prompts, or frontend citation rendering.
