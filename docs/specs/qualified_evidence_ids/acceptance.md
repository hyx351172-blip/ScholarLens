# Qualified evidence-ID protocol v3

## Scope

Opt-in, offline-only replacement for model-written quotations. Keep the v2
content/scope/conditions policy and verdict rules unchanged to isolate the
citation-contract change. Preserve all frozen experiments and production code.
This feature does not claim to fix semantic over-rejection or infer entailment.

- AC-4701: Wrap only validated selected v1 anchors in a policy-bound v3 packet. Preserve text, claim, IDs and Unicode codepoint coordinates without adding neighboring/sibling evidence. Tampered, oversized and malformed packets fail closed.
- AC-4702: Require exactly three checks with bounded reasons and selected evidence_ids. Reject unknown, duplicated, wrong-type IDs, missing required evidence, extra quotes/offsets/verdicts, stale packet identities and malformed JSON. Each check selects at most three anchors.
- AC-4703: Programmatically reconstruct each citation from the entire chosen original anchor, with explicit selected_anchor granularity, exact original text and coordinates. Preserve repeated text, newlines, formulas and Unicode; never fuzzy-match or concatenate noncontiguous anchors.
- AC-4704: Preserve all v2 verdict and scope-guard semantics, including unsupported vs uncertain. Correct citation IDs do not prove semantic correctness; human_verified and semantic_verified stay false. Model reasons are not verified quotations.
- AC-4705: Provide an opt-in local answer gate. Missing, invalid, stale or unsupported reviews cannot release a candidate answer. No rewriting, implicit client, credentials, network, retries or production dispatch.
- AC-4706: Prepare the unchanged 30 SciFact + 22 regression inputs under the new protocol without Gold in requests. Frozen v1/v2/v2.1 records remain unchanged; write-once artifacts are hash-verified. No live approval is inherited from prior batches.
- AC-4707: Diagnose the six stored old responses and demonstrate explicit, labelled schema-adapter simulations on their selected IDs. Reject unmodified old responses under v3. Simulations are not actual model runs, do not change historical errors, and have null semantic accuracy. Produce RED/GREEN tests and an honest report.

## Plan and tasks

1. [BE] Write adversarial packet/parser tests, observe RED, implement the new isolated module.
2. [BE] Test full-anchor source reconstruction, v2 rule parity and local fail-closed gate.
3. [INT] Write offline preparation/history-drift tests, implement request export and clearly marked simulations.
4. [INT] Run targeted/full regression, traceability and hash checks; freeze a new offline artifact set and document limits.

No sentence re-segmentation is introduced: fixed E anchors remain fixed chunks,
U anchors remain existing sentence/paragraph units. Finer spans can be a future
independently tested contract, not a silent interpretation of an evidence ID.
