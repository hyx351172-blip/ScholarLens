# Geometric logical-grid binding v10

Continue the v9 diagnosed empty-cell collapse, as one offline feature. Use only
the frozen v8 strict HTML topology and v9 raw detector/OCR captures. No model run,
network, paid API, production parser change, commit or push. Preserve the dirty
workspace; no new checkout because prior uncommitted experiment inputs are needed.

## Acceptance criteria

- AC-1301: Infer ordered nonuniform row/column boundaries from repeated detector
  edges, independently of text values and gold. Require supported, stable axes and
  exact agreement with the frozen topology dimensions; never force a count or
  invent a missing boundary. Fail closed with diagnostic evidence.
- AC-1302: Construct logical rectangles from these axes, including rowspan and
  colspan. Match OCR by geometric overlap, never physical-box ordinal. Preserve
  empty cells, text, source IDs and spans. Reject ambiguous/cross-cell/outside OCR
  instead of duplicating it, shifting it, splitting it or guessing values.
- AC-1303: Validate finite crop-relative rectangles, bounded payloads and strict
  HTML; escape OCR text. Persist per-cell provenance, empty cells, unmatched OCR,
  axis evidence and an independent no-gold gate. A gate pass is review eligibility,
  not proof of OCR accuracy or permission to promote into production.
- AC-1304: Replay only verified frozen inputs into fresh nonoverlapping output,
  hash before/after; retain the invalid control and rejected candidates as baseline
  fallback. Separate scoring verifies output hashes and uses the existing official
  evaluator and coordinate diagnostics. No gold-based selection.
- AC-1305: RED/GREEN tests, real frozen-artifact replay and separate scoring,
  regression, traceability, review and report. Explain unsupported complex headers
  and limits of the three selected development tables, without claiming held-out
  generalization or downstream RAG gains.

## Plan and tasks

1. [BE] Failure tests: missing blank detections, nonuniform columns, shuffled boxes,
   spans, unstable/missing axes, ambiguous/outside OCR and unsafe payloads.
2. [BE] Pure stdlib edge clustering and logical-grid mapper. Cluster tolerance is
   15% of median detector dimension, with 10%/20% stability checks. An interior
   edge needs at least max(2, ceil(2% of unique boxes)) votes; outer edges need two.
   Counts are validated, not adjusted to fit. Require OCR coverage >= 0.7 and
   a >= 0.4 margin over the second-best cell. Freeze before gold scoring.
3. [INT] Fresh-output offline replay, integrity checks, artifacts and separate TEDS
   scoring using existing gold-only diagnostics. Never modify v8/v9 artifacts.
4. Review (validation, fail-closed behavior, injection, bounded work, integrity),
   full existing regression, report and traceability. No DB/UI/auth change or new
   application user journey; the new seam is captured geometry -> grid -> HTML ->
   official scoring. The skill routes tests; executed local gates provide evidence,
   not a claim of automatic CI enforcement.

## Completed / review outcome

- [x] RED import failures -> 19 new passing tests (14 mapper + 5 runner contracts).
- [x] Frozen no-gold replay: one mapping succeeds, one rejects missing row boundaries,
  invalid control retained. Zero model/API calls; 27 protected files unchanged.
- [x] Separate official TEDS reproduces baseline, scores accepted candidate 0.997186;
  both raw-glyph and official-normalized coordinate diagnostics preserve 2 OCR errors.
- [x] Full 289 tests pass, isolated pure 14 pass, AC traceability and diff whitespace pass.
- [x] Review and limits documented in `docs/evaluation/omnidocbench-table-grid-binding-v10.md`.

This feature stops at reviewable offline outputs. No production, commit, push or
gold-driven adoption. Next distinct feature: local hierarchical-header topology.
