# Claim-to-citation Held-out v5 — Human Review

> **Do not run this held-out split before every item is reviewed and confirmed.**

## Dataset summary

- Cases: 11
- Claims: 13
- Supported labels: 5
- Unsupported labels: 8
- Prior Gold chunk overlap: 0
- Exact prior-question overlap: 0
- Current status: `pending_human_review` / `consumed=false`

For each case, verify the question, candidate answer, claim boundary, citation binding, support label, rationale, and evidence excerpt.

## CCHV5-01 — correct_single_real_evidence

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** How does LoRA parameterize a weight update during adaptation?

**Reference answer:** LoRA freezes the pretrained weight and represents its update as a low-rank product BA.

**Candidate answer:** LoRA freezes the pretrained weight and represents its update as the low-rank product BA [S1].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: LoRA freezes the pretrained weight and represents its update as the low-rank product BA [S1]. | S1 | supported | S1 explicitly states that W0 is frozen and the update is represented as BA. |

### Evidence

**S1 — 2106.09685_lora.pdf**, page 4, `4 OUR METHOD > 4.1 LOW-RANK-PARAMETRIZED UPDATE MATRICES`

- Chunk: `e9a0d3128767db616085dc0f4e6e455e672e89af823e8ed1282793682787395a:paragraph:block_000053:part_0001`
- SHA-256: `263031d2f521389ace055873ff3ed4ed9e62dd1d203da7f3568f2c047b331781`

> LORA: LOW-RANK ADAPTATION OF LARGE LANGUAGE MODELS 4 OUR METHOD > 4.1 LOW-RANK-PARAMETRIZED UPDATE MATRICES A neural network contains many dense layers which perform matrix multiplication. The weight matrices in these layers typically have full-rank. When adapting to a specific task, Aghajanyan et al. (2020) shows that the pre-trained language models have a low 'instrisic dimension' and can still learn efficiently despite a random projection to a smaller subspace. Inspired by this, we hypothesize the updates to the weights also have a low 'intrinsic rank' during adaptation. For a pre-trained weight matrix W 0 ∈ R d × k , we constrain its update by representing the latter with a low-rank decomposition W 0 +∆ W = W 0 + BA , where B ∈ R d × r , A ∈ R r × k , and the rank r ≪ min( d, k ) . During training, W 0 is frozen and does not receive gradient updates, while A and B contain trainable parameters. Note both W 0 and ∆ W = BA are multiplied with the same input, and their respective outpu…

## CCHV5-02 — wrong_citation_correct_real_evidence_elsewhere

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** What makes Mamba selective and how is it computed efficiently?

**Reference answer:** Mamba makes SSM parameters input-dependent and uses a hardware-aware recurrent scan without materializing the expanded state.

**Candidate answer:** Mamba makes SSM parameters input-dependent and computes them with a hardware-aware recurrent scan [S1].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: Mamba makes SSM parameters input-dependent and computes them with a hardware-aware recurrent scan [S1]. | S1 | unsupported | The claim cites S1 about FlashAttention; the matching Mamba evidence exists only in uncited S2. |

### Evidence

**S1 — 2205.14135_flashattention.pdf**, page 2, `1 Introduction`

- Chunk: `ca7f9fda10b90fc05dd291a3accc85e9c1a4a860b99b31928dab03ed3fcb14e4:paragraph:block_000013:part_0001`
- SHA-256: `fbd5e2bcbb29915c606a45895fe6799bd1014c80b3ad0eb56a049c2a40cbbfd6`

> FlashAttention : Fast and Memory-Efficient Exact Attention with IO-Awareness 1 Introduction GPUs, compute speed has out-paced memory speed [61, 62, 63], and most operations in Transformers are bottlenecked by memory accesses [43]. IO-aware algorithms have been critical for similar memory-bound operations, when reading and writing data can account for a large portion of the runtime-such as database joins [71], image processing [70], numerical linear algebra [4], and more [40, 85]. However, common Python interfaces to deep learning such as PyTorch and Tensorflow do not allow fine-grained control of memory access. We propose FlashAttention , a new attention algorithm that computes exact attention with far fewer memory accesses. Our main goal is to avoid reading and writing the attention matrix to and from HBM. This requires (i) computing the softmax reduction without access to the whole input (ii) not storing the large intermediate attention matrix for the backward pass. We apply two well…

**S2 — 2312.00752_mamba.pdf**, page 2, `1 Introduction`

- Chunk: `adf70ed1803c85b1899dec3e21f3af0b124411439e8654b840ea65f7b9f52b2e:paragraph:block_000010:part_0001`
- SHA-256: `eeebe3d10d30656ce05a41af92c662c9d3241da20d844990c2b0269cfd9feda8`

> Mamba: Linear-Time Sequence Modeling with Selective State Spaces 1 Introduction We propose a new class of selective state space models , that improves on prior work on several axes to achieve the modeling power of Transformers while scaling linearly in sequence length. Selection Mechanism. First, we identify a key limitation of prior models: the ability to efficiently select data in an input-dependent manner (i.e. focus on or ignore particular inputs). Building on intuition based on important synthetic tasks such as selective copy and induction heads, we design a simple selection mechanism by parameterizing the SSM parameters based on the input. This allows the model to filter out irrelevant information and remember relevant information indefinitely. Hardware-aware Algorithm. This simple change poses a technical challenge for the computation of the model; in fact, all prior SSMs models must be time- and input-invariant in order to be computationally efficient. We overcome this with a h…

## CCHV5-03 — grouped_citations_one_real_source_supports

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** Which pre-training objectives does LayoutLMv3 combine?

**Reference answer:** LayoutLMv3 combines MLM, MIM, and word-patch alignment.

**Candidate answer:** LayoutLMv3 jointly uses MLM, MIM, and word-patch alignment [S1, S2].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: LayoutLMv3 jointly uses MLM, MIM, and word-patch alignment [S1, S2]. | S1, S2 | supported | S2 explicitly lists MLM, MIM, and WPA; grouped citation S1 is irrelevant but does not remove S2 support. |

### Evidence

**S1 — 2106.09685_lora.pdf**, page 4, `4 OUR METHOD > 4.1 LOW-RANK-PARAMETRIZED UPDATE MATRICES`

- Chunk: `e9a0d3128767db616085dc0f4e6e455e672e89af823e8ed1282793682787395a:paragraph:block_000053:part_0001`
- SHA-256: `263031d2f521389ace055873ff3ed4ed9e62dd1d203da7f3568f2c047b331781`

> LORA: LOW-RANK ADAPTATION OF LARGE LANGUAGE MODELS 4 OUR METHOD > 4.1 LOW-RANK-PARAMETRIZED UPDATE MATRICES A neural network contains many dense layers which perform matrix multiplication. The weight matrices in these layers typically have full-rank. When adapting to a specific task, Aghajanyan et al. (2020) shows that the pre-trained language models have a low 'instrisic dimension' and can still learn efficiently despite a random projection to a smaller subspace. Inspired by this, we hypothesize the updates to the weights also have a low 'intrinsic rank' during adaptation. For a pre-trained weight matrix W 0 ∈ R d × k , we constrain its update by representing the latter with a low-rank decomposition W 0 +∆ W = W 0 + BA , where B ∈ R d × r , A ∈ R r × k , and the rank r ≪ min( d, k ) . During training, W 0 is frozen and does not receive gradient updates, while A and B contain trainable parameters. Note both W 0 and ∆ W = BA are multiplied with the same input, and their respective outpu…

**S2 — 2204.08387_layoutlmv3.pdf**, page 2, `1 INTRODUCTION`

- Chunk: `bd5395610755a49e6419c406e651906e688e7a0cfe155b3c43566469dfd641fe:paragraph:block_000029:part_0001`
- SHA-256: `f9f0790f6909763484f5bfed6a13926fe98eef01ce2d2f6ecabf216d3c2a82f7`

> LayoutLMv3: Pre-training for Document AI with Unified Text and Image Masking 1 INTRODUCTION To overcome the discrepancy in pre-training objectives of text and image modalities and facilitate multimodal representation learning, we propose LayoutLMv3 to pre-train multimodal Transformers for Document AI with unified text and image masking objectives MLMand MIM. As shown in Figure 3, LayoutLMv3 learns to reconstruct masked word tokens of the text modality and symmetrically reconstruct masked patch tokens of the image modality. Inspired by DALL-E [43] and BEiT [3], we obtain the target image tokens from latent codes of a discrete VAE. For documents, each text word corresponds to an image patch. To learn this cross-modal alignment, we propose a Word-Patch Alignment (WPA) objective to predict whether the corresponding image patch of a text word is masked. Inspired by ViT [11] and ViLT [22], LayoutLMv3 directly leverages raw image patches from document images without complex pre-processing ste…

## CCHV5-04 — uncited_claim_real_evidence_available

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** How does the neural ODE adjoint method compute gradients?

**Reference answer:** It solves an augmented ODE backward in time with low memory cost.

**Candidate answer:** The neural ODE adjoint method computes gradients by solving an augmented ODE backward in time.

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: The neural ODE adjoint method computes gradients by solving an augmented ODE backward in time. | none | unsupported | The statement is factually present in S1, but the claim contains no citation and therefore has no bound evidence. |

### Evidence

**S1 — 1806.07366_neural-ordinary-differential-equations.pdf**, page 2, `2 Reverse-mode automatic differentiation of ODE solutions`

- Chunk: `435299cc42b75f9ad43d9aa246c96d3d7bdcc3297aa57f419bdc571b9c25137c:paragraph:block_000021:part_0001`
- SHA-256: `a017069ec0a47fc5193e63624c0721d27efebf22d6df404a687b6b31182ad8d7`

> Neural Ordinary Differential Equations 2 Reverse-mode automatic differentiation of ODE solutions The main technical difficulty in training continuous-depth networks is performing reverse-mode differentiation (also known as backpropagation) through the ODE solver. Differentiating through the operations of the forward pass is straightforward, but incurs a high memory cost and introduces additional numerical error. We treat the ODE solver as a black box, and compute gradients using the adjoint sensitivity method (Pontryagin et al., 1962). This approach computes gradients by solving a second, augmented ODE backwards in time, and is applicable to all ODE solvers. This approach scales linearly with problem size, has low memory cost, and explicitly controls numerical error. Consider optimizing a scalar-valued loss function L () , whose input is the result of an ODE solver:

## CCHV5-05 — invalid_source_id_real_evidence_available

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** How are queries, keys, and values transformed in multi-head attention?

**Reference answer:** They are projected multiple times with different learned linear projections and processed in parallel.

**Candidate answer:** Multi-head attention applies different learned projections to queries, keys, and values in parallel [S9].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: Multi-head attention applies different learned projections to queries, keys, and values in parallel [S9]. | none | unsupported | S9 is outside the one-source response, so the claim has no valid bound evidence. |

### Evidence

**S1 — 1706.03762_attention-is-all-you-need.pdf**, page 4, `3 Model Architecture > 3.2 Attention > 3.2.2 Multi-Head Attention`

- Chunk: `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697:paragraph:block_000042:part_0001`
- SHA-256: `e860b2eee15312a8994ac14d2825a05f270d8221c860db0da932a5cfa8571b83`

> Attention Is All You Need 3 Model Architecture > 3.2 Attention > 3.2.2 Multi-Head Attention Instead of performing a single attention function with d model-dimensional keys, values and queries, we found it beneficial to linearly project the queries, keys and values h times with different, learned linear projections to d k , d k and d v dimensions, respectively. On each of these projected versions of queries, keys and values we then perform the attention function in parallel, yielding d v -dimensional output values. These are concatenated and once again projected, resulting in the final values, as depicted in Figure 2.

## CCHV5-06 — real_evidence_contradicts_claim

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** Does FlashAttention approximate attention and materialize the attention matrix in HBM?

**Reference answer:** No. It computes exact attention and avoids reading and writing the full attention matrix to HBM.

**Candidate answer:** FlashAttention is an approximate attention algorithm that materializes the full attention matrix in HBM [S1].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: FlashAttention is an approximate attention algorithm that materializes the full attention matrix in HBM [S1]. | S1 | unsupported | S1 says FlashAttention is exact and aims to avoid attention-matrix HBM reads and writes. |

### Evidence

**S1 — 2205.14135_flashattention.pdf**, page 2, `1 Introduction`

- Chunk: `ca7f9fda10b90fc05dd291a3accc85e9c1a4a860b99b31928dab03ed3fcb14e4:paragraph:block_000013:part_0001`
- SHA-256: `fbd5e2bcbb29915c606a45895fe6799bd1014c80b3ad0eb56a049c2a40cbbfd6`

> FlashAttention : Fast and Memory-Efficient Exact Attention with IO-Awareness 1 Introduction GPUs, compute speed has out-paced memory speed [61, 62, 63], and most operations in Transformers are bottlenecked by memory accesses [43]. IO-aware algorithms have been critical for similar memory-bound operations, when reading and writing data can account for a large portion of the runtime-such as database joins [71], image processing [70], numerical linear algebra [4], and more [40, 85]. However, common Python interfaces to deep learning such as PyTorch and Tensorflow do not allow fine-grained control of memory access. We propose FlashAttention , a new attention algorithm that computes exact attention with far fewer memory accesses. Our main goal is to avoid reading and writing the attention matrix to and from HBM. This requires (i) computing the softmax reduction without access to the whole input (ii) not storing the large intermediate attention matrix for the backward pass. We apply two well…

## CCHV5-07 — same_real_source_mixed_claims

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** What does multi-head attention do with its learned projections?

**Reference answer:** It applies multiple different learned projections in parallel, concatenates their outputs, and projects again.

**Candidate answer:** Multi-head attention applies different learned projections in parallel [S1]. It uses one shared projection and a single head [S1].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: Multi-head attention applies different learned projections in parallel [S1]. | S1 | supported | S1 explicitly describes h different learned projections whose attention operations run in parallel. |
| A2: It uses one shared projection and a single head [S1]. | S1 | unsupported | S1 describes multiple projections and heads, contradicting a single shared projection and head. |

### Evidence

**S1 — 1706.03762_attention-is-all-you-need.pdf**, page 4, `3 Model Architecture > 3.2 Attention > 3.2.2 Multi-Head Attention`

- Chunk: `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697:paragraph:block_000042:part_0001`
- SHA-256: `e860b2eee15312a8994ac14d2825a05f270d8221c860db0da932a5cfa8571b83`

> Attention Is All You Need 3 Model Architecture > 3.2 Attention > 3.2.2 Multi-Head Attention Instead of performing a single attention function with d model-dimensional keys, values and queries, we found it beneficial to linearly project the queries, keys and values h times with different, learned linear projections to d k , d k and d v dimensions, respectively. On each of these projected versions of queries, keys and values we then perform the attention function in parallel, yielding d v -dimensional output values. These are concatenated and once again projected, resulting in the final values, as depicted in Figure 2.

## CCHV5-08 — same_real_source_supported_and_fabricated_detail

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** How is SynthDoG used for Donut pre-training?

**Reference answer:** It generates synthetic document images for Chinese, Japanese, Korean, and English, with 0.5 million samples per language.

**Candidate answer:** SynthDoG generated 0.5 million samples per language for Chinese, Japanese, Korean, and English [S1]. It uses only real scanned documents and no synthetic backgrounds [S1].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: SynthDoG generated 0.5 million samples per language for Chinese, Japanese, Korean, and English [S1]. | S1 | supported | S1 states that 0.5M samples per language were generated for those four languages. |
| A2: It uses only real scanned documents and no synthetic backgrounds [S1]. | S1 | unsupported | S1 describes synthetic rendering and sampled backgrounds rather than only real scanned documents. |

### Evidence

**S1 — 2111.15664_donut.pdf**, page 5, `2 Method > 2.3 Pre-training`

- Chunk: `ad9c20523c37f53fc6d31ccb4c63dcc7b916c7340d6bb16033c9924ce70c7668:paragraph:block_000039:part_0001`
- SHA-256: `f91eb72b7f4b19e0e2fe23e6a36d35426c287ac2819511192fc52b866dcae46b`

> OCR-free Document Understanding Transformer 2 Method > 2.3 Pre-training Task. The model is trained to read all texts in the image in reading order (from top-left to bottom-right, basically). The objective is to minimize cross-entropy loss of next token prediction by jointly conditioning on the image and previous contexts. This task can be interpreted as a pseudo-OCR task. The model is trained as a visual language model over the visual corpora, i.e., document images. Visual Corpora. We use IIT-CDIP [32], which is a set of 11M scanned english document images. A commercial CLOVA OCR API is applied to get the pseudo text labels. As aforementioned, however, this kind of dataset is not always available, especially for languages other than English. To alleviate the dependencies, we build a scalable Synth etic Do cument G enerator , referred to as SynthDoG . Using the SynthDog and Chinese, Japanese, Korean and English Wikipedia, we generated 0.5M samples per language. Synthetic Document Genera…

## CCHV5-09 — wrong_method_attribution

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** Does the neural ODE gradient method use LoRA-style low-rank weight updates?

**Reference answer:** No. Neural ODE uses the adjoint sensitivity method; low-rank frozen-weight adaptation belongs to LoRA.

**Candidate answer:** Neural ODE freezes pretrained weights and injects trainable low-rank update matrices [S1].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: Neural ODE freezes pretrained weights and injects trainable low-rank update matrices [S1]. | S1 | unsupported | S1 attributes the mechanism to LoRA, not Neural ODE; S2 describes the Neural ODE adjoint method. |

### Evidence

**S1 — 2106.09685_lora.pdf**, page 4, `4 OUR METHOD > 4.1 LOW-RANK-PARAMETRIZED UPDATE MATRICES`

- Chunk: `e9a0d3128767db616085dc0f4e6e455e672e89af823e8ed1282793682787395a:paragraph:block_000053:part_0001`
- SHA-256: `263031d2f521389ace055873ff3ed4ed9e62dd1d203da7f3568f2c047b331781`

> LORA: LOW-RANK ADAPTATION OF LARGE LANGUAGE MODELS 4 OUR METHOD > 4.1 LOW-RANK-PARAMETRIZED UPDATE MATRICES A neural network contains many dense layers which perform matrix multiplication. The weight matrices in these layers typically have full-rank. When adapting to a specific task, Aghajanyan et al. (2020) shows that the pre-trained language models have a low 'instrisic dimension' and can still learn efficiently despite a random projection to a smaller subspace. Inspired by this, we hypothesize the updates to the weights also have a low 'intrinsic rank' during adaptation. For a pre-trained weight matrix W 0 ∈ R d × k , we constrain its update by representing the latter with a low-rank decomposition W 0 +∆ W = W 0 + BA , where B ∈ R d × r , A ∈ R r × k , and the rank r ≪ min( d, k ) . During training, W 0 is frozen and does not receive gradient updates, while A and B contain trainable parameters. Note both W 0 and ∆ W = BA are multiplied with the same input, and their respective outpu…

**S2 — 1806.07366_neural-ordinary-differential-equations.pdf**, page 2, `2 Reverse-mode automatic differentiation of ODE solutions`

- Chunk: `435299cc42b75f9ad43d9aa246c96d3d7bdcc3297aa57f419bdc571b9c25137c:paragraph:block_000021:part_0001`
- SHA-256: `a017069ec0a47fc5193e63624c0721d27efebf22d6df404a687b6b31182ad8d7`

> Neural Ordinary Differential Equations 2 Reverse-mode automatic differentiation of ODE solutions The main technical difficulty in training continuous-depth networks is performing reverse-mode differentiation (also known as backpropagation) through the ODE solver. Differentiating through the operations of the forward pass is straightforward, but incurs a high memory cost and introduces additional numerical error. We treat the ODE solver as a black box, and compute gradients using the adjoint sensitivity method (Pontryagin et al., 1962). This approach computes gradients by solving a second, augmented ODE backwards in time, and is applicable to all ODE solvers. This approach scales linearly with problem size, has low memory cost, and explicitly controls numerical error. Consider optimizing a scalar-valued loss function L () , whose input is the result of an ODE solver:

## CCHV5-10 — partially_supported_composite_claim

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** How does Mamba combine input-dependent selection with efficient computation?

**Reference answer:** It makes SSM parameters input-dependent and computes recurrently with a scan instead of convolution.

**Candidate answer:** Mamba makes SSM parameters input-dependent but computes them by convolution rather than a recurrent scan [S1].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: Mamba makes SSM parameters input-dependent but computes them by convolution rather than a recurrent scan [S1]. | S1 | unsupported | S1 supports input dependence but says recurrent scan instead of convolution, so the full composite claim is not entailed. |

### Evidence

**S1 — 2312.00752_mamba.pdf**, page 2, `1 Introduction`

- Chunk: `adf70ed1803c85b1899dec3e21f3af0b124411439e8654b840ea65f7b9f52b2e:paragraph:block_000010:part_0001`
- SHA-256: `eeebe3d10d30656ce05a41af92c662c9d3241da20d844990c2b0269cfd9feda8`

> Mamba: Linear-Time Sequence Modeling with Selective State Spaces 1 Introduction We propose a new class of selective state space models , that improves on prior work on several axes to achieve the modeling power of Transformers while scaling linearly in sequence length. Selection Mechanism. First, we identify a key limitation of prior models: the ability to efficiently select data in an input-dependent manner (i.e. focus on or ignore particular inputs). Building on intuition based on important synthetic tasks such as selective copy and induction heads, we design a simple selection mechanism by parameterizing the SSM parameters based on the input. This allows the model to filter out irrelevant information and remember relevant information indefinitely. Hardware-aware Algorithm. This simple change poses a technical challenge for the computation of the model; in fact, all prior SSMs models must be time- and input-invariant in order to be computationally efficient. We overcome this with a h…

## CCHV5-11 — correct_downstream_output_contract

- [ ] Question and reference answer are correct.
- [ ] Claim boundaries and citation bindings are correct.
- [ ] Support labels and rationales agree with the cited evidence only.

**Question:** How does Donut formulate downstream document tasks?

**Reference answer:** It formulates downstream tasks as token generation that is converted to JSON.

**Candidate answer:** Donut formulates downstream document tasks as token generation that can be converted into JSON [S1].

### Expected claim decisions

| Claim | Bound evidence | Label | Rationale |
|---|---|---|---|
| A1: Donut formulates downstream document tasks as token generation that can be converted into JSON [S1]. | S1 | supported | S1 explicitly describes downstream tasks as JSON prediction via generated token sequences. |

### Evidence

**S1 — 2111.15664_donut.pdf**, page 6, `2 Method > 2.4 Fine-tuning`

- Chunk: `ad9c20523c37f53fc6d31ccb4c63dcc7b916c7340d6bb16033c9924ce70c7668:paragraph:block_000046:part_0001`
- SHA-256: `daf6d3d9ecba62be8fd01090d4fc76831f54912265023cb3d908d1a81767d44b`

> OCR-free Document Understanding Transformer 2 Method > 2.4 Fine-tuning After the model learns how to read , in the application stage (i.e., fine-tuning), we teach the model how to understand the document image. As shown in Figure 3, we interpret all downstream tasks as a JSON prediction problem. The decoder is trained to generate a token sequence that can be converted into a JSON that represents the desired output information. For example, in the document classification task, the decoder is trained to generate a token sequence [START class][memo][END class] which is 1-to-1 invertible to a JSON { 'class': 'memo' } . We introduce some special tokens (e.g., [memo] is used for representing the class 'memo'), if such replacement is available in the target task.

## Final owner confirmation

- [ ] I reviewed all 11 cases and 13 claim labels.
- [ ] I confirm that labels use only each claim's bound cited evidence.
- [ ] I authorize changing the dataset to `human_verified` and executing it once.
