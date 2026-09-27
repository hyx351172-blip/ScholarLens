# QASPER answer guard diagnostic v1

Date: 2026-09-26. Development diagnostic, NOT official test-set performance and
NOT PDF/chunking/Milvus end-to-end evaluation. Dataset: QASPER v0.3 (CC BY 4.0),
local original distribution; answer scoring uses its supplied evaluator function.

## Frozen protocol

20 questions from 20 distinct papers: 15 unanimously answerable with nonempty
text-only evidence mapped to paper paragraphs, 5 unanimously unanswerable.
Seed: `scholarlens-qasper-guard-v1`. Hash ordering, scarce stratum first, one
question per paper. Excluded long contexts (>60000 characters) rather than truncate.
Eligible pools after filtering: 642 answerable / 59 unanswerable. Exclusions:
175 missing/visual evidence, 75 annotator disagreements, 39 unmapped evidence,
15 empty/overlong contexts. Compared normalized question text against 187 unique
historical questions in project report/run JSON files; no overlap found. This does
not exclude semantic overlap, paper overlap or prior exposure outside those files.

Inputs and reference labels are separate. Generation never loads labels; both
answerability groups receive full paper paragraph context with sequential source
IDs. No gold paragraph selection, answerability flags, page numbers or reference
answers enter the prompt. Official test split was not used for this experiment.

20 real calls, current configured model, temperature 0, max_tokens 700, no automatic
retry; all finish without length truncation. Total reported tokens: 105515. Mean
per-call duration: 3.479 seconds. Raw draft is preserved, then the production
deterministic guard is applied to the identical draft. System grounding policy
is enabled for both arms: this isolates the output guard, not the entire old/new
production system. No API keys/config responses were written to artifacts.

## Results

| Diagnostic | Result |
| --- | ---: |
| Answerable outputs converted to fixed abstention | 4/15 (26.7%) |
| Of those: malformed citation reason | 3 |
| Of those: insufficient-evidence phrase reason | 1 |
| Unanswerable outputs normalized to fixed abstention | 2/5 |
| Answerable mean token F1, raw draft | 0.2536 |
| Answerable mean token F1, guarded | 0.2018 |

Token F1 is max over references using the official function; citation markers are
stripped and the fixed Chinese refusal maps to `Unanswerable`. Long explanations
reduce lexical precision. These are not manually adjudicated correctness rates.
The 2/5 value is **not correct-refusal accuracy**: some of the other three drafts
already express lack of evidence in English, but are not normalized by the guard.
No evidence F1 or full claim-entailment metric is reported.

## Failure inspection

- Baselines question: a substantively relevant Transformer-baseline answer uses
  `[S1, S5, S6, S15]`; guard rejects the entire answer.
- Evaluation datasets question: draft lists CSAT, 20 newsgroups and Fisher Phase 1,
  matching references, but `[S23, S26]` syntax causes an avoidable rejection.
- NLP tasks question: draft uses comma-separated citations and an ID range
  (`[S36, S40–S52]`); current guard rejects rather than parsing grouped citations.
- A second baseline question has an insufficient-evidence caveat. Its draft is
  also narrower than reference answers, so do not attribute all quality loss solely
  to the guard or claim the draft was fully correct.
- Two unanswerable drafts say `does not specify` / `evidence is insufficient` or
  `evidence insufficient, cannot reliably answer`; the current phrase matcher
  does not cover these forms and allows explanatory prose through.

## Next repair, not implemented here

1. Parse grouped/range source citations conservatively; expand only syntactically
   valid, bounded IDs that actually exist. Never guess malformed IDs.
2. Separate answerability decisions from substring detection, and distinguish a
   partial-answer caveat from whole-answer refusal. Test English and Chinese cases.
3. Keep these 20 as development regression data now that failures were inspected.
   Freeze a disjoint paper-level validation batch before assessing new generalization.

## Reproduction and artifacts

- Prepare: `tests/integration/prepare_qasper_guard.py` (refuses overwrite).
- Generate: `tests/integration/run_qasper_guard.py` (opt-in; existing predictions skipped).
- Score: `tests/integration/score_qasper_guard.py` (offline, refuses missing predictions).
- Ignored artifacts: `output/qasper-guard-dev-v1/` contains inputs, separate labels,
  manifest with input hashes and overlap scope, 20 predictions, and scores.
- Preparation unit checks: 5 passed. No application change, commit or push.
- ai-product-dev-pack kept inference inputs separate from evaluation labels;
  this diagnostic does not replace production acceptance or CI enforcement.
