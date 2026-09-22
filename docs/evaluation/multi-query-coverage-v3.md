# ScholarLens Multi-query Coverage Development Evaluation v3

## Decision

**Go for an automatic query-planner prototype; not yet a production release.**

On this six-question cross-paper development set, multi-query retrieval raised
complete-evidence Hit@10 from `16.67%` to `100%` with no per-question
regressions. The result establishes that independent paper-target retrieval and
coverage-aware context allocation can repair the failure mode seen in the
consumed v2 held-out run.

This is a tuned development result. It must not be presented as independent
held-out performance.

## Protocol

- Dataset: `scholarlens-evidence-gold-v3-multi-query-dev`
- Split: development
- Cases: 6 cross-paper questions, each requiring evidence from 2 papers
- Evidence: 12 chunk references derived from the human-verified v1 set
- Annotation status: owner review pending for the new pairings and questions
- Dense candidates: Top-10 for the original question and each subquery
- Query merge: reciprocal-rank fusion, `k=60`
- Final context: Top-10
- Allocation: original-query Top-4, each target-query Top-2, then global fusion
  fill for remaining positions
- Planner: explicit dataset subqueries; no LLM planner was evaluated
- External services: none; only the local Milvus/embedding service was used

## Aggregate result

| Arm | Complete-evidence Hit@10 | Mean evidence recall | Set MRR@10 | nDCG@10 | Mean latency |
|---|---:|---:|---:|---:|---:|
| Single-query Dense | 16.67% | 58.33% | 0.0333 | 0.3584 | 2.313 s |
| Multi-query coverage | **100.00%** | **100.00%** | **0.1301** | **0.6584** | 6.911 s |
| Delta | **+83.33 points** | **+41.67 points** | **+0.0968** | **+0.3000** | +4.598 s |

Multi-query coverage records five strict-evidence wins, one tie, and zero
losses against the single-query baseline.

## Per-question result

| ID | Comparison | Dense complete | Multi-query complete |
|---|---|---:|---:|
| MQ01 | Transformer vs Mamba | no | yes |
| MQ02 | Donut vs Nougat | no | yes |
| MQ03 | CLIP vs LayoutLMv3 | no | yes |
| MQ04 | BERT pretraining vs LoRA adaptation | no | yes |
| MQ05 | Transformer attention vs FlashAttention | no | yes |
| MQ06 | BERT fine-tuning vs GPT-3 in-context learning | yes | yes |

## What the feature now proves

1. A full comparison question should not be represented by only one embedding.
2. Each comparison target needs its own candidate list.
3. Deduplication must retain query provenance and per-query rank.
4. Final selection needs both baseline safety and target quotas; pure global
   fusion can drop complementary evidence.
5. Query wording matters. Target subqueries must preserve the paper-specific
   mechanism being compared, not merely the entity name.

## Limitations

- The six questions and their subqueries were developed and refined on this
  set. The `100%` result is therefore not an unbiased generalization estimate.
- The evidence chunks came from accepted v1 annotations, but the newly paired
  comparison questions still require owner sign-off.
- The current experiment receives explicit subqueries from the dataset. It does
  not yet detect comparison questions or generate subqueries automatically.
- The three Dense calls run sequentially. The `+4.598 s` cost should fall after
  independent subquery retrieval is parallelized, but that has not been
  measured.
- Complete evidence is present, but some last-required chunks remain low in the
  final Top-10; answer generation and citation quality have not yet been tested.

## Next release gate

Before production integration:

1. owner-review the v3 development questions and evidence pairings;
2. implement a structured query planner with validation and a single-query
   fallback;
3. run target retrieval concurrently and expose provenance in the trace;
4. add answer/citation tests over the selected multi-paper context;
5. create a fresh, untouched v4 held-out set and run it exactly once after the
   implementation is frozen.

## Reproduction

```powershell
$corpusPath = "<path-to-parser-artifacts>"

python -B scripts\evaluate_multi_query_coverage.py `
  docs\evaluation\evidence-gold-v3-multi-query-dev.json `
  --corpus $corpusPath `
  --candidate-k 10 `
  --top-k 10 `
  --rrf-k 60 `
  --original-reserve 4 `
  --per-target-reserve 2 `
  --output docs\evaluation\multi-query-coverage-v3-results.json
```
