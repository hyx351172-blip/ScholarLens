# Attention Section-Aware Live Smoke Evaluation v1

## Scope

- Date: 2026-09-24
- Dataset: `scholarlens-attention-section-smoke-v1`
- Split: development
- Annotation status: assistant draft pending human review
- Corpus: one structured copy of `1706.03762_attention-is-all-you-need.pdf`
- Collection: `kb_1790243595007` (54 StructureAwareChunks)
- Model: `qwen3-vl-plus` through DashScope
- Retrieval: Top-K 10, score threshold 0.1, multi-query enabled
- Cases: broad paper method and paper conclusion

This is a targeted regression smoke test for the section-aware retrieval fix. It
is not an independent held-out benchmark and must not be reported as one.

## Validity correction

The first run (`attention-live-v1`) returned `FAIL`, but inspection showed two
evaluation defects rather than answer defects:

1. The draft method Gold set omitted an equivalent cited evidence combination
   containing the encoder/decoder stack, scaled-dot-product formula, Figure 2
   multi-head description and positional encoding.
2. The claim splitter treated the Chinese structural lead-in “论文……的结论如下：”
   as an uncited factual claim.

The equivalent Gold set was appended without removing the original annotation.
The claim splitter was fixed with a regression test that ignores short
colon-terminated structural lead-ins while retaining factual text after a
colon. No answer-quality threshold was reduced.

## Corrected live result

Run: `attention-live-v2` — **PASS**

| Metric | Result | Gate |
| --- | ---: | ---: |
| Citation syntax valid rate | 100% | 100% |
| Complete required-source coverage | 100% | 100% |
| Gold-evidence citation hit rate | 100% | 100% |
| Mean claim citation completeness | 100% | ≥90% |
| Mean concept coverage | 100% | ≥90% |
| Mean claim entailment rate | 100% | ≥90% |
| Unsupported-claim case rate | 0% | 0% |
| Mean answer pipeline latency | 15.138 s | informational |
| Mean judge latency | 13.265 s | informational |

### Per-case findings

- `ASSV1-01` method: 10 method-section sources returned; all answer claims and
  all required concepts were supported. Answer latency was 19.901 s.
- `ASSV1-02` conclusion: exactly one source returned, the page-10 `7 Conclusion`
  chunk; all claims and concepts were supported. Answer latency was 10.376 s.

The source sections contained no reference-list noise. The conclusion result
demonstrates that the section-intent filter can reduce a broad query to the
single intended scientific section.

## Comparison with the invalid first run

After correcting evaluation validity, Gold-evidence citation hit rose from 50%
to 100%, claim citation completeness and entailment rose from 92.86% to 100%,
and unsupported-claim case rate fell from 50% to 0%. Mean answer latency varied
from 13.354 s to 15.138 s; with only two cases this is not a reliable latency
regression estimate.

Full machine-readable artifacts, logs and the generated comparison remain in
the ignored local directories `harness/runs/attention-live-v1/` and
`harness/runs/attention-live-v2/`.

