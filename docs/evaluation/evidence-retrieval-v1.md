# ScholarLens Evidence Retrieval Baseline v1

## Scope

This baseline evaluates whether dense retrieval returns the exact chunks needed
to answer scientific-paper questions. It does **not** evaluate the final LLM
answer, citation formatting, faithfulness, or refusal behavior.

- Collection: `kb_1790061860190`
- Corpus: 19 papers, 2,057 chunks, chunk schema `1.1`
- Evaluation set: 14 cases (12 answerable, 2 unanswerable)
- Retrieval: current dense embedding search, Top-10, no reranker
- Annotation status: `human_verified` (2026-09-22)

## Gold-set integrity

The evaluator rebuilt the chunks from all 19 saved `document.json` artifacts
using the current 600/900-token configuration and checked every gold reference.

| Check | Result |
|---|---:|
| Gold evidence references | 18 |
| Missing chunk IDs | 0 |
| Duplicate chunk IDs | 0 |
| Metadata mismatches | 0 |

This guards against silently evaluating with stale chunk IDs after chunker
changes.

## Results

| Metric | Result |
|---|---:|
| Strict complete-evidence Hit@10 | 100.0% (12/12) |
| Mean best evidence-set recall@10 | 100.0% |
| Evidence-set MRR@10 | 0.6181 |
| Mean nDCG@10 | 0.7274 |
| Mean retrieval latency | 2.352 s |
| Median retrieval latency | 2.288 s |

“Strict complete-evidence hit” requires all chunks from at least one valid gold
evidence set to appear in the Top-10. For a multi-chunk or cross-paper question,
finding only one supporting chunk does not count.

## Per-case evidence rank

`Best complete rank` is the lowest rank at which one complete evidence set has
been accumulated.

| ID | Category | Best complete rank | MRR | nDCG |
|---|---|---:|---:|---:|
| EV01 | mechanism | 3 | 0.333 | 0.712 |
| EV02 | fact | 2 | 0.500 | 0.631 |
| EV03 | mechanism | 1 | 1.000 | 0.798 |
| EV04 | mechanism | 1 | 1.000 | 1.000 |
| EV05 | figure/mechanism | 2 | 0.500 | 0.651 |
| EV06 | mechanism | 4 | 0.250 | 0.431 |
| EV07 | architecture | 2 | 0.500 | 0.631 |
| EV08 | fact | 1 | 1.000 | 0.920 |
| EV09 | figure | 2 | 0.500 | 0.631 |
| EV10 | cross-paper comparison | 3 | 0.333 | 0.693 |
| EV11 | table | 1 | 1.000 | 1.000 |
| EV12 | formula | 2 | 0.500 | 0.631 |

## Interpretation

The current chunker preserves enough scientific evidence for all answerable
cases at Top-10, including a table value, a formula, two figure-grounded cases,
and a two-paper comparison. The main bottleneck exposed by this baseline is
ranking: Mamba evidence (EV06) is only complete at rank 4, while Transformer and
cross-paper evidence are complete at rank 3. A reranker or hybrid retrieval
experiment is therefore a better next step than another broad chunker rewrite.

The two unanswerable questions still produced dense-search maximum similarity
scores of `0.6510` and `0.6375`. These values overlap plausible answerable
retrieval scores, so a single similarity threshold is not yet justified as a
refusal mechanism. Refusal must be tested at the answer-generation layer using
evidence sufficiency and citation entailment checks.

## Reproduction

```powershell
$corpusPath = "<path-to-parser-artifacts>"
python -B scripts\evaluate_evidence_retrieval.py `
  docs\evaluation\evidence-gold-v1.json `
  --corpus $corpusPath `
  --output docs\evaluation\evidence-retrieval-v1-results.json
```

## Release decision

This is a human-verified retrieval baseline. It can now be used as the v1
regression gate for retrieval experiments. It remains a retrieval benchmark,
not evidence that final answer generation, citation faithfulness, or refusal
behavior is correct.
