# Subject scope refinement for anchored audit v3.1

Scope: a single evaluation-only refinement in the existing isolated checkout.
Use Python/unittest, existing v3 anchors and judge protocol. No production edits,
no v3 code/output overwrite, no automatic human approval, no paid calls this turn.

- AC-3301: For unresolved v3 clauses, extract conservative same-sentence antecedents from an immediately preceding introduced object, task label, or explicitly scoped retrieved-evidence noun. Keep exact answer spans. Do not pass predicates or borrow any prior clause's citations. Reject multiple candidate objects, subject changes, cross-sentence/newline/list boundaries, and unclear scope instead of inventing identity.
- AC-3302: Recognize explicit coordinated mathematical entities, named mathematical relations, and explicit operation objects without requiring a single grammatical subject. Preserve all entities, the full claim, and qualifiers. Do not equate explicit objects with semantic support or inherit a frozen parameter as the subject of trainable parameters.
- AC-3303: Apply syntax-based rules, never question/case/paper-specific overrides or AI-review labels. Preserve all original claim IDs, text, offsets, evidence, anchors, and denominator. Retain before/after diagnostics; failed matches remain unresolved. A narrow safety exception rejects v3's single-subject selection from mathematical alternatives (A or B) and any inherited hint originating there. V3 request isolation and exact anchor validation are unchanged.
- AC-3304: Prepare a new write-once v3.1 packet offline, freeze inputs/implementations/previous artifacts, and produce reviewable deltas with all human decisions pending. Assert zero provider calls and unchanged prior hashes. Tests include unseen names/symbols and negative examples, not only reviewed questions.
- AC-3305: Reuse v3's strict judgment and bounded journaled execution: fresh explicit request budget, no retries, preflight all cached fingerprints, incomplete-attempt stop, raw/error preservation, and no score overwrites. Runtime refuses protocol/settings drift. No new semantic score is produced by preparation or by local subject classification.

Plan / tasks:

1. RED fixture tests for the three antecedent patterns, six explicit-object cases,
   changed names/symbols, ambiguity, provenance, and source isolation.
2. GREEN standalone refinement atop immutable v3; reuse v3 anchors/judge/runner.
3. Dry-inspect all 85 frozen units before freezing v3.1; check changed and unchanged
   requests and all candidate spans. Prepare only after code/tests stabilize.
4. Full regression, traceability, integrity checks, report, then hand off. Live
   evaluation is a separate newly authorized batch, not covered by prior v2 calls.
