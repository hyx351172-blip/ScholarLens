# Claim-bound answer generation v1

Scope: one opt-in production answer format, not semantic auto-grading. Existing
Python/FastAPI/OpenAI-compatible stack, unittest, no new dependency or migration.
Continue in the existing isolated checkout; preserve unrelated work and frozen
evaluation artifacts. No paid calls, service restart, commit, merge or push.

- AC-3401: Build bounded, deterministic evidence anchors from the final retrieved/reranked documents. Preserve source order, exact text and Unicode offsets without normalization or silent truncation. Invalid/oversized evidence fails before any model call.
- AC-3402: Require a strict JSON envelope containing answered claims with their own nonempty known anchor IDs, or an empty insufficient response. Reject unknown/duplicate anchors, extra/duplicate keys, embedded citations, malformed JSON, unsafe multi-line/list/code output, and multiple sentences within one claim. No copied quotes or source IDs are accepted from the model.
- AC-3403: Programmatically render each validated claim with only the citations derived from its selected anchors. Return auditable claim-to-source offsets in additive metadata. Do not attach sibling sources, guess missing citations, repair formulas, infer entailment, or silently salvage invalid partial output.
- AC-3404: ChatRequest.answer_mode defaults to legacy; claim_bound is opt-in. Stream and non-stream share the exact validation/rendering path and emit no raw JSON or unvalidated tokens. Existing answer/source/stream contracts and source numbering remain compatible. Empty retrieval makes zero model calls.
- AC-3405: The new generation path makes one bounded provider call with zero retries and 60-second timeout. Reject truncated/refused/empty responses, sanitize provider exceptions, and do not fall back to free-text generation. System policy applies even with custom templates or historical system messages; metadata never contains credentials/raw provider errors.
- AC-3406: Test positive and negative contracts and both chat response modes using mocked external boundaries. Test only provenance and structural citation coverage, not semantic truth. Keep v3.1 raw labels and 304 frozen hashes unchanged. Real generation efficacy remains unverified until separately authorized.

Plan / tasks:

1. Review diagnostic boundaries: citation gaps vs rubric ambiguities and judge
   mistakes. AI review does not fill human labels or rewrite prior scores.
2. RED unit tests for anchors, strict claim envelope and rendering; integration
   tests for mode dispatch, source order, streaming buffering and single-call safety.
3. GREEN standalone backend module and minimal ChatService integration, preserving
   the default legacy path and frontend contract.
4. Run full regression, traceability and frozen-input checks. Document invocation,
   limitations and pending real-model validation. Stop after this one feature;
   inline PDF fractions are a separate task.

Completion: steps 1–4 completed offline on 2026-09-26. New tests: 27;
full regression: 578 passed; traceability: 151/151; frozen v3.1 hashes: 304/304.
See `docs/evaluation/claim-bound-answer-v1.md` for the contract, review and limits.
No external calls, default switch, service restart, commit, merge or push.
