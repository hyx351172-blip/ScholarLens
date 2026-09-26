# Local hierarchical-header reconstruction v11

One offline feature following v10: reconstruct missing header levels and spans
using existing group topology, frozen OCR geometry and actual crop ruling lines.
Do not modify production parsing, dependencies, prior runs, database or git history.
Keep the current dirty checkout because previous experimental artifacts depend on it.

## Acceptance criteria

- AC-1401: Only repair the supported failure: a strict, empty grouped-header
  structure, stable column axes, one collapsed physical header band, and otherwise
  matching regular body rows. Existing v10 successes must remain byte-identical.
  Invalid structures, unsupported topology or missing evidence retain fallback.
- AC-1402: Infer internal header levels from cropped-image vertical rule starts,
  independently corroborated by OCR positions in at least two different top-level
  groups. Wrapped text in spanning standalone cells cannot create header rows.
  No gold, known label strings, case IDs or desired row counts in reconstruction.
- AC-1403: Reconstruct colspan from rule partitions inside each parent group;
  extend existing standalone rowspan anchors to the inferred header depth. Preserve
  the body topology except uniform row offset; explicit empty slots cannot collapse.
  Do not split text or repair OCR characters. Unknown local spans are rejected.
- AC-1404: Bind text with unique geometric evidence, strict render/reparse, no
  lost/duplicated OCR; export changed-cell provenance, header hierarchy and per-column
  header paths. Contradictory lines/OCR or uncertain spans cannot silently pass.
- AC-1405: RED/GREEN synthetic and negative tests, frozen 3-case replay, separate
  official TEDS and coordinate/header diagnostics, integrity checks, full regression,
  traceability and report. Do not claim broad generalization or production acceptance.

## Plan / tasks

1. Tests for collapsed three-level header, nested colspan, standalone wrapped
   rowspan, empty slots, missing/contradictory rulings, preservation and escaping.
2. New isolated adapter. Reuse v10 axes/input checks unchanged; inspect vertical
   rules using the already installed OpenCV/NumPy. Match rule starts to OCR levels;
   partition only within original top-level header groups. Empty subregions keep
   atomic blank columns. Produce an auditable tree, not semantic label guesses.
3. Replay the same immutable cohort, keeping successful v10 outputs untouched.
   New outputs only; no model calls or network. Score only after inference freezes.
4. Review defense, topology invariants, failure handling, bounded work and source
   integrity; run tests and document limitations. No new application user journey:
   the real seam is crop pixels + OCR -> local topology -> HTML -> offline evaluator.
   Testing skill routes coverage; executed checks, not prose, provide evidence.

## Completed / review outcome

- [x] Core module import RED -> passing tests; review conflict/provenance tests
  independently failed first, then passed after remediation. 17 new tests total.
- [x] Real frozen replay: repaired paper header, byte-identical EEPROM success,
  invalid-structure control retained. No labels/case IDs/gold in reconstruction.
- [x] Header tree, column paths and original-cell provenance saved; body unchanged.
- [x] Separate official score: paper structure TEDS 1.0, full TEDS 0.990868;
  header span coordinates 20/20. Text discrepancies and gold-empty value kept visible.
- [x] 306 tests passed; 10 passed in isolated Paddle environment. Traceability and
  whitespace checks pass; 37 protected files unchanged.
- [x] Report: `docs/evaluation/omnidocbench-table-header-v11.md`.

Scope remains offline. No production integration, commit/push, annotation changes
or forced correction of OCR. Unsupported topologies and missing evidence fail closed.
