# Claim-bound output validation v2

Scope: fix semicolon false rejection and misleading failure messages only.
Keep the old v1 module byte-identical for archived experiment replay. Production
dispatch uses a new v2 output module, with the SAME prompts, anchors, model,
retrieval and default legacy mode. No paid calls, restarts or git publication.

- AC-3601: A semicolon joining clauses within a single claim is not a hard rejection. Preserve every original character and the model's exact selected evidence. Emit a non-blocking compound-clause warning. Do not split/rewrite clauses, manufacture citations or broaden anchor ownership. Semantic verification remains false.
- AC-3602: Continue rejecting unknown/missing/duplicate evidence IDs, duplicate or extra JSON keys, invalid envelopes, oversized/deep JSON, multiple full-stop sentences, control characters, injected citation markers, code and HTML. Validate the entire answer before rendering; no partial salvage.
- AC-3603: Only genuine insufficient output or empty retrieval returns the insufficient-evidence message. Invalid structure, invalid evidence input and incomplete generation receive distinct fixed safe messages, with unchanged diagnostic status codes and v2 binding version. Provider exceptions stay sanitized; no fallback generation or retries.
- AC-3604: Integrate both JSON and NDJSON response paths, preserving legacy behavior, the existing source shape and return_source flag. New warning metadata is additive; no raw JSON or partial answer leaks. Neither historical prompts nor source IDs change.
- AC-3605: Replay all 12 frozen candidate cases against v1 and v2 using saved raw responses, not new model output. A02/A03 must recover without dropping rows; previously accepted answers and intended refusals must remain byte-identical. Report structural recovery only, not improved semantic accuracy, new latency or new live A/B scores.
- AC-3606: Add failing regression cases before changes and run full tests/traceability. Preserve all original answer-mode-ab-v1 data and scores. Archive pre-change versions of frozen code files being intentionally edited and verify all other 604-manifest entries unchanged. The old live experiment's drift guard must still reject the changed checkout.

Plan: snapshot → RED contract/API tests → v2 renderer and dispatch → GREEN →
offline replay with immutable output + differential regression → local acceptance.
Out of scope: better anchor selection, PDF fraction repair, semantic verification,
frontend mode switch, clause auto-splitting, expanded paid experiments.

Local acceptance (2026-09-27): 12 cached responses replayed, only A02/A03
answers changed; 608 regression tests and 163/163 traceability passed.
See `docs/evaluation/claim-output-v2-replay.md` for the non-semantic scope,
historical integrity checks, artifacts and remaining limitations.
