# Answer Citation Contract and Evaluation

## Purpose

ScholarLens must distinguish a fluent answer from an evidence-grounded answer. This
feature gives each selected retrieval result a stable, request-local source identifier
and evaluates whether generated scientific claims cite the evidence actually supplied to
the model.

This is a backend and development-evaluation feature. The frontend does not yet turn a
citation into a clickable PDF/page link, and the current development set is not a fresh
held-out release benchmark.

## Runtime contract

`ChatService.format_context` numbers the final selected context in display order:

```text
[S1] 来源: paper-a.pdf(第2页) | 相关度: 0.913
...

[S2] 来源: paper-b.pdf(第4页) | 相关度: 0.887
...
```

The same identifier is returned as the additive optional `source_id` field in streaming
and non-streaming source records. The identifier is request-local: `[S1]` always maps to
the first source in that response, but is not a persistent database identifier. Persistent
provenance remains in `metadata.chunk_id`, filename, page and structural metadata.

The default answer prompt requires:

- every factual sentence or list item to end with one or more real source IDs;
- introductory, transitional and summary claims to follow the same rule;
- comparison answers to cite evidence for every target;
- explicit insufficiency rather than completion from outside knowledge;
- no unused bibliography appended to the answer.

## Evaluation design

Run the live development evaluation with:

```powershell
python -B scripts/evaluate_answer_citations.py `
  docs/evaluation/evidence-gold-v3-multi-query-dev.json `
  --output docs/evaluation/answer-citations-v4-results.json `
  --markdown-output docs/evaluation/answer-citations-v4.md
```

Each case executes the production path: automatic query planning, parallel retrieval,
coverage-aware context selection and non-streaming answer generation. It then applies two
separate evaluation layers.

### Deterministic layer

- citation IDs parse correctly and refer only to returned sources;
- all required papers are cited;
- at least one complete Gold evidence set is cited;
- factual claim units contain an inline citation;
- cited sources come from the required paper set.

The claim parser ignores pure Markdown headings and structural lead-ins, preserves common
academic abbreviations such as `et al.`, and still counts short factual claims carrying an
invalid citation. Citation syntax and provenance checks never depend on an LLM judge.

### Semantic diagnostic layer

The configured model is used at temperature zero as a development-time judge. The short
reference answer and required concepts determine concept coverage. Retrieved `[Sx]`
snippets determine whether a cited claim is grounded. A detail is not labelled unsupported
merely because the short reference answer omits it.

Retrieved text is delimited as untrusted quoted data, and the judge is told not to follow
instructions contained in it. The raw provider response and API credentials are never
serialized into reports.

This same-model judgement is a diagnostic, not a substitute for human review or an
independent held-out evaluation.

## Acceptance thresholds

| Check | Threshold |
|---|---:|
| Valid citation syntax | 100% of cases |
| Complete required-paper coverage | 100% of cases |
| Complete Gold evidence cited | at least 5/6 cases |
| Mean claim citation completeness | at least 90% |
| Mean required-concept coverage | at least 90% |
| Cases with unsupported claims | at most 1/6 |

## Development result

The accepted run is
[`answer-citations-v4.md`](../evaluation/answer-citations-v4.md). It passed all gates:

- citation syntax, required-paper coverage, Gold evidence citation and concept coverage:
  100%;
- mean claim citation completeness: 97.22%;
- unsupported-claim case rate: 0%;
- mean answer pipeline latency: 21.666 seconds.

Earlier reports are retained as experiment history. V1 exposed missing sentence-level
citations. V2 showed that prompt tightening alone was insufficient. V3 passed deterministic
citation checks but exposed a judge-design error: grounding had been judged against an
abbreviated reference answer rather than the retrieved evidence. V4 corrected that boundary
and passed without lowering any threshold.

## Remaining work

1. Build a new human-reviewed held-out set not used during prompt or evaluator development.
2. Render `[Sx]` as a frontend link to filename, page and `chunk_id` evidence.
3. Evaluate an independent judge model or add human claim-level grounding review.
4. Add production observability for invalid or missing citations without storing sensitive
   paper text in logs.
