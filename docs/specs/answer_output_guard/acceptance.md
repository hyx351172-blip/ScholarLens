# Answer output guard

Bounded repair of the two live journey failures, not a general semantic verifier.

- AC-2201: Reject malformed, missing, and unknown source citations without guessing IDs.
- AC-2202: Normalize detected insufficient-evidence responses to a fixed abstention,
  removing any accompanying unsupported explanation.
- AC-2203: Streaming and non-streaming validate the full answer before publishing.
- AC-2204: Empty retrieval never falls back to free-form model knowledge.

Implementation: a shared deterministic guard plus a system-level grounding policy;
preserve existing response schemas with additive guard metadata. Buffer streaming
text until validation; increased first-content latency is an intentional tradeoff.
Citation checks do not prove entailment. Abstention detection is conservative and
may reject useful partial answers; paraphrases may evade detection. No automatic
repair call or added API cost. Keep the parser and retrieval algorithms unchanged.

Tasks: reproduce failures, implement shared guard, test both API modes, replay
saved live responses, run regression. Live regeneration remains a separate check.
