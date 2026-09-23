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
reference answer and required concepts determine concept coverage. Every parsed factual
claim receives a stable request-local `A1`, `A2`, ... identifier and a separate evidence
bundle containing only the `[Sx]` snippets cited inside that claim. The judge must report
every concept and claim exactly once with a boolean decision and a reason.

Evidence from another claim is not included as a fallback. If a claim has no valid cited
evidence because it is uncited or cites only invalid source IDs, a deterministic policy
marks it unsupported even if the judge or reference answer agrees with the statement.
The LLM therefore handles semantic entailment only after citation-to-evidence binding has
been enforced in code.

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
| Mean claim entailment | at least 90% |
| Cases with unsupported claims | at most 1/6 |

## Claim-entailment development contract

The independent synthetic development set can be validated without API calls:

```powershell
python -B scripts/evaluate_claim_citation_entailment.py --validate-only
```

Run the semantic development judge with:

```powershell
python -B scripts/evaluate_claim_citation_entailment.py `
  --output docs/evaluation/claim-citation-entailment-dev-v1-results.json `
  --markdown-output docs/evaluation/claim-citation-entailment-dev-v1.md
```

It contains seven purpose-built scenarios and eight claim decisions: correct citations,
a wrong citation while the correct source exists elsewhere, grouped citations, no citation,
an invalid source ID, contradictory evidence, and two claims citing the same source where
only one is supported. The accepted run achieved 100% claim accuracy, case exact match,
unsupported-claim recall, and supported-claim recall.

## Held-out v5 draft

`claim-citation-entailment-heldout-v5.json` is a frozen claim-level held-out
dataset built from exact indexed ScholarLens chunks. It contains 11
scenarios and 13 claim decisions, with five supported and eight unsupported
labels. Its source chunk IDs do not overlap Gold evidence from v1 through v4,
and every embedded source text carries a SHA-256 integrity hash.

The draft initially blocked execution until the project owner verified it and
explicitly authorized one evaluation plus transmission of the evidence excerpts
to DashScope. The completed run passed all gates: 11/11 cases, 13/13 claim
decisions, 100% supported-claim recall, and 100% unsupported-claim recall. The
dataset is now `human_verified` and `consumed=true`; the evaluator rejects any
rerun, and v5 must not be used for tuning.

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

1. Build a new human-reviewed claim-level held-out set not used during evaluator development.
2. Render `[Sx]` as a frontend link to filename, page and `chunk_id` evidence.
3. Evaluate an independent judge model or add human claim-level grounding review.
4. Add production observability for invalid or missing citations without storing sensitive
   paper text in logs.
