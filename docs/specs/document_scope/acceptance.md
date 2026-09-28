# Authoritative document scope

Repair the candidate leakage found by multipaper E2E A04/B04/L02, without weakening that frozen gate.

- AC-2901: Resolve explicit current-question paper identities against this collection's catalog; use exact file IDs when available, with escaped filename fallback only for legacy catalog rows lacking an ID. Do not hard-code the three evaluation papers.
- AC-2902: The resulting scope constrains original queries, subqueries, fallback, and final candidates. A single-paper scope bypasses comparison planning; a comparison inside that paper must not invent another document target.
- AC-2903: Actual two-paper requests retain both papers and independent target retrieval. Planner errors cannot widen the original scope. General questions with no detected paper identity remain collection-wide.
- AC-2904: Unknown explicit restrictions and ambiguous aliases fail closed with an observable reason. Catalog failures return a service error without unfiltered retrieval. Never silently reinterpret these as permission to search more documents.
- AC-2905: Add regression tests for ID validation, escaping, ignored scope filters, historical/negated mentions, non-matching substrings, and real dev replay of the three failures plus comparison/history/empty cases. Preserve the v1 originals.

Plan: pure scope resolver -> catalog reader -> scoped retrieval closure -> RED/GREEN tests -> full regression -> isolated Chat service replay against the existing 3-paper index. No re-upload, no parser/front-end changes, no commit/push as part of this feature.

Compatibility: request/response schemas stay unchanged; trace gains document_scope, dropped candidate counts, and planner bypass information. This supersedes AC-201.2's unfiltered-original rule and AC-201.3's catalog-failure fallback where an authoritative document scope is required. A genuine catalog outage now fails visibly instead of pretending an unscoped answer is safe.

Boundary: deterministic aliases come from PDF filenames and optional catalog titles, not arbitrary semantic paraphrases. Document scope is evidence selection, not authentication/authorization. A successful dev replay is not a new held-out quality claim.
