# Qualified claim support v2 — offline implementation

Scope: independent experimental verifier for content, scope and conditions.
Preserve every v1 experiment, label, prompt and production default. Inspect the
four SciFact disagreements as AI analysis, not human adjudication. Prepare the
same 30 SciFact and 22 selected-claim inputs for a future authorized comparison.
No model calls, label corrections, sample exclusions or production rollout.

- AC-4301: Wrap a validated immutable v1 packet without expanding/repartitioning evidence or borrowing sibling text. Bind the new policy, deterministic English/Chinese risk cues and original packet to a new fingerprint; reject tampering or stale v1 responses.
- AC-4302: Require exactly three checks: content, scope and conditions, with bounded statuses/reasons and exact selected-anchor citations. Resolve unique quote offsets from source text in code; reject foreign, fabricated, ambiguous, duplicate or empty supporting citations and malformed/oversized JSON.
- AC-4303: Compute the final decision in code, never accept a model-supplied overall pass. All checks must be entailed to pass. Reported broader scope, missing conditions and uncertain alignment cannot pass. For a lexical generalization cue, single-example/inference/no-basis scope evidence cannot establish generality; do not automatically reject all claims containing broad words.
- AC-4304: Risk cues are reminders, not a complete semantic parser or truth proof. Run scope/condition checks on every claim including those with no cue. Document that a model can still misclassify its own basis or conditions; exact quotation and structural success do not imply semantic verification.
- AC-4305: Gate the whole candidate conservatively; missing/invalid/stale reviews, uncertainty and unsupported checks cannot release it. Preserve empty/insufficient/invalid input distinctions, candidate text and explicit semantic_verified=false/human_verified=false. No implicit API client or kb_chat integration.
- AC-4306: Review all four SciFact mismatches with traceable source snippets, preserve official/adapted labels and denominator, keep human judgments null, and distinguish the clear generalization failure from annotation/inference-policy ambiguities. Freeze 52 identical-evidence v2 packets with labels/review notes stored separately.
- AC-4307: Offline RED/GREEN tests, complete regression, AC alignment, source/history hashes and secret-pattern checks pass. Export write-once artifacts and zero-call preparation stats; do not report synthetic decisions as model accuracy or imply that the live false acceptance is already fixed. New paid experiments require separate approval.

Implementation sequence: AI disagreement review → RED contract tests → new pure
v2 module → source-identical 52-packet offline adapter → GREEN → frozen report.
The cue lexicon is intentionally small; this is not atomic-fact decomposition,
retrieval repair, an abbreviation fix, or a rewrite of previous experiments.
