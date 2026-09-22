# ScholarLens Evidence Gold v2 Held-out — Human Review Sheet

## Review status

`Human verified on 2026-09-22`

Held-out execution status: `Consumed on 2026-09-22 — no-go`. The frozen run
is recorded in `rank-fusion-heldout-v2.md`. Do not use this split for further
weight, threshold, question, or evidence tuning.

This sheet accompanies `evidence-gold-v2-heldout.json`. The 24 questions were
created after the v1 Rank Fusion configuration was frozen. Do not run the
held-out experiment, change the frozen weights, or inspect retrieval rankings
until the evidence annotations have been reviewed and accepted.

## Frozen evaluation configuration

| Setting | Value |
|---|---:|
| Dense candidates | 20 |
| Final results | 10 |
| RRF k | 60 |
| Dense weight | 2.0 |
| `qwen3-rerank` weight | 1.0 |

## Acceptance rules

For every answerable case, verify that the complete evidence set:

1. supports every required concept without unsupported inference;
2. points to the correct paper, page, content type, and section;
3. remains understandable as a standalone retrieval result;
4. contains no answer that was copied from retrieval output after configuration
   selection.

For every unanswerable case, verify the requested exact fact is absent from the
19-paper corpus. A related passage or an explicit statement that details were
withheld does not turn an unsupported exact value into an answerable value.

## Cases

| ID | Type | Evidence target | Expected answer summary | Review |
|---|---|---|---|---|
| HV01 | mechanism | Neural ODE abstract | derivative-parameterized continuous depth, solved by a black-box ODE solver | ☑ |
| HV02 | mechanism | GPT-4 §3.1 | fit `L(C)=aC^b+c` on runs using up to 10,000× less compute | ☑ |
| HV03 | mechanism | SAM abstract | promptable zero-shot transfer; 1B+ masks over 11M images | ☑ |
| HV04 | mechanism | Docling §3 | backend → page AI models → aggregation/post-processing → JSON/Markdown | ☑ |
| HV05 | mechanism | Llama 3 §4 | repeated SFT followed by DPO | ☑ |
| HV06 | mechanism | DeepSeek-R1 §3 | cold start → RL → rejection sampling/SFT → second RL | ☑ |
| HV07 | table | Neural ODE Table 1 | ODE-Net: 0.42%, 0.22M, O(1) memory, O(L-tilde) time | ☑ |
| HV08 | table | Docling Table 1 | M3 Max 16-thread native versus pypdfium runtime, throughput, memory | ☑ |
| HV09 | table | Llama 3 Table 1 | all three Llama 3.1 Instruct sizes support the four listed capabilities | ☑ |
| HV10 | table | Structured Tables Table I | FY10 and FY22 are sourced from F Winston | ☑ |
| HV11 | figure | Neural ODE Figure 1 | discrete residual transforms versus a continuous ODE vector field | ☑ |
| HV12 | figure | SAM Figure 1 | promptable task, SAM, and SA-1B data engine | ☑ |
| HV13 | figure | GPT-4 Figure 2 | smaller-model HumanEval power law predicts GPT-4 | ☑ |
| HV14 | formula | Neural ODE Equation 4 | adjoint dynamics and backward-time solve | ☑ |
| HV15 | formula | Neural ODE Equation 8 | negative Jacobian trace replaces log determinant | ☑ |
| HV16 | formula | DeepSeek-R1 Equation 3 | group mean/std reward normalization | ☑ |
| HV17 | cross-paper | GPT-4 §3.1 + Llama 3 §3.1.2 | final-loss prediction versus data-mixture selection | ☑ |
| HV18 | cross-paper | Llama 3 §4 + DeepSeek-R1 §3 | compare their post-training sequences | ☑ |
| HV19 | cross-paper | SAM Figure 1 + Docling §3 | compare component responsibilities in both pipelines | ☑ |
| HV20 | cross-paper | Docling §3.3 + Table Triplification | typed JSON/Markdown documents versus canonical tables and RDF triples | ☑ |
| HV21 | unanswerable | corpus-wide absence | refuse an exact GPT-4 parameter count | ☑ |
| HV22 | unanswerable | corpus-wide absence | refuse exact SAM training electricity in kWh | ☑ |
| HV23 | unanswerable | corpus-wide absence | refuse exact Docling TableFormer A100 latency | ☑ |
| HV24 | unanswerable | corpus-wide absence | refuse same-hardware Llama 3/DeepSeek joules comparison | ☑ |

## Reviewer sign-off

- Reviewer: Project owner
- Date: 2026-09-22
- Cases accepted: 24/24
- Cases revised: 0
- Notes: All questions, expected answers, evidence locations, and unanswerable labels were manually reviewed and accepted.

The dataset remains frozen as `human_verified` and has been evaluated once.
Future retrieval changes require a new development set and another untouched
held-out split.
