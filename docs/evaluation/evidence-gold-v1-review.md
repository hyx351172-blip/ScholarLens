# ScholarLens Evidence Gold v1 — Human Review Sheet

## Review status

`Human verified on 2026-09-22`

This sheet accompanies `evidence-gold-v1.json`. A reviewer should verify each
question, reference answer, page, and evidence chunk against the source PDF.
Only after review should `annotation_status` be changed to `human_verified`.

## Acceptance rules

For each answerable case, confirm that at least one complete evidence set:

1. contains enough information to answer every required concept;
2. does not require unsupported inference;
3. points to the correct paper, page, section, and evidence type;
4. remains understandable without unrelated surrounding chunks.

For an unanswerable case, confirm that the requested exact fact or comparison
is not stated in the indexed corpus. A semantically related retrieval result is
not evidence that the question is answerable.

## Cases

| ID | Type | Evidence target | Expected answer summary | Review |
|---|---|---|---|---|
| EV01 | mechanism | Transformer abstract or Background + Positional Encoding | attention/self-attention replaces recurrence and convolution; positions are encoded | ☑ |
| EV02 | fact | BERT §3.1, page 4 | MLM and NSP | ☑ |
| EV03 | mechanism | LoRA Introduction or Equation 3 context | freeze W0; learn low-rank BA | ☑ |
| EV04 | mechanism | CLIP §3.1.2, page 6 | image/text embeddings + cosine similarity + text-derived classifier | ☑ |
| EV05 | Figure/mechanism | FlashAttention Figure 1 or §3 | tiled SRAM computation avoids HBM materialization while remaining exact | ☑ |
| EV06 | mechanism | Mamba abstract | input-dependent selective SSM with linear scaling | ☑ |
| EV07 | architecture | Donut §2.2, page 4 | Swin visual encoder + BART decoder, no OCR | ☑ |
| EV08 | fact | Nougat abstract or conclusion | rasterized scientific pages to markup | ☑ |
| EV09 | Figure | LayoutLMv3 Figure 3 | MLM, MIM, WPA | ☑ |
| EV10 | cross-paper | BERT appendix + GPT-3 introduction | fine-tuned bidirectional pretraining vs in-context autoregressive learning | ☑ |
| EV11 | Table | Nougat Table 1 | BLEU 89.1, F1 93.1 | ☑ |
| EV12 | Formula | LoRA Equation 3 context | ΔW=BA; A Gaussian, B zero; α/r scaling | ☑ |
| EV13 | unanswerable | corpus-wide absence | refuse exact kWh values | ☑ |
| EV14 | unanswerable | corpus-wide absence | refuse exact cross-paper kg CO2e ranking | ☑ |

## Reviewer sign-off

- Reviewer: Project owner
- Date: 2026-09-22
- Cases accepted: 14/14
- Cases revised: 0
- Notes: All questions, expected answers, evidence locations, and unanswerable labels were manually reviewed and accepted.
