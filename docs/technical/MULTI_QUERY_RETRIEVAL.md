# ScholarLens Multi-query Retrieval

## Status

The backend prototype is implemented behind an opt-in request flag. Existing
clients continue to use single-query Dense retrieval because
`use_multi_query=false` by default.

The retrieval selector reached complete evidence Hit@10 on the tuned v3
development set. The automatic LLM planner has unit and integration coverage,
but has not yet passed a fresh independent held-out evaluation.

## Runtime flow

```text
User comparison question
  -> LLM Query Planner
  -> validated RetrievalPlan (2-3 target questions)
  -> original + target Dense searches in parallel
  -> query-level reciprocal-rank fusion and deduplication
  -> original-query reserve + per-target reserve + global fill
  -> optional existing reranker
  -> answer generation with source provenance
```

## API usage

Enable the feature on the existing `POST /chat` request:

```json
{
  "query": "Compare BERT pretraining with GPT-3 in-context learning.",
  "collection_name": "kb_1790061860190",
  "llm_config": {
    "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "<local-secret>",
    "model_name": "qwen-plus"
  },
  "top_k": 10,
  "score_threshold": 0.1,
  "use_multi_query": true,
  "multi_query_config": {
    "planner_timeout_seconds": 12,
    "max_subqueries": 3,
    "candidate_k_per_query": 10,
    "rrf_k": 60,
    "original_reserve": 4,
    "per_target_reserve": 2
  },
  "stream": false
}
```

The planner reuses the request's LLM provider and API key with temperature `0`
and at most 600 output tokens. Secrets are not added to the retrieval trace.

## Validation contract

A comparison plan is accepted only when it contains two or three subqueries
with:

- unique normalized IDs;
- a nonempty target and standalone question;
- no duplicate question or verbatim copy of the original comparison;
- no subquery longer than 500 characters.

The system falls back to the original Dense query when planning times out,
returns invalid output, exceeds the available Top-K reserve budget, or any
target retrieval fails or returns no candidates. Failure traces expose only an
error type, not provider responses or credentials.

## Context allocation

With the default final Top-10 and two targets:

- preserve the original-query Top-4 as a non-regression guard;
- preserve Top-2 from each target query;
- fill the remaining two positions by query-level RRF score;
- deduplicate by stable `chunk_id` and retain `matched_query_ids` plus
  `query_ranks` as source provenance.

For three targets, the reserve budget becomes `4 + 3 x 2 = 10`. Requests whose
Top-K is smaller than the configured budget safely use single-query retrieval.

## Response trace

Both streaming metadata and non-streaming response metadata include
`retrieval_trace` with:

- selected mode and fallback reason;
- validated plan and target subqueries;
- per-query status, result count, and latency;
- unique candidate and final context counts;
- planner latency.

Each source can additionally contain `query_rrf_score`, `matched_query_ids`,
and `query_ranks`.

If the optional reranker is enabled, it may reorder the multi-query context but
the backend raises its effective `top_n` to the selected context size. This
prevents a smaller reranker `top_n` from silently deleting one comparison
target. Single-query requests continue to honor the configured `top_n`.

## Remaining release work

1. Run the real planner against the reviewed v3 development questions and
   record planner validity, target preservation, and end-to-end latency.
2. Add answer-level citation completeness tests over the selected context.
3. Freeze the implementation and validate once on a fresh v4 held-out set.
4. Add the frontend toggle and a compact retrieval Trace only after the
   held-out gate passes.
