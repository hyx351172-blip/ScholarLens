# Answer guard v2: bounded citation normalization and refusal scope

- AC-2401: Expand comma/semicolon groups and ascending inclusive ranges into valid
  independent source markers; reject unknown IDs, malformed syntax, descending
  ranges and groups over 100 IDs. Preserve unrelated answer text.
- AC-2402: A limitation after a completed, cited affirmative sentence must not by
  itself cause whole-answer abstention.
- AC-2403: Leading absence-of-evidence statements and explicit global refusal
  variants in English/Chinese still produce the fixed abstention.

Implementation: deterministic normalization before validation; no guessed IDs or
new model calls. Whole-refusal detection remains a syntactic heuristic, not semantic
classification. Partial answers can still contain unsupported statements. HTTP
schema remains compatible; metadata can report `normalized_citations`.

Verification: unit red/green, both API modes, immutable QASPER dev draft replay,
full offline regression. No claim of held-out improvement or production deployment.
