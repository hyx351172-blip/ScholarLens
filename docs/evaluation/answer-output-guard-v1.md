# Answer output guard v1

## Scope

Repair two observed output failures without changing retrieval or parsing.
An empty retrieval now returns a fixed insufficient-evidence response without
calling the generation model. Both chat modes apply the same system policy and
validate complete output before sending text to clients. Guard reason is exposed
as additive `metadata.answer_guard`.

Malformed, missing, or out-of-range source IDs cause abstention; IDs are never
guessed or silently attached to unsupported claims. Detected insufficient-evidence
answers are normalized to a fixed response, dropping accompanying explanations.

## Verification

- Full local discovery passed 404 tests in 21.426 seconds (no reported skips).
- Traceability passed: 106 declared AC IDs and 106 referenced IDs across the repository.
- `git diff --check` passed for the tracked implementation change.
- TDD: the new guard tests failed before implementation (missing module), then
  all six unit/API-mode tests passed. Streaming tests split output character by
  character to exercise broken citation boundaries.
- Offline replay of four saved live responses:
  - Method: unchanged, passed.
  - Table: unchanged, passed (28.4/41.8 preserved).
  - Conclusion: malformed citation blocked; returns abstention, not a corrected conclusion.
  - Unanswerable: normalized abstention, unsupported background removed.
- These are replay results, not newly generated live answers. No paid API call,
  server restart, merge or push was performed for this repair.

## Limitations and tradeoffs

Streaming transport stays compatible, but content is buffered until validation,
so first-content latency is now full generation latency. Sources still represent
retrieved candidates, not necessarily cited evidence.

This is not a semantic entailment verifier: a false claim with a valid source ID
can pass. Abstention phrase matching may over-reject useful partial answers or
miss unfamiliar paraphrases. Evaluate fresh answers and held-out questions before
claiming comprehensive grounding or releasing; PDF navigation remains unverified.

## Follow-up live validation — 2026-09-26

After the user restored Milvus, its standalone/MinIO/etcd containers were healthy.
Started the retrieval API (8000) and updated chat service (8501); reused the existing
isolated KB without uploading or re-embedding documents. Four real generations
used the existing configured provider, temperature 0, max_tokens 1000, multi-query
retrieval, top_k 10, threshold 0.1, no reranker. Query planning/embedding may also
invoke configured APIs. Credentials were consumed in memory only.

| Case | Mode | Seconds | Guard | Observed result |
| --- | --- | ---: | --- | --- |
| Conclusion | JSON | 9.92 | passed | Substantive Transformer conclusion, valid S1 |
| Conclusion | Stream | 7.28 | passed | Substantive Transformer conclusion, valid S1 |
| Unanswerable | JSON | 5.59 | insufficient_evidence | Fixed abstention; no 2023 claim |
| Unanswerable | Stream | 4.81 | insufficient_evidence | Fixed abstention; no 2023 claim |

All four final outputs passed citation-ID and expected-answer smoke checks. The
conclusion source was section 7; manual inspection matched the answer's architecture,
translation results, future-work and code-release statements to that source.
The service's `answer_guard` metadata confirms the updated path is running.
This run did not reproduce malformed model output; deterministic tests cover its
rejection. Raw pre-guard text is not stored, so the exact abstention trigger is not
distinguishable from metadata alone. No broad semantic-quality claim is made.

Reproducible opt-in runner: `tests/integration/run_answer_guard_live.py` (skips
already saved cases). Final responses and logs: ignored `output/answer-guard-live-v1/`.
Services remain running. PDF browser navigation, UI buffering behavior and wider
held-out regression are still pending. No merge or push performed.
