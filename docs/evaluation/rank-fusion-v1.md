# ScholarLens Rank Fusion Experiment v1

## Decision

**Proceed to held-out validation with weighted RRF (`Dense 2.0`, `Reranker 1.0`).**

This configuration is the only tested fusion variant that passes all current
acceptance gates. It restores the Dense baseline's 100% complete-evidence
Hit@10 while retaining most of the ranking-quality gain from `qwen3-rerank`.
It is not yet approved for production because the same v1 Gold set was used
to select the weight.

## Experiment design

- Gold set: `scholarlens-evidence-gold-v1`, status `human_verified`
- Corpus: 19 papers, 2,057 chunks
- Cases: 12 answerable and 2 unanswerable questions
- Candidate generation: one Dense Top-20 request per question
- Reranker: `qwen3-rerank` over the exact same 20 candidates
- Final result size: Top-10
- Fusion: weighted Reciprocal Rank Fusion (RRF), `k = 60`
- Compared weights: `1:1`, `1.5:1`, `2:1`, and `3:1`
- Failures: abort the experiment; no silent Dense fallback
- Secrets: loaded from `.env`, never serialized into result files

For candidate `d`, the fusion score is:

```text
score(d) = dense_weight / (60 + dense_rank(d))
         + reranker_weight / (60 + reranker_rank(d))
```

## Acceptance gates

| Gate | Threshold |
|---|---:|
| Strict complete-evidence Hit@10 | 100% and no regression |
| Evidence-set MRR@10 | >= 0.75 |
| Mean nDCG@10 | >= 0.82 |
| Mean added latency | <= 1.0 s |

Every gate must pass for a `go` decision.

## Aggregate results

| Arm | Hit@10 | MRR@10 | nDCG@10 | Added latency | Decision |
|---|---:|---:|---:|---:|---|
| Dense baseline | **100.00%** | 0.6181 | 0.7274 | - | baseline |
| Pure `qwen3-rerank` | 91.67% | 0.7361 | 0.8237 | 0.216 s | no-go |
| RRF `1:1` | **100.00%** | 0.7454 | **0.8279** | 0.216 s | no-go: MRR |
| RRF `1.5:1` | **100.00%** | 0.7480 | **0.8286** | 0.216 s | no-go: MRR |
| RRF `2:1` | **100.00%** | **0.7500** | **0.8231** | 0.216 s | **go for held-out validation** |
| RRF `3:1` | **100.00%** | 0.7083 | 0.8025 | 0.216 s | no-go: MRR and nDCG |

The selected `2:1` arm has 4 MRR wins, 7 ties, and 1 loss against Dense. For
nDCG it has 6 wins, 5 ties, and 1 loss. Its mean gains over Dense are `+0.1319`
MRR and `+0.0957` nDCG.

## Per-case results for the selected arm

Values are `MRR / nDCG`; all selected-arm cases retain complete evidence in
Top-10.

| ID | Category | Dense | Pure reranker | RRF `2:1` |
|---|---|---:|---:|---:|
| EV01 | mechanism | 0.333 / 0.712 | 0.333 / 0.733 | 0.333 / 0.733 |
| EV02 | fact | 0.500 / 0.631 | 0.500 / 0.631 | 0.500 / 0.631 |
| EV03 | mechanism | 1.000 / 0.798 | 1.000 / 0.807 | 1.000 / 0.807 |
| EV04 | mechanism | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 |
| EV05 | figure/mechanism | 0.500 / 0.651 | 1.000 / 0.920 | 1.000 / 0.920 |
| EV06 | mechanism | 0.250 / 0.431 | 0.500 / 0.631 | 0.500 / 0.631 |
| EV07 | architecture | 0.500 / 0.631 | 1.000 / 1.000 | 1.000 / 1.000 |
| EV08 | fact | 1.000 / 0.920 | 1.000 / 0.920 | 1.000 / 0.920 |
| EV09 | figure | 0.500 / 0.631 | 1.000 / 1.000 | 1.000 / 1.000 |
| EV10 | cross-paper comparison | 0.333 / 0.693 | **0.000 / 0.613** | 0.167 / 0.605 |
| EV11 | table | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 |
| EV12 | formula | 0.500 / 0.631 | 0.500 / 0.631 | 0.500 / 0.631 |

## EV10 failure recovery

EV10 requires complementary evidence from both BERT and GPT-3. Dense ranks
those chunks at 3 and 2. The pure reranker moves the BERT evidence to rank 1
but pushes the required GPT-3 paragraph to rank 20, so the complete evidence
set is absent from Top-10.

Weighted RRF `2:1` places the BERT and GPT-3 evidence at ranks 2 and 6. This
restores complete-evidence Hit@10, but the evidence set becomes complete later
than in Dense (rank 6 instead of rank 3). This explains the single paired MRR
and nDCG loss and should remain a named regression case in future tests.

## Interpretation and next gate

The experiment supports Rank Fusion over replacing Dense order with the pure
reranker order. The `2:1` weight is only a development-set choice, however.
Selecting it and reporting its score on the same 14 questions introduces
selection bias.

Before production integration:

1. Add a new held-out set with unseen questions, including several cross-paper
   comparison questions.
2. Freeze `k = 60` and the `2:1` weights before evaluating that set.
3. Require the same four gates and explicitly require EV10-like complete
   evidence coverage.
4. If held-out validation passes, integrate the fusion behind a feature flag
   and add an offline Dense fallback for reranker service failures.

## Reproduction

```powershell
$corpusPath = "<path-to-parser-artifacts>"

python -B scripts\evaluate_rank_fusion.py `
  docs\evaluation\evidence-gold-v1.json `
  --corpus $corpusPath `
  --candidate-k 20 `
  --top-k 10 `
  --rrf-k 60 `
  --reranker-model qwen3-rerank `
  --output docs\evaluation\rank-fusion-v1-results.json
```
