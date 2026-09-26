# Development checkpoint — 2026-09-26

Historical checkpoint: the NO-GO below was the decision before answer repairs.
For the subsequent bounded development merge decision, see
`merge-acceptance-20260926.md`. Do not interpret this as the current gate status.

Scope: accumulated parser/export improvements, bounded table experiments,
evaluation harness, and live journey reports. This is not a production release.

## Checks

- Full local discovery: `python -X utf8 -m unittest discover -s tests -p 'test_*.py'`
  passed 398 tests in 57.945 seconds, with no reported skips.
- Spec/test traceability: 102 declared AC IDs and 102 referenced IDs; check passed.
- Tracked-file `git diff --check` passed before staging. The staged check,
  including formerly untracked files, reports trailing blank lines at EOF in
  12 files; these are preserved in this checkpoint, not claimed as a clean gate.
  Existing LF/CRLF conversion warnings also remain.
- Common credential-pattern scan of changed/new files found no matches. This is
  a limited safeguard, not a security audit. Environment files, raw uploads,
  local run artifacts and model caches are excluded from this commit.
- Frontend tests/build were verified in the preceding live journey run, not
  rerun for this checkpoint; see `end-to-end-live-v1.md`.

## Merge decision: NO-GO

The offline regression suite does not supersede live acceptance failures:

- One live answer emitted a malformed citation (`[S母公司]`).
- An insufficient-evidence answer added a fact absent from retrieved evidence.
- PDF page navigation has not yet been visually verified in a normal browser.

Push the development checkpoint for backup/review, but do not merge into main
under the current release gate. No answer-generation fix is included here.
Fix and rerun the failing cases before reevaluating the gate. No CI enforcement
has been added; this document records a manual gate decision.
