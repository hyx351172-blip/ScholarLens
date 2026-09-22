# ScholarLens Reranker A/B Experiment v1

## Decision

**No-go for replacing the current Dense ranking with a pure Reranker ranking.**

`qwen3-rerank` improves average ordering, but it fails the non-regression gate
because one cross-paper evidence set is no longer complete within Top-10.
`gte-rerank-v2` also fails and does not improve aggregate ranking quality.

## Experiment design

- Gold set: `scholarlens-evidence-gold-v1`, status `human_verified`
- Corpus: 19 papers, 2,057 chunks
- Cases: 12 answerable and 2 unanswerable questions
- Candidate generation: one Dense Top-20 request per question
- Arm A: original Dense Top-10
- Arm B: rerank the exact same 20 candidates, then take Top-10
- Models: `qwen3-rerank` and `gte-rerank-v2`
- Provider: Alibaba Cloud Model Studio / DashScope text rerank API
- Failures: abort the experiment; no silent Dense fallback
- Secrets: loaded from `.env`, never serialized into the result files

The API request and response contract follows the official
[Alibaba Cloud Text Rerank API](https://help.aliyun.com/en/model-studio/text-rerank-api).

## Acceptance gates

| Gate | Threshold |
|---|---:|
| Strict complete-evidence Hit@10 | 100% and no regression |
| Evidence-set MRR@10 | ≥ 0.75 |
| Mean nDCG@10 | ≥ 0.82 |
| Mean added latency | ≤ 1.0 s |

Every gate must pass for a `go` decision.

## Aggregate results

| Arm | Hit@10 | MRR@10 | nDCG@10 | Added latency | Decision |
|---|---:|---:|---:|---:|---|
| Dense baseline | **100.00%** | 0.6181 | 0.7274 | — | baseline |
| Dense + `gte-rerank-v2` | 91.67% | 0.6042 | 0.7231 | 0.213 s | **no-go** |
| Dense + `qwen3-rerank` | 91.67% | **0.7361** | **0.8237** | 0.222 s | **no-go** |

For `qwen3-rerank`, paired MRR outcomes are 4 wins, 7 ties, and 1 loss.
Paired nDCG outcomes are 6 wins, 5 ties, and 1 loss. The mean gains are
`+0.1181` MRR and `+0.0964` nDCG, but the hard Hit@10 regression takes
precedence over those average improvements.

## qwen3-rerank per-case analysis

| ID | Category | Dense MRR | Rerank MRR | Dense nDCG | Rerank nDCG | Outcome |
|---|---|---:|---:|---:|---:|---|
| EV01 | mechanism | 0.333 | 0.333 | 0.712 | 0.732 | tie/improved |
| EV02 | fact | 0.500 | 0.500 | 0.631 | 0.631 | tie |
| EV03 | mechanism | 1.000 | 1.000 | 0.798 | 0.813 | tie/improved |
| EV04 | mechanism | 1.000 | 1.000 | 1.000 | 1.000 | tie |
| EV05 | figure/mechanism | 0.500 | 1.000 | 0.651 | 0.920 | improved |
| EV06 | mechanism | 0.250 | 0.500 | 0.431 | 0.631 | improved |
| EV07 | architecture | 0.500 | 1.000 | 0.631 | 1.000 | improved |
| EV08 | fact | 1.000 | 1.000 | 0.920 | 0.920 | tie |
| EV09 | figure | 0.500 | 1.000 | 0.631 | 1.000 | improved |
| EV10 | cross-paper comparison | 0.333 | **0.000** | 0.693 | 0.613 | **regressed** |
| EV11 | table | 1.000 | 1.000 | 1.000 | 1.000 | tie |
| EV12 | formula | 0.500 | 0.500 | 0.631 | 0.631 | tie |

## Failure analysis

EV10 requires two pieces of evidence, one from BERT and one from GPT-3. Dense
retrieval ranks them at 3 and 2, so the complete set is available by rank 3.
`qwen3-rerank` moves the BERT evidence to rank 1 but pushes the required GPT-3
paragraph from rank 2 to rank 20. The reranker optimizes each passage
independently and does not preserve complementary evidence coverage across
papers. This is not a chunker or candidate-recall failure; both gold chunks are
present in the Dense Top-20 candidate pool.

The two unanswerable cases are retained for score inspection, but reranker
scores are relative within a request and must not be used as a global refusal
threshold. Refusal quality requires a separate answer/evidence-sufficiency
evaluation.

## Recommendation

Do not enable pure reranking in the production chat path yet. The next bounded
experiment should preserve Dense coverage while using reranker preferences,
for example rank fusion or a coverage-aware selection rule. It must be tested
against the same v1 Gold set and pass all four gates before integration.

## Reproduction

```powershell
$corpusPath = "<path-to-parser-artifacts>"

python -B scripts\evaluate_reranker_ab.py `
  docs\evaluation\evidence-gold-v1.json `
  --corpus $corpusPath `
  --candidate-k 20 `
  --top-k 10 `
  --reranker-model qwen3-rerank `
  --output docs\evaluation\reranker-ab-qwen3-v1-results.json

python -B scripts\evaluate_reranker_ab.py `
  docs\evaluation\evidence-gold-v1.json `
  --corpus $corpusPath `
  --candidate-k 20 `
  --top-k 10 `
  --reranker-model gte-rerank-v2 `
  --output docs\evaluation\reranker-ab-gte-v2-v1-results.json
```
