# ScholarLens Chunker v2 Dense Retrieval Smoke Baseline

## Scope

- Date: 2026-09-22
- Collection: `kb_1790061860190`
- Corpus: 19 scientific papers
- Chunks: 2,057 (`ScientificChunk` schema `1.1`)
- Chunk budget: target 600 tokens, maximum 900 tokens
- Retrieval: `text-embedding-v4` + Milvus COSINE, Top-K 10
- Generation and reranking: not included

This is a document-level dense-retrieval smoke test. It verifies that the new
Chunker output can be embedded, indexed, searched, and traced back to paper,
page, section, content type, and stable chunk ID. It is not a strict
evidence-level Recall@K benchmark because the questions do not yet have
human-annotated gold chunk IDs.

## Results

| Metric | Result |
|---|---:|
| Indexed papers | 19/19 |
| Indexed chunks | 2,057 |
| Maximum retrieval-text length | 4,580 characters |
| Chunks over 12,000 characters | 0 |
| Test questions | 10 |
| Document Recall@10 | 100% |
| Hit@1 | 100% |
| MRR | 1.000 |
| Mean retrieval latency | 2.276 s |
| Median retrieval latency | 2.255 s |

Nine questions target one paper. The comparison question targets both BERT and
GPT-3: GPT-3 ranked first and BERT first appeared at rank three, so both sides
were present in the returned context.

The top results also exercised structure-aware evidence types. For example,
the Donut and LayoutLMv3 questions ranked bound Figure chunks first, while the
FlashAttention Top-10 included paragraph, Figure, Table, Abstract, and Formula
chunks with page and section provenance.

## Failure found during indexing

The first indexing attempt stopped on the GPT-3 paper when the embedding API
returned HTTP 400. A Figure chunk was below the 900-token budget but contained
about 33,000 characters because PDF layout alignment had been preserved as a
large run of horizontal spaces. Token budgeting alone therefore did not protect
the provider request-size limit.

Chunk construction now collapses horizontal layout whitespace while preserving
line boundaries. The affected retrieval text fell to about 2,472 characters,
the regression test passes, and the clean rerun indexed all 19 papers. The
partial failed test collection was removed; existing user knowledge bases and
Docker data volumes were not overwritten.

## Interpretation

The Chunker v2 output is ready for the next retrieval iteration: the complete
corpus can be indexed, metadata survives the Milvus boundary, and the initial
document-level retrieval set passes. These perfect scores should not be treated
as production RAG accuracy because the questions deliberately name distinctive
paper concepts and the gold labels are paper-level.

The next meaningful gate is a human-annotated evidence set containing expected
`chunk_id`/page pairs, including tables, formulas, figures, cross-paper
comparisons, ambiguous questions, and unanswerable questions. That set can then
measure strict Recall@K, MRR, nDCG, citation accuracy, and answer faithfulness.

Machine-readable results are saved in
`docs/evaluation/dense-retrieval-chunker-v2.json`; the index manifest is saved
in `docs/evaluation/chunker-v2-index-manifest.json`.
