# Isolated clause-level semantic evaluation v2

One evaluation feature only. Preserve frozen v1 answers, judge outputs, labels,
and scores; no production prompt/parser/retrieval/UI edits and no commit/push.
Use the existing isolated evaluation checkout (earlier work is uncommitted).

- AC-3101: Split Chinese sentences without mandatory whitespace, English sentences, semicolons, and selected clause commas. Preserve math, decimals, abbreviations, bracket tokens and source offsets. Retain potentially factual text; disclose remaining composite/context-dependent units rather than claiming perfect atomization.
- AC-3102: Citation groups bind backwards within their sentence/region only. Subclauses can inherit that region's trailing citations with explicit provenance; never borrow earlier sentences' or later lines' citations. Every judge call contains one unit and only its sources, not the full answer or other units.
- AC-3103: Request JSON-object output in non-thinking mode; validate a single exact-schema decision, expected ID, enum verdict, nonempty reason, and verbatim supporting quotes from that unit's cited sources. Reject malformed/duplicate-key/trailing JSON, fabricated quotes, foreign IDs, and truncated/provider-refused output. Never auto-repair or turn an error into unsupported/pass.
- AC-3104: Allow supported/unsupported/uncertain; malformed formula evidence can be uncertain rather than invented as multiplication. Count error, missing and uncertain separately, with all units retained in denominators. Exact refusals are separate; no valid evidence is deterministically unsupported without an API call. Only complete all-supported cases pass the semantic gate.
- AC-3105: Build a write-once v2 audit packet from the frozen 16 answers and compare segmentation/provenance locally. Persist raw text, usage, finish reason and errors for any authorized live run; no auto-retry, no automatic plain-text fallback, a required finite call budget, and an exclusive pre-call marker prevent uncertain repeat charges. V1 hashes and the runtime feature code remain unchanged.

Plan: RED fixture tests -> independent v2 evaluator/helper -> dry preparation and
inspection of A01/X01/L03 -> full regression/traceability and report. Live v2 API
requests require fresh authorization: prior approval was limited to 12 v1 calls.

JSON Object is a transport constraint, not schema/semantic correctness. Current
provider reference: https://help.aliyun.com/zh/model-studio/qwen-structured-output
(checked 2026-09-26). Qwen3-VL-Plus non-thinking mode supports JSON Object; local
strict validation remains mandatory. New denominator must not be compared to v1
as an answer-quality improvement, since answers are identical and units differ.
