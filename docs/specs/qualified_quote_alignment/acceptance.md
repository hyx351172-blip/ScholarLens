# Bounded quote alignment v2.1 — offline fix

Repair the saved v2 response's whitespace-only citation failure without modifying
frozen policies, packets, raw responses, results or production defaults. This is
a new local interpretation, not a new model run or a retroactive v2 score.

- AC-4501: Collapse only nonempty runs of ASCII space, tab, CR and LF to one space. Preserve every other character, order and separator; do not strip, casefold, normalize Unicode, delete hyphens, join words or use fuzzy matching. Enforce bounded inputs.
- AC-4502: Require exactly one match inside the selected anchor after normalization, including when an exact match and a whitespace variant both exist. Count overlapping matches. Resolve the original contiguous source span and retain both the model quote and original source quote/offsets. Duplicate citations of the same resolved span fail.
- AC-4503: Add an independent v2.1 parser using the immutable v2 semantics after locally aligning quotes. Keep packet identity, strict JSON/field/count/length checks, three-facet logic, reason codes and fail-closed behavior. Preserve raw-response hash and declare the parser version; quotation alignment is not semantic verification.
- AC-4504: Reject foreign or cross-anchor citations, changed words/numbers/operators/punctuation, deleted/inserted separators, ambiguous occurrences, nonfinite/duplicate/oversized JSON and invalid metadata. All previously enforced semantic gates remain intact.
- AC-4505: Replay only the actual frozen complete responses, verify source/history hashes, retain all 52 input identities with 51 not_run entries and null semantic accuracy. No credentials, network clients, resumption or new API calls. Write new artifacts exclusively, never overwrite the stopped v2 experiment or reclassify its historical ERROR.
- AC-4506: RED/GREEN tests cover the actual failed response, source-coordinate mapping, ambiguity/negative cases, semantic invariance, immutable history, zero-call replay and write-once verification. Run full regression and traceability before handoff; no production wiring or Git publication.

Implementation: bounded matcher → v2.1 parser → separate cached replay → report.
No live runner, new prompt, changed evidence selection or new evaluation budget.
