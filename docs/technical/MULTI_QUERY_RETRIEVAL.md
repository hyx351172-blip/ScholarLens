# ScholarLens Multi-query Retrieval

## Status

The backend prototype is implemented behind an opt-in request flag. Existing
clients continue to use single-query Dense retrieval because
`use_multi_query=false` by default.

The retrieval selector reached complete evidence Hit@10 with the explicit v3
development queries. A live `qwen3-vl-plus` planner run preserved all target
pairs but initially reached only 50% exact strict evidence Hit@10. Human review
confirmed five same-paper alternative evidence chunks; replaying the persisted
live results against the appended Gold sets reached 100%. A subsequent fresh
live planner plus Milvus rerun also reached 100%, so the development retrieval
gate now passes. Full-v3 review and a fresh held-out gate are still required.

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
- unique canonical targets (one query per target);
- a nonempty target and standalone question;
- no duplicate question or verbatim copy of the original comparison;
- no subquery longer than 500 characters.

Invalid planner JSON receives one repair attempt within the original timeout
budget. The system falls back to the original Dense query when planning or its
repair times out, the repaired plan remains invalid, the plan exceeds the
available Top-K reserve budget, or any target retrieval fails or returns no
candidates. Failure traces expose only an error type, not provider responses or
credentials.

## Live development result

The latest live run is recorded in
`docs/evaluation/query-planner-live-v3-results.json` and its Markdown summary.

- valid plan rate: 100%;
- complete target rate: 100%;
- exact strict evidence Hit@10: 50%;
- mean exact evidence recall: 75%;
- required source-paper coverage: 100% (diagnostic only, not a release gate);
- mean planner latency: 4.509 seconds;
- mean end-to-end planner plus retrieval latency: 7.358 seconds.

MQ01, MQ02, and MQ05 retrieved apparently relevant alternative chunks from the
correct papers but missed the single annotated Gold chunk. These candidates
were accepted by the project owner on 2026-09-23 and appended without replacing
the original Gold sets. The persisted v3 live run was then re-scored in
`docs/evaluation/query-planner-live-v4-replay-results.json`:

- strict evidence Hit@10: 100%;
- mean evidence recall: 100%;
- valid-plan and complete-target rates: 100%;
- acceptance checks: PASS.

The replay report is deliberately labelled `persisted_retrieval_replay`; it is
not evidence of a fresh successful provider/vector-store run.

The required fresh rerun is recorded in
`docs/evaluation/query-planner-live-v4-results.json`:

- valid plan and complete target rates: 100%;
- strict evidence Hit@10 and mean evidence recall: 100%;
- evidence-set MRR: 0.1852;
- mean nDCG: 0.5949;
- mean planner latency: 3.854 seconds;
- mean retrieval latency: 2.912 seconds;
- mean end-to-end latency: 6.766 seconds;
- fallback count: zero;
- acceptance checks: PASS.

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

1. Complete the remaining full-v3 question/subquery review, then add
   answer-level citation completeness tests over the selected context.
2. Freeze the implementation and validate once on a fresh v4 held-out set.
3. Add the frontend toggle and a compact retrieval Trace only after the
   held-out gate passes.
