# Sentence-aware claim evidence (candidate, not default)

The prior experiment found that fixed-width anchors can interrupt supporting
sentences. This feature changes evidence presentation and explicit selection,
not retrieval, PDF content, factual interpretation or semantic verification.

- AC-3701: Deterministic sentence/paragraph units preserve source order, every original character and exact offsets. English/Chinese punctuation is recognized, but decimals, abbreviations, URLs, math and ordinary line wraps are not mistaken for boundaries. Markdown table rows stay intact within the size limit.
- AC-3702: A unit longer than the hard 960-character limit is split into bounded, explicitly linked parts without cutting a protected math/URL span. All parts must be explicitly selected to cite a fragmented unit. Reject impossible protected spans, more than 8 parts or excessive catalog size before a model call; never truncate evidence or add citations automatically.
- AC-3703: Use a separate U namespace and catalog version; old E IDs cannot silently bind to new ranges. Each claim still needs its own IDs; unknown/missing IDs and other output checks remain hard failures. Valid structure never implies semantic support.
- AC-3704: Add opt-in claim_evidence_mode=sentence_v2; fixed_v1 and legacy remain defaults. JSON and NDJSON share messages/metadata; empty or invalid evidence causes zero provider calls. No added retry, fallback, provider or dependency.
- AC-3705: Prompt asks for only question-relevant facts, explicit coverage of each quantity/dimension/condition and preservation of research scope; unclear equations must be omitted. User data/history/preferences cannot override this policy. These instructions are not represented as a semantic guarantee.
- AC-3706: Audit all 12 frozen input cases offline. Export candidate catalogs and generation messages, compare exact coverage and sentence-boundary cuts, and inspect previously split NSP/rank sentences. Do not reuse old E selections as U selections, regenerate answers, revise old scores/labels or report improved accuracy. Historical artifacts and pre-change code hashes remain verifiable.

Plan/tasks: RED fixtures and API tests → pure versioned catalog/selection
module → optional shared-dispatch integration → GREEN → 12-case read-only-input
audit with write-once outputs → full regression and local release gate.

Out of scope: automatic semantic judging, new paid calls, formula recovery,
automatic citation expansion, default/UI switches, restarts and git publication.

Local acceptance (2026-09-27): all 12 frozen cases audited without generation;
626 tests passed, 169/169 traceability. Default requests and previous replays
unchanged. See docs/evaluation/evidence-units-v2.md; semantic improvements and
actual token/latency changes remain unmeasured, and the candidate stays opt-in.
