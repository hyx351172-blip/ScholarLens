# ScholarLens Frozen Rank Fusion Held-out Validation v2

## Decision

**No-go for production integration.**

The frozen `Dense 2.0 + qwen3-rerank 1.0` RRF configuration improves the
overall retrieval metrics over Dense, but it fails four of the six release
gates. Most importantly, none of the four cross-paper questions has its full
evidence set in the final Top-10.

The held-out split has now been consumed. Its questions, evidence, thresholds,
or fusion parameters must not be changed to obtain a passing result.

## Frozen protocol

- Dataset: `scholarlens-evidence-gold-v2-heldout`
- Annotation status: `human_verified`
- Corpus: 19 papers, 2,057 chunks
- Cases: 20 answerable and 4 unanswerable
- Dense candidate pool: Top-20
- Final output: Top-10
- RRF: `k=60`, Dense weight `2.0`, reranker weight `1.0`
- Reranker: `qwen3-rerank`
- Evaluated variants: exactly one
- External processing: explicitly authorized for this run
- Run policy: one held-out execution, with no post-result parameter tuning

## Aggregate result

| Arm | Complete-evidence Hit@10 | MRR@10 | nDCG@10 | Mean latency |
|---|---:|---:|---:|---:|
| Dense baseline | 75.00% | 0.5613 | 0.6789 | 2.332 s |
| Frozen RRF `2:1` | **80.00%** | **0.6597** | **0.7603** | 2.625 s |

RRF adds about `0.293 s` mean latency. It records 7 MRR wins, 13 ties, and no
losses against Dense. For nDCG it records 7 wins, 11 ties, and 2 losses. These
average gains do not override the missing complete evidence sets.

## Release gates

| Gate | Threshold | Result | Status |
|---|---:|---:|---|
| Overall complete-evidence Hit@10 | 100% | 80.00% | fail |
| Hit@10 non-regression vs Dense | no regression | +5 points | pass |
| MRR@10 | >= 0.75 | 0.6597 | fail |
| nDCG@10 | >= 0.82 | 0.7603 | fail |
| Added mean latency | <= 1.0 s | 0.293 s | pass |
| Cross-paper complete-evidence Hit@10 | 100% | 0.00% | fail |

## Results by question type

| Category | Cases | Dense Hit@10 | RRF Hit@10 | Dense MRR | RRF MRR | Dense nDCG | RRF nDCG |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mechanism | 6 | 100% | 100% | 0.8750 | 0.8889 | 0.9051 | 0.9167 |
| Table | 4 | 100% | 100% | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Figure | 3 | 100% | 100% | 0.4444 | 0.8333 | 0.5873 | 0.8770 |
| Formula | 3 | 66.67% | 100% | 0.2143 | 0.4537 | 0.3214 | 0.5772 |
| Cross-paper | 4 | 0% | 0% | 0.0000 | 0.0000 | 0.3552 | 0.3356 |

RRF works well for the tested single-paper cases. It moves the missed Neural
ODE adjoint formula from Dense rank 13 to final rank 9, recovering HV14 within
Top-10. All table questions remain at rank 1, and all figure questions improve
or retain their evidence ranks.

## Cross-paper failure analysis

| ID | Required evidence | Dense candidate ranks | Final RRF ranks | Failure class |
|---|---|---|---|---|
| HV17 | GPT-4 + Llama 3 | 4 + absent | 6 + absent | Dense Top-20 recall |
| HV18 | Llama 3 + DeepSeek-R1 | absent + 5 | absent + 7 | Dense Top-20 recall |
| HV19 | SAM + Docling | absent + 1 | absent + 1 | Dense Top-20 recall |
| HV20 | Docling + structured tables | 3 + 19 | 3 + 15 | coverage/final Top-10 |

Three failures occur before reranking: one required paper's Gold Chunk is
absent from the Dense Top-20 candidate pool. A reranker or a different RRF
weight cannot recover evidence it never receives. HV20 contains both Gold
Chunks in the candidate pool, but independent passage ranking leaves the
second paper at rank 15 instead of selecting a complementary cross-paper
evidence set.

## Engineering conclusion

Do not tune the RRF weight on this held-out set. The next retrieval feature
should target multi-evidence coverage rather than ranking weights:

1. decompose explicit comparison questions into paper- or entity-specific
   subqueries;
2. retrieve candidates independently for each subquery;
3. merge and deduplicate the candidate pools;
4. select the final context with a coverage-aware rule that preserves evidence
   from each comparison target;
5. develop and tune on a new development set, then validate once on another
   untouched held-out set.

## Execution record

The following command records the frozen configuration used for this completed
run. Re-running it would be reproducible, but would not create a new independent
held-out result.

```powershell
$corpusPath = "<path-to-parser-artifacts>"

python -B scripts\evaluate_rank_fusion.py `
  docs\evaluation\evidence-gold-v2-heldout.json `
  --corpus $corpusPath `
  --candidate-k 20 `
  --top-k 10 `
  --rrf-k 60 `
  --variant rrf_dense_2x `
  --evaluation-role heldout `
  --reranker-model qwen3-rerank `
  --output docs\evaluation\rank-fusion-heldout-v2-results.json
```
