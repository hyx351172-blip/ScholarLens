# QASPER guard v2 — offline development replay

Replayed the same 20 immutable drafts from v1; zero new model calls. No production
service restart, commit, push or merge. ai-product-dev-pack was used for red/green
regressions and traceability; results are not an independent held-out evaluation.

## Changes

Grouped markers such as `[S1, S5]` and bounded ascending ranges such as `[S3–S5]`
expand into individual markers. Invalid IDs, descending ranges and groups exceeding
100 IDs fail closed. All non-citation answer text is preserved.

Refusal detection now recognizes additional English forms. A limitation after a
completed cited sentence does not automatically erase the answer; leading absence
statements and explicit whole-question refusals still normalize to fixed abstention.
This is a syntactic heuristic, not an evidence-grounding classifier.

| Development diagnostic | v1 | v2 |
| --- | ---: | ---: |
| Answerable drafts converted to fixed abstention | 4/15 | 0/15 |
| Unanswerable drafts normalized to fixed abstention | 2/5 | 4/5 |

These counts do not measure answer accuracy. In particular, the retained baseline
answer previously found narrower than the gold reference remains a quality issue.
The unanswerable question `What background do they have?` still passes: a response
can cite real text yet fail the question/annotation intent. Semantic support review
is necessary; no special-case rule for that single question was introduced.

## Verification

- Three new unit cases failed on v1, then passed on v2.
- Streaming and non-streaming tests include grouped citations and partial caveats.
- Full local test discovery: 412 passed in 22.556 seconds, no reported skips.
- Traceability: 112 declared/referenced AC IDs, no orphan/ghost IDs.
- `git diff --check` passed.
- Replay stores original draft file hashes and guard source hash in ignored
  `output/qasper-guard-dev-v1/guard-v2-replay.json`; v1 files are unchanged.

Next: freeze a paper-disjoint validation batch before live evaluation. Do not claim
v2 generalization based on development replay. Running services must load the new
code before live verification; this turn did not restart them.
