# ScholarLens Multi-query Development Set v3 — Review Sheet

## Status and scope

`Review pending`

This is a **development** set for the cross-paper retrieval feature. It does
not replace or modify the consumed v2 held-out set. All evidence chunks were
previously accepted in the human-verified v1 set, but the new comparison
questions, paired evidence sets, and retrieval subqueries still require a
final owner review before the annotation status can be changed.

The explicit subqueries are an evaluation oracle for retrieval orchestration,
not a claim that a production query planner is already implemented.

## What to verify

For each case, confirm that:

1. both paper-specific subqueries preserve the meaning of the original query;
2. the two Gold chunks together support the complete expected answer;
3. neither Gold chunk requires unsupported inference from the other paper;
4. the comparison is useful and natural for a scientific-paper assistant.

## Cases

| ID | Comparison | Evidence sources | Review |
|---|---|---|---|
| MQ01 | Transformer vs Mamba sequence modeling | EV01 + EV06 | ☐ |
| MQ02 | Donut vs Nougat OCR-free conversion | EV07 + EV08 | ☐ |
| MQ03 | CLIP vs LayoutLMv3 cross-modal learning | EV04 + EV09 | ☐ |
| MQ04 | BERT pretraining vs LoRA adaptation | EV02 + EV03 | ☐ |
| MQ05 | Transformer attention vs FlashAttention IO optimization | EV01 + EV05 | ☐ |
| MQ06 | BERT fine-tuning vs GPT-3 in-context learning | EV10 | ☐ |

## Reviewer sign-off

- Reviewer: pending
- Date: pending
- Cases accepted: pending
- Cases revised: pending
- Notes: pending
