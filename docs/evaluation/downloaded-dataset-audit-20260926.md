# Downloaded dataset audit and next evaluation

Date: 2026-09-26. Local files were inspected; no download, model call, ingestion,
or application change. Root: `backend/data/benchmarks/` (gitignored).
This is a test-routing audit under ai-product-dev-pack, not a benchmark result or
CI gate. Existing parser reports demonstrate prior OmniDocBench use; no QASPER,
SciFact or SPIQA execution report was found in the inspected project report/script
directories. That does not prove they were never accessed elsewhere.

## Verified inventory

| Dataset | Available locally | Next use |
| --- | --- | --- |
| QASPER v0.3 | Train 888 papers/2593 questions; dev 281/1005; test 416/1451; evaluator | Scientific QA and abstention |
| SciFact | 5183 abstracts; claims train 809/dev 300/test 300 | Claim support/refutation and evidence retrieval, not general QA |
| SPIQA test-A | 118 papers; manifest records 666 questions; 1126 images verified | Figure/table QA later; only 224px images downloaded |
| OmniDocBench | 1651 annotation pages; selected 100 academic-English pages | Parser regression; previously tuned samples are development data |

QASPER files include titles, abstracts, section text, questions, answer annotations,
and paragraph evidence. Figure/table references are not the actual images. Its
README identifies visual evidence with `FLOAT SELECTED`. Do not substitute
captions for visual data or call missing visual evidence model failure.

## QASPER dev eligibility

- 1005 questions total.
- 60 questions: all available annotations mark unanswerable.
- 75 questions: disagreement in unanswerability; exclude from the first binary
  refusal diagnostic, preserving them for a later ambiguity analysis.
- 690 questions: all annotations answerable, each with nonempty textual evidence
  and no `FLOAT SELECTED` entry. These are a candidate pool, not manually verified
  clean examples; evidence-to-full-text mapping still needs checking.

Train/dev/test counts were inspected. Test questions were not selected for tuning;
do not call a newly chosen development subset an untouched official held-out test.
Question overlap with project-specific Gold sets has not yet been checked.

## Proposed bounded next run

1. Freeze a deterministic dev subset: 15 answerable questions and 5 unanimous
   unanswerable questions, paper-stratified; retain IDs, input hash and exclusions.
   Check exact/normalized question overlap against existing Gold and run artifacts.
2. Separate inference inputs from labels. Never include reference answers,
   answerability flags or highlighted evidence in model prompts.
3. First isolate the output guard: use identical fixed model drafts/evidence and
   compare before/after deterministic guarding. Preserve raw drafts separately from
   final responses; this is guard ablation, not the full system before/after comparison.
4. For a gold-evidence answerable diagnostic, label it explicitly as oracle-context.
   Do not test unanswerable cases with empty gold evidence: that would leak the label
   and trigger the trivial no-evidence path. Use full paper context, or a retriever
   that sees only question and corpus, and record truncation/context limits.
5. Score answerable quality and false refusals separately from correct abstentions.
   Use multi-reference scoring, citation-ID validity, and manual evidence support
   checks; valid citation IDs alone are not entailment. Inspect the official evaluator
   before adapting its prediction schema or reporting its metrics.
6. Only after this diagnosis, run corpus retrieval/generation, then a separate PDF
   upload pipeline on available PDFs. Dataset text lacks our parser page provenance,
   so do not invent page numbers or claim PDF ingestion coverage.

Keep OmniDocBench frozen for this answer-only change; no expensive parser rerun.
SciFact and SPIQA require separate task adapters and should not be pooled into one
QA score. Final test splits remain reserved for a frozen system evaluation.

Status: inventory complete; sampling/adapter/model execution not yet performed.
