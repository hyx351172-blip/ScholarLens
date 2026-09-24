# Retrieval and Ingestion Alignment

## Goal

Ensure the production upload path uses ScholarLens' scientific document
structure and that broad paper questions such as "what is the method" or
"what is the conclusion" retrieve the corresponding paper sections before the
answer model is called.

## Acceptance criteria

- **AC-401.1** — The upload dialog defaults to Docling scientific parsing,
  submits the VLM-repair preference explicitly, and uses the shared frontend
  service configuration instead of hard-coded localhost URLs.
- **AC-401.2** — A Docling upload with automatic chunking persists
  StructureAwareChunker output containing `retrieval_text`, `section_path`,
  stable chunk IDs and content types.
- **AC-401.3** — Single-query retrieval overfetches a bounded candidate pool,
  applies deterministic scientific-section intent scoring, and only then
  returns the requested Top-K evidence.
- **AC-401.4** — Broad Chinese or English method/conclusion questions promote
  matching section evidence while preserving the original dense score as
  retrieval provenance; unrelated questions preserve dense ordering.
- **AC-401.5** — The frontend uses the validated `0.1` dense threshold and the
  unit, integration, typecheck, build and live method/conclusion smoke checks
  pass.

## Compatibility

The upload and chat HTTP schemas remain backward compatible. Fast and full-VLM
extraction remain selectable. Retrieval responses only gain additive metadata
fields (`retrieval_score`, `section_intent`, and `section_boost`).

## Out of scope

- Implementing BM25 + Dense + RRF.
- Enabling a paid reranker by default.
- Automatically migrating every existing knowledge base.

