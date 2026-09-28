# Browser acceptance failure repair

Repair the actual 2026-09-27 browser observations without rewriting that report or consuming its exhausted generation budget. This is an incremental fix, not a new architecture or benchmark.

- AC-4901: With default UI settings and an explicit catalog-resolved two/three-paper scope, independently retrieve each paper without requiring the paid LLM planner. Preserve named-paper coverage within Top-K, including Top-K=2 for two papers. A single-paper request remains scoped as before.
- AC-4902: If the budget cannot cover the requested papers or any named paper has no selected evidence, refuse before generation with a diagnostic trace, in both JSON and NDJSON paths. Never silently treat one paper as the complete comparison.
- AC-4903: Generation receives only bounded historical user questions as identity context, with old source markers removed. Prior assistant assertions/system instructions are not current evidence. Apply this history boundary to both answer modes.
- AC-4904: Legacy comparison answers must cite evidence from each resolved requested paper, otherwise return evidence-insufficient. This is document coverage, not semantic entailment or proof that each sentence uses the right citation.
- AC-4905: Render inline/display LaTeX using the existing Markdown pipeline, keep citation markers clickable outside math, preserve literal code/pre-existing links, and do not allow raw HTML or trusted KaTeX external commands.
- AC-4906: At narrow widths, provide knowledge-base selection, new chat and history selection. Changing knowledge base starts a separate conversation; block switching/new/deleting sessions during an active generation so results cannot be attached to another context.

Plan: reproduce the default-query failure with offline stubs -> bounded catalog plan and coverage gate -> history/citation checks -> math/responsive UI -> regression/build and cached-answer browser checks. Reuse the current checkout, preserve existing uncommitted acceptance artifacts. No commit, push or paid live retest without separate direction.

Compatibility: existing API fields/default answer mode remain. `use_multi_query=false` continues to disable LLM planning but no longer disables deterministic named-paper coverage: up to original + three filtered embedding searches may occur. This changes query cost, not model/provider credentials. More than three named papers or too-small Top-K fail closed instead of silently dropping targets. Trace gains coverage status/missing documents. Generic unnamed multi-paper requests are not solved by this deterministic alias fix.

The PDF URL already identifies the file/page correctly; PDF viewer availability is outside these fixes and remains pending ordinary Chrome/Edge verification. Historical measurements remain historical, and structural regressions do not establish live answer quality.
