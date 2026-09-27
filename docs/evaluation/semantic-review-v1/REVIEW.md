# 20题人工语义复核清单（AI草稿，尚未确认）

更新：Q02、Q06、Q08、Q17、Q20 已按用户要求暂时从本轮子集排除，下文保留原始归档。当前15题结果见 [FILTERED.md](FILTERED.md)，选择清单见 `selection-v1.json`。

这是开发集，不是独立测试集。原始标签未改写；所有语义判断待你确认。
先看题目、验收建议和原文，再展开三版回答；请在 review.json 填 review 和各输出的 judgment。
priority：先复核 Q02、Q06、Q08、Q17、Q20 的争议；另重点看 Q01、Q05 的答非所问。

## Q01 · What kind of out-of-domain data?

论文：Predicting Annotation Difficulty to Improve Task Routing and Model Performance for Biomedical Information Extraction；原标签：unanswerable
[完整上下文](contexts/Q01.md)

- 对象：universal sentence encoder
- 属性：域外预训练数据来源
- 建议验收：区分USE训练数据与GloVe词向量初始化数据；原文不明确时应说明缺失。
- 易错点：不能以Common Crawl词向量数据替代USE数据。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

The out-of-domain data used for the universal encoder is not explicitly specified beyond being “out-of-domain data” in [S1] and [S7]. The only concrete dataset mentioned in relation to pretraining is **Common Crawl**, but that is cited specifically for training the GloVe word embeddings (300d), not for the universal sentence encoder [S27]. The universal sentence encoder (USE) is referenced as pretrained (BIBREF6) in [S26] and [S28], but the paper does not state what data BIBREF6 used for its pretraining.

Thus, the kind of out-of-domain data used for the universal encoder is not specified in the provided text.

Current retrieval evidence insufficient, cannot reliably answer.

### qasper-structured-v1

程序状态：structured_passed（不是正确性判定）

common crawl data: The out-of-domain data used for initializing word embeddings is Common Crawl data, as stated in the candidate quote and confirmed by the paper's context where GloVe vectors trained on Common Crawl are used to initialize embeddings for a biomedical task. [S27]

</details>

## Q02 · What is the performance of their method?

论文：Text Summarization using Abstract Meaning Representation；原标签：unanswerable
[完整上下文](contexts/Q02.md)

- 对象：AMR summarization method
- 属性：方法性能
- 建议验收：原标签无答案，但S1/S36/S44含性能描述；先人工裁决可回答范围。
- 易错点：不得为追求标签一致而删去原文实际结果；不要臆造绝对分数。
- 争议：原始无答案标签与正文性能描述冲突
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：normalized_citations（不是正确性判定）

The proposed method achieves state-of-the-art results compared to other AMR-based text summarization routines [S1]. Specifically:

- On the AMR Bank proxy report section, their *first co-occurrence+first* model outperforms BIBREF0’s method and beats the Lead-1-AMR baseline by 0.3 ROGUE-1 F1 points [S36].
- On the CNN-Dailymail corpus, their *first-3* model yields results competitive with the Lead-3-AMR baseline [S44].
- When using gold-standard AMRs and full AMR graphs (no extraction), the method shows improved ROGUE-1 F1 scores after summary graph extraction due to increased precision and only slight recall drop [S43].

However, performance drops significantly when using automatically parsed AMRs (via JAMR) instead of gold-standard AMRs, especially for their proposed methods compared to the Lead-1-AMR baseline [S37][S38]. Human evaluation indicates that ROGUE scores do not correlate well with readability or information content, suggesting the metric underestimates quality of abstractive outputs [S40][S41].

### qasper-evidence-plan-v1

程序状态：normalized_citations（不是正确性判定）

Their method achieves state-of-the-art results compared to other AMR-based summarization routines [S1]. Specifically:

- On the AMR Bank proxy report, their **first co-occurrence+first model** obtains the best ROGUE-1 INLINEFORM0 scores and outperforms the Lead-1-AMR baseline by 0.3 ROGUE-1 INLINEFORM1 points [S36].
- All their methods outperform BIBREF0’s method on AMR Bank [S36].
- On CNN-Dailymail, using the **first-3 model**, their results are competitive with the Lead-3-AMR baseline, though significantly below the Lead-3 (non-anonymized) due to parser/generator errors [S44].
- Extracting AMR subgraphs improves ROGUE-1 precision with only slight recall drop, yielding an overall improved ROGUE-1 INLINEFORM1 [S43].

Human evaluation shows Lead-1-AMR is rated similarly to Lead-1 in overall quality, with better readability but slightly less information [S41]. However, ROGUE scores do not correlate well with human judgment, especially for abstractive outputs [S41][S42].

### qasper-structured-v1

程序状态：structured_partial（不是正确性判定）

first co-occurrence+first model on AMR Bank proxy report: Best ROGUE-1 INLINEFORM0 scores, outperforming Lead-1-AMR baseline by 0.3 ROGUE-1 INLINEFORM1 points. [S36]

first-3 model on CNN-Dailymail: Results are competitive with the Lead-3-AMR baseline. [S44]

human evaluation of Lead-1 vs Lead-1-AMR on AMR Bank: Human evaluators gave almost similar scores; Lead-1-AMR performed better on readability but dropped some information. [S41]

extracted AMR vs full AMR on ROGUE-1 F1: Extracting AMR improves ROGUE-1 precision, slightly reduces recall, resulting in overall improved ROGUE-1 INLINEFORM1. [S43]

comparison with BIBREF0 on AMR Bank: All methods outperform BIBREF0's method; best ROGUE-1 INLINEFORM0 achieved with first co-occurrence+first model. [S36]

以下候选对象证据不足：Lead-1-AMR baseline on AMR Bank、Lead-3-AMR baseline on CNN-Dailymail。

</details>

## Q03 · How does this approach compares to the state-of-the-art results on these tasks?

论文：Contextual Joint Factor Acoustic Embeddings；原标签：unanswerable
[完整上下文](contexts/Q03.md)

- 对象：CJFA/CJFS
- 属性：与SOTA的比较
- 建议验收：区分与VAE基线的比较和与完整SOTA的比较。
- 易错点：基线胜出不自动意味着超过所有SOTA。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-evidence-plan-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-structured-v1

程序状态：invalid_structure（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

</details>

## Q04 · How many layers does their model have?

论文：FacTweet: Profiling Fake News Twitter Accounts；原标签：unanswerable
[完整上下文](contexts/Q04.md)

- 对象：FacTweet model
- 属性：网络总层数
- 建议验收：只接受原文明确的层数；模块名称不足以推导总层数。
- 易错点：不要把LSTM、attention、dropout数量相加。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-evidence-plan-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-structured-v1

程序状态：invalid_structure（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

</details>

## Q05 · What are the languages represented in the DSL datasets? 

论文：Short Text Language Identification for Under Resourced Languages；原标签：unanswerable
[完整上下文](contexts/Q05.md)

- 对象：DSL datasets
- 属性：语言名称列表
- 建议验收：回答需给出具体语言名称；若文本只有数量，应指出名称缺失。
- 易错点：14种语言、6组不是语言名称列表。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-evidence-plan-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-structured-v1

程序状态：structured_passed（不是正确性判定）

DSL 2017 dataset: The DSL 2017 dataset contains 14 languages over 6 language groups. [S9]

</details>

## Q06 · How big is their created dataset?

论文：Fast Prototyping a Dialogue Comprehension System for Nurse-Patient Conversations on Symptom Monitoring；原标签：answerable
[完整上下文](contexts/Q06.md)

- 对象：created dataset（需消歧）
- 属性：数据规模
- 建议验收：参考为真实会话语料353段会话、40位说话者；应说明与模拟训练集不同。
- 易错点：不能只回答100k或评估集大小；不得静默假定created仅指模拟集。
- 争议：created指代及参考答案范围需确认
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S14

The dataset comprises a total of 353 conversations from 40 speakers (11 nurses, 16 patients, and 13 caregivers) with consent to the use of anonymized data for research. The speakers are 38 to 88 years old, equally distributed across gender, and comprise a range of ethnic groups (55% Chinese, 17% Malay, 14% Indian, 3% Eurasian, and 11% unspecified). The conversations cover 11 topics (e.g., medication compliance, symptom checking, education, greeting) and 9 symptoms (e.g., chest pain, cough) and amount to 41 hours.

来源：S27

We divide the construction of data simulation into two stages. In Section SECREF16 , we build templates and expression pools using linguistic analysis followed by manual verification. In Section SECREF20 , we present our proposed framework for generating simulated training data. The templates and framework are verified for logical correctness and clinical soundness.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

The paper does not state the total size of the *created simulated dataset* explicitly. It only specifies the sizes of three evaluation sets:  
- Base Set: 1,264 samples  
- Augmented Set: 1,280 samples  
- Real-World Set: 944 samples [S40]  

It mentions that the model was trained on the simulated data and that the optimal training size in their setting is 100k samples [S41], but this 100k figure is presented as the *optimal training sample size* used in experiments, not as a direct statement of the total created dataset size. Since no explicit total count of the simulated training dataset is given, and the 100k value is contextualized as an experimental choice rather than a dataset construction fact, the exact size of the created simulated dataset cannot be confirmed from the provided text.

Current retrieval evidence insufficient to reliably answer the question.

### qasper-structured-v1

程序状态：invalid_structure（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

</details>

## Q07 · How does car speak pertains to a car's physical attributes?

论文：Understanding Car-Speak: Replacing Humans in Dealerships；原标签：answerable
[完整上下文](contexts/Q07.md)

- 对象：car-speak
- 属性：与物理属性的关系
- 建议验收：抽象描述可以关联物理属性，但无法确定fast具体指马力还是外形；应保留歧义。
- 易错点：不能把fast唯一映射为马力；也不能只泛泛说与属性相关。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S16

The term “fast” is car-speak. Car-speak is abstract language that pertains to a car's physical attribute(s). In this instance the physical attributes that the term “fast” pertains to could be the horsepower, or it could be the car's form factor (how the car looks). However, we do not know exactly which attributes the term “fast” refers to.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

Car-speak is defined as abstract language that pertains to a car's physical attributes [S1], and examples include terms like “fast”, which may refer to physical attributes such as horsepower or form factor (e.g., sleek design) [S15][S16]. Similarly, words like “safety” and “luxury” are abstract descriptions but are associated with specific physical characteristics [S26]. The dealer translates such car-speak into concrete physical attributes (e.g., “fast” → “700 horsepower & a sleek form factor”) to make recommendations [S17].

### qasper-evidence-plan-v1

程序状态：normalized_citations（不是正确性判定）

Car-speak pertains to a car's physical attributes through abstract language that implicitly refers to those attributes, though the exact mapping is often ambiguous. For example, the term “fast” is car-speak and may refer to physical attributes such as horsepower or form factor (how the car looks), but the specific attribute(s) it denotes are not explicitly specified [S16]. Similarly, words like “safety” and “luxury” are abstract descriptions that have associated physical characteristics, though the paper does not enumerate them in detail beyond stating they are linked to physical traits [S26]. The dealer (or a model) must interpret these abstract terms and map them to concrete physical attributes (e.g., “fast” → “700 horsepower & a sleek form factor”) [S17]. Thus, car-speak is defined as abstract language *pertaining to* a car’s physical attributes, but the correspondence is indirect and context-dependent [S1][S16].

### qasper-structured-v1

程序状态：structured_passed（不是正确性判定）

car-speak: Car-speak is abstract language that pertains to a car's physical attributes. [S1]

car-speak: Car-speak is abstract language that pertains to a car's physical attribute(s); for example, 'fast' may refer to horsepower or form factor, though the exact attributes are not precisely specified. [S16]

car-speak: Words like 'safety' and 'luxury' are car-speak: abstract descriptions of cars that have associated physical characteristics. [S26]

</details>

## Q08 · Is the template-based model realistic?  

论文：Abstractive Summarization for Low Resource Data using Domain Transfer and Data Synthesis；原标签：answerable
[完整上下文](contexts/Q08.md)

- 对象：template-based synthesis model
- 属性：realistic的实验含义
- 建议验收：参考为Yes，但措辞模糊；可说明实验支持的有效性及边界，需人审是否满足题意。
- 易错点：不得擅自增加部署/规模化要求，也不得把ROUGE提高等同所有现实属性成立。
- 争议：realistic含义宽泛，不能强制二值化
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S27

Hypothesis 4 (H4) : The proposed template-based synthesis model outperforms a simple word replacement model.

来源：S40

To validate our next set of hypothesises (H3, H4. H5), we use the synthesized data in two settings: either using it for training (rows 7, 8 and 19, 20) or tuning (rows 10, 11 and 22, 23). Table TABREF13 supports H4 by showing that the proposed synthesis model outperforms the WordNet baseline in training (rows 7, 8 and 19, 20) except Stat2016, and tuning (10, 11 and 22, 23) over all courses. It also shows that while adding synthetic data from the baseline is not always helpful, adding synthetic data from the template model helps to improve both the training and the tuning process. In both CS and ENGR courses, tuning with synthetic data enhances all ROUGE scores compared to tuning with only the original data. (rows 9 and 11). As for Stat2015, R-1 and R-$L$ improved, while R-2 decreased. For Stat2016, R-2 and R-$L$ improved, and R-1 decreased (rows 21 and 23). Training with both student reflection data and synthetic data compared to training with only student reflection data yields similar improvements, supporting H3 (rows 6, 8 and 18, 20). While the increase in ROUGE scores is small, our results show that enriching training data with synthetic data can benefit both the training and tuning of other models. In general, the best results are obtained when using data synthesis for both training and tuning (rows 11 and 23), supporting H5.

来源：S41

Finally, while the goal of our template model was to synthesize data, using it for summarization is surprisingly competitive, supporting H6. We believe that training the model with little data is doable due to the small number of parameters (logistic regression classifier only). While rows 12 and 24 are never the best results, they are close to the best involving tuning. This encourages us to enhance our template model and explore templates not so tailored to our data.

来源：S42

Human Evaluation Results. While automated evaluation metrics like ROUGE measure lexical similarity between machine and human summaries, humans can better measure how coherent and readable a summary is. Our evaluation study investigates whether tuning the PG-net model increases summary coherence, by asking evaluators to select which of three summaries for the same document they like most: the PG-net model trained on CNN/DM; the model trained on student reflections; and finally the model trained on CNN/DM and tuned on student reflections. 20 evaluators were recruited from our institution and asked to each perform 20 annotations. Summaries are presented to evaluators in random order. Evaluators are then asked to select the summary they feel to be most readable and coherent. Unlike ROUGE, which measures the coverage of a generated summary relative to a reference summary, our evaluators don't read the reflections or reference summary. They choose the summary that is most coherent and readable, regardless of the source of the summary. For both courses, the majority of selected summaries were produced by the tuned model (49% for CS and 41% for Stat2015), compared to (31% for CS and 30.9% for Stat2015) for CNN/DM model, and (19.7% for CS and 28.5% for Stat2015) for student reflections model. These results again suggest that domain transfer can remedy the size of in-domain data and improve performance.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-evidence-plan-v1

程序状态：insufficient_evidence（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

### qasper-structured-v1

程序状态：invalid_structure（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

</details>

## Q09 · How does Gaussian-masked directional multi-head attention works?

论文：Attention Is All You Need for Chinese Word Segmentation；原标签：answerable
[完整上下文](contexts/Q09.md)

- 对象：Gaussian-masked directional attention
- 属性：工作机制
- 建议验收：说明邻近字符、依距离确定的高斯权重和局部性；参考允许解释query/key/value映射。
- 易错点：仅复述标准点积注意力不足。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S23

Different from scaled dot-product attention, Gaussian-masked directional attention expects to pay attention to the adjacent characters of each positions and cast the localness relationship between characters as a fix Gaussian weight for attention. We assume that the Gaussian weight only relys on the distance between characters.

来源：S22

Similar as scaled dot-product attention BIBREF24, Gaussian-masked directional attention can be described as a function to map queries and key-value pairs to the representation of input. Here queries, keys and values are all vectors. Standard scaled dot-product attention is calculated by dotting query $Q$ with all keys $K$, dividing each values by $\sqrt{d_k}$, where $\sqrt{d_k}$ is the dimension of keys, and apply a softmax function to generate the weights in the attention:

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

Gaussian-masked directional multi-head attention works by modifying standard scaled dot-product attention with two key mechanisms: a Gaussian weight matrix to emphasize local (adjacent) character relationships, and directional triangular masks to enforce forward or backward information flow.

First, a Gaussian weight matrix $G$ is introduced, where the weight $g_{ij}$ between characters $i$ and $j$ depends on their distance $dis_{ij}$ via the cumulative distribution function of a Gaussian: $g_{ij} = \Phi(dis_{ij}/\sigma)$, ensuring higher weights for closer characters and lower weights for distant ones [S24][S25]. This matrix is combined with the standard attention score matrix $QK^T$ via Hadamard product to produce the Gaussian-masked attention $AG$, weakening long-distance dependencies [S26][S27].

Second, for directional encoding (forward/backward), triangular masks are applied to restrict attention to one direction: a lower-triangular mask for forward encoder (attending only to current and prior positions) and an upper-triangular mask for backward encoder (attending only to current and later positions) [S29][S30][S31].

Finally, multi-head attention is used, where queries, keys, and values are projected into multiple heads using parameter matrices $\{W_i^q, W_i^k, W_i^v\}$, and each head applies the Gaussian-masked directional attention; outputs are concatenated and linearly transformed [S32][S33].

This design enhances the model’s ability to capture localness and directional information critical for Chinese word segmentation [S9][S14][S17][S18][S28].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

Gaussian-masked directional multi-head attention works by modifying standard scaled dot-product attention with two key components: a **Gaussian weight matrix** that encodes localness (distance-based decay), and **directional masking** (triangular masks) to enforce forward/backward directionality. Specifically:

1. It starts from scaled dot-product attention, where queries $Q$ and keys $K$ are dotted, scaled by $\sqrt{d_k}$, and softmaxed to produce attention weights [S22].

2. A Gaussian weight matrix $G$ is introduced, where the weight $g_{ij}$ between characters $i$ and $j$ depends only on their distance $dis_{ij}$ via a Gaussian cumulative distribution function:  
   $g_{ij} = \Phi\left(\frac{dis_{ij}}{\sigma}\right)$, with $\sigma$ as a hyperparameter; this ensures weight = 1 when $dis_{ij}=0$, and decays with distance [S23][S24][S25].

3. The Gaussian weight matrix $G$ is combined with the raw attention score matrix $QK^T$ via Hadamard product: $AG = \text{softmax}(QK^T \odot G)$, yielding Gaussian-masked attention that weakens long-distance relationships [S26][S27].

4. For directional encoding (forward/backward), triangular masks are applied to the self-attention sublayer to restrict attention to past or future positions respectively [S29][S30][S31].

5. Multi-head attention is then used: queries, keys, and values are projected into multiple heads, each applying the above Gaussian-masked directional attention, and results are concatenated and linearly transformed [S32][S33].

This design ensures adjacent characters have stronger influence, captures directional context, and retains the parallelizability of Transformer-style attention [S28][S17].

### qasper-structured-v1

程序状态：structured_passed（不是正确性判定）

Gaussian-masked directional multi-head attention: It maps queries and key-value pairs to input representation using scaled dot-product attention, but modifies the attention scores with a Gaussian weight matrix based on character distance. [S22]

Gaussian-masked directional multi-head attention: It focuses on adjacent characters by assigning fixed Gaussian weights based solely on inter-character distance, emphasizing localness relationships. [S23]

Gaussian-masked directional multi-head attention: It introduces a Gaussian weight matrix G to encode localness relationships between every pair of characters. [S24]

Gaussian-masked directional multi-head attention: The Gaussian weight $g_{ij}$ between characters i and j is defined via the cumulative distribution function of a Gaussian with standard deviation σ (a hyperparameter), ensuring weight=1 at distance 0 and decreasing with distance. [S25]

Gaussian-masked directional multi-head attention: It combines Gaussian weights with self-attention by taking the Hadamard product of the Gaussian weight matrix G and the QK^T score matrix. [S26]

Gaussian-masked directional multi-head attention: The resulting AG (Gaussian-masked attention) ensures long-distance character relationships are weaker than adjacent ones. [S27]

Gaussian-masked directional multi-head attention: For forward and backward encoders, a triangular matrix mask is applied to restrict attention to specific directional contexts (past or future). [S29]

Gaussian-masked directional multi-head attention: It extends standard multi-head attention by applying the Gaussian-masked directional attention mechanism across multiple heads to capture information from different subspaces. [S32]

</details>

## Q10 · What are the difficulties in modelling the ironic pattern?

论文：A Neural Approach to Irony Generation；原标签：answerable
[完整上下文](contexts/Q10.md)

- 对象：irony generation
- 属性：建模困难
- 建议验收：涵盖隐晦难理解；部分参考还包括缺少既有研究与基线。
- 易错点：保留不同参考范围，不强行要求某一句逐字匹配。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S3

Although some previous studies focus on irony detection, little attention is paid to irony generation. As ironies can strengthen sentiments and express stronger emotions, we mainly focus on generating ironic sentences. Given a non-ironic sentence, we implement a neural network to transfer it to an ironic sentence and constrain the sentiment polarity of the two sentences to be the same. For example, the input is “I hate it when my plans get ruined" which is negative in sentiment polarity and the output should be ironic and negative in sentiment as well, such as “I like it when my plans get ruined". The speaker uses “like" to be ironic and express his or her negative sentiment. At the same time, our model can preserve contents which are irrelevant to sentiment polarity and irony. According to the categories mentioned in BIBREF5 , irony can be classified into 3 classes: verbal irony by means of a polarity contrast, the sentences containing expression whose polarity is inverted between the intended and the literal evaluation; other types of verbal irony, the sentences that show no polarity contrast between the literal and intended meaning but are still ironic; and situational irony, the sentences that describe situations that fail to meet some expectations. As ironies in the latter two categories are obscure and hard to understand, we decide to only focus on ironies in the first category in this work. For example, our work can be specifically described as: given a sentence “I hate to be ignored", we train our model to generate an ironic sentence such as “I love to be ignored". Although there is “love" in the generated sentence, the speaker still expresses his or her negative sentiment by irony. We also make some explorations in the transformation from ironic sentences to non-ironic sentences at the end of our work. Because of the lack of previous work and baselines on irony generation, we implement our model based on style transfer. Our work will not only provide the first large-scale irony dataset but also make our model as a benchmark for the irony generation.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：normalized_citations（不是正确性判定）

The difficulties in modelling the ironic pattern include: (1) irony is a complicated style that is hard to model with specific style attribute words [S7]; (2) many non-ironic sentences do not have specific stylistic words, making it difficult to transfer them to ironic sentences by removing or replacing stylistic words [S9]; (3) ironic style is hard to model and describe, which complicates the design of effective generation methods [S5][S10]; and (4) the lack of large-scale irony datasets further hinders the modelling of ironic patterns [S1][S4].

### qasper-evidence-plan-v1

程序状态：normalized_citations（不是正确性判定）

The difficulties in modelling the ironic pattern include:  
- The lack of large-scale irony datasets [S1][S4];  
- Irony being a complicated style that is hard to model with specific style attribute words [S7];  
- The ironic style being inherently hard to model and describe [S5];  
- Irony being hard for the model to learn, leading to improper word generation [S53];  
- Obscurity and difficulty in understanding certain categories of irony (e.g., non-polarity-contrast types), prompting the authors to restrict focus to only the first category [S3];  
- Many non-ironic sentences lacking specific stylistic words, making style transfer via word editing impractical [S9].  

These challenges collectively make irony generation a very challenging task [S50].

### qasper-structured-v1

程序状态：invalid_structure（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

</details>

## Q11 · How do the authors define a concept map?

论文：Bringing Structure into Summaries: Crowdsourcing a Benchmark Corpus of Concept Maps；原标签：answerable
[完整上下文](contexts/Q11.md)

- 对象：concept map
- 属性：定义
- 建议验收：带标签的图；概念为节点，概念关系为边。
- 易错点：不能只称其为摘要或目录。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S3

A representation that is more in line with observed user behavior is a concept map BIBREF5 , a labeled graph showing concepts as nodes and relationships between them as edges (Figure FIGREF2 ). Introduced in 1972 as a teaching tool BIBREF6 , concept maps have found many applications in education BIBREF7 , BIBREF8 , for writing assistance BIBREF9 or to structure information repositories BIBREF10 , BIBREF11 . For summarization, concept maps make it possible to represent a summary concisely and clearly reveal relationships. Moreover, we see a second interesting use case that goes beyond the capabilities of textual summaries: When concepts and relations are linked to corresponding locations in the documents they have been extracted from, the graph can be used to navigate in a document collection, similar to a table of contents. An implementation of this idea has been recently described by BIBREF12 .

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

The authors define a concept map as “a labeled graph showing concepts as nodes and relationships between them as edges” [S3], where “labels are arbitrary sequences of tokens taken from the documents, making the summarization task extractive” [S9]. A concept can be “an entity, abstract idea, event or activity, designated by its unique label”, and good maps should be “propositionally coherent, meaning that every relation together with the two connected concepts form a meaningful proposition” [S9].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

The authors define a concept map as a labeled graph showing concepts as nodes and relationships between them as edges. Labels are arbitrary sequences of tokens taken from the documents, making the summarization task extractive; a concept can be an entity, abstract idea, event, or activity, designated by its unique label. Good maps should be propositionally coherent, meaning every relation together with its two connected concepts forms a meaningful proposition [S9]. This definition is also echoed in [S3], which describes it similarly as a labeled graph with concepts as nodes, relationships as edges, and references BIBREF5.

### qasper-structured-v1

程序状态：structured_passed（不是正确性判定）

concept map: A labeled graph showing concepts as nodes and relationships between them as edges. [S3]

concept map: A labeled graph showing concepts as nodes and relationships between them as edges; labels are arbitrary token sequences from documents, concepts can be entities, ideas, events or activities, and good maps are propositionally coherent. [S9]

</details>

## Q12 · Do they incoprorate WordNet into the model?

论文：GlossBERT: BERT for Word Sense Disambiguation with Gloss Knowledge；原标签：answerable
[完整上下文](contexts/Q12.md)

- 对象：GlossBERT
- 属性：是否及如何使用WordNet
- 建议验收：是：利用目标词WordNet义项的gloss构造context-gloss对。
- 易错点：不要与BERT本身的预训练来源混淆。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S14

BERT can explicitly model the relationship of a pair of texts, which has shown to be beneficial to many pair-wise natural language understanding tasks. In order to fully leverage gloss information, we propose GlossBERT to construct context-gloss pairs from all possible senses of the target word in WordNet, thus treating WSD task as a sentence-pair classification problem.

来源：S7

In this paper, we focus on how to better leverage gloss information in a supervised neural WSD system. Recently, the pre-trained language models, such as ELMo BIBREF14 and BERT BIBREF15, have shown their effectiveness to alleviate the effort of feature engineering. Especially, BERT has achieved excellent results in question answering (QA) and natural language inference (NLI). We construct context-gloss pairs from glosses of all possible senses (in WordNet) of the target word, thus treating WSD task as a sentence-pair classification problem. We fine-tune the pre-trained BERT model and achieve new state-of-the-art results on WSD task. In particular, our contribution is two-fold:

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

Yes, they incorporate WordNet into the model by extracting glosses (sense definitions) of all possible senses of the target word from WordNet 3.0 to construct context-gloss pairs for BERT input [S16][S25].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

Yes, they incorporate WordNet into the model by extracting sense glosses from WordNet 3.0 to construct context-gloss pairs for the WSD task [S25]. Specifically, for each target word, they extract glosses of all possible senses from WordNet and use them to form sentence-pair inputs for BERT [S14][S16][S7].

### qasper-structured-v1

程序状态：structured_partial（不是正确性判定）

GlossBERT: Yes, GlossBERT incorporates WordNet by constructing context-gloss pairs from all possible senses of the target word in WordNet, treating WSD as a sentence-pair classification problem. [S14]

context-gloss pairs: Yes, context-gloss pairs are constructed using glosses extracted from WordNet for each target word's possible senses. [S16]

WordNet 3.0: Yes, the paper uses WordNet 3.0 to extract word sense glosses, as the datasets' sense annotations are mapped to WordNet 3.0. [S25]

GlossBERT models: Yes, GlossBERT models incorporate WordNet by using context-gloss pairs derived from WordNet senses during training and inference. [S18]

method: Yes, the method constructs context-gloss pairs from glosses of all possible senses in WordNet, treating WSD as a sentence-pair classification problem. [S7]

approach: Yes, the approach constructs context-gloss pairs using WordNet glosses and converts WSD into a sentence-pair classification task. [S34]

solution: Yes, the solution constructs context-gloss pairs from WordNet glosses and converts WSD to a sentence-pair classification task. [S36]

以下候选对象证据不足：SemCor3.0。

</details>

## Q13 · How effective is their NCEL approach overall?

论文：Neural Collective Entity Linking；原标签：answerable
[完整上下文](contexts/Q13.md)

- 对象：NCEL
- 属性：整体效果
- 建议验收：在实验范围内超过多个基线，并具较好的泛化能力。
- 易错点：不可扩张为所有数据集/所有方法均最优。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S10

In experiments, we first verify the efficiency of NCEL via theoretically comparing its time complexity with other collective alternatives. Afterwards, we train our neural model using collected Wikipedia hyperlinks instead of dataset-specific annotations, and perform evaluations on five public available benchmarks. The results show that NCEL consistently outperforms various baselines with a favorable generalization ability. Finally, we further present the performance on a challenging dataset WW BIBREF19 as well as qualitative results, investigating the effectiveness of each key module.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

NCEL consistently outperforms state-of-the-art baselines across five public datasets, achieving the best performance in most cases with an average gain of 2% on Micro F1 and 3% on Macro F1 [S58]. It demonstrates strong generalization ability, performing well on both “easy” (e.g., TAC2010) and “hard” (e.g., WW) datasets, where local models or other global methods often fail [S58][S60]. On the challenging WW dataset, NCEL significantly improves over NCEL-local (its ablated version without global features), especially due to its attention and embedding modules that enhance robustness to noise [S61][S62]. Qualitative results confirm that NCEL correctly resolves ambiguous mentions (e.g., “England” as *England cricket team*) using neighbor coherence, whereas NCEL-local fails [S63].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

NCEL consistently outperforms various baselines across five datasets, with an average gain of 2% on Micro F1 and 3% on Macro F1 [S58]. It achieves the best performance in most cases and demonstrates strong generalization ability by performing well on all datasets, unlike baselines that excel on some but fail on others [S58]. It also outperforms all baseline methods on both “easy” (TAC2010) and “hard” (WW) cases [S60], and surpasses state-of-the-art collective methods when trained on Wikipedia hyperlinks [S64].

### qasper-structured-v1

程序状态：invalid_structure（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

</details>

## Q14 · What is the McGurk effect?

论文：A Surprising Density of Illusionable Natural Speech；原标签：answerable
[完整上下文](contexts/Q14.md)

- 对象：McGurk effect
- 属性：定义
- 建议验收：视觉口型影响对听觉语音的感知；音频不必改变。
- 易错点：不能描述成仅改变音频产生错觉。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S7

For the McGurk effect, we attempt an illusion for a language token (e.g. phoneme, word, sentence) $x$ by creating a video where an audio stream of $x$ is visually dubbed over by a person saying $x^{\prime }\ne x$ . We stress that the audio portion of the illusion is not modified and corresponds to a person saying $x$ . The illusion $f(x^{\prime },x)$ affects a listener if they perceive what is being said to be $y\ne x$ if they watched the illusory video whereas they perceive $x$ if they had either listened to the audio stream without watching the video or had watched the original unaltered video, depending on specification. We call a token illusionable if an illusion can be made for the token that affects the perception of a significant fraction of people.

来源：S4

In this work, we attempt to understand how susceptible humans' perceptual systems for natural speech are to carefully designed “adversarial attacks.” We investigate the density of certain classes of illusion, that is, the fraction of natural language utterances whose comprehension can be affected by the illusion. Our study centers around the McGurk effect, which is the well-studied phenomenon by which the perception of what we hear can be influenced by what we see BIBREF0 . A prototypical example is that the audio of the phoneme “baa,” accompanied by a video of someone mouthing “vaa”, can be perceived as “vaa” or “gaa” (Figure 1 ). This effect persists even when the subject is aware of the setup, though the strength of the effect varies significantly across people and languages and with factors such as age, gender, and disorders BIBREF11 , BIBREF12 , BIBREF13 , BIBREF14 , BIBREF15 , BIBREF16 , BIBREF17 , BIBREF18 , BIBREF19 .

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

The McGurk effect is a well-studied phenomenon in which the perception of what is heard is influenced by what is seen, specifically when audio and visual speech signals are mismatched. A prototypical example is that the audio of the phoneme “baa” accompanied by a video of someone mouthing “vaa” can be perceived as “vaa” or “gaa” [S4]. It occurs because human speech perception is bimodal (audio-visual) when lip reading is available [S6], and it persists even when the subject is aware of the setup, though its strength varies across individuals and contexts [S4].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

The McGurk effect is a well-studied phenomenon in which the perception of what is heard is influenced by what is seen—specifically, when audio of one phoneme/word is paired with video of someone mouthing a different phoneme/word, leading viewers to perceive a third, often different, sound (e.g., audio “baa” + video “vaa” perceived as “vaa” or “gaa”) [S4]. This effect persists even when subjects are aware of the setup, though its strength varies across individuals and contexts [S4]. It arises because human speech perception is bimodal (audio-visual) when lip reading is available, providing a compelling explanation for the confusion, unlike adversarial examples for ML systems [S6].

### qasper-structured-v1

程序状态：structured_passed（不是正确性判定）

McGurk effect: The McGurk effect is a well-studied phenomenon where the perception of what we hear is influenced by what we see; for example, audio of the phoneme 'baa' accompanied by video of someone mouthing 'vaa' can be perceived as 'vaa' or 'gaa'. [S1][S4]

</details>

## Q15 · How many categories do authors define for speaker role?

论文：Gender Representation in French Broadcast Corpora and Its Impact on ASR Performance；原标签：answerable
[完整上下文](contexts/Q15.md)

- 对象：speaker role
- 属性：类别数及名称
- 建议验收：两类：Anchors和Punctual speakers。
- 易错点：不要把定义角色的两个统计指标当作另外的类别。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S15

As pointed out by the CSA report BIBREF1, women presence tends to be marginal within the high-audience hours, showing that women are represented but less than men and within certain given conditions. It is clear that a small number of speakers is responsible for a large number of speech turns. Most of these speakers are journalists, politicians, presenters and such, who are representative of a show. Therefore, we introduce the notion of speaker's role to refine our exploration of gender disparity, following studies which quantified women's presence in terms of role. Within our work, we define the notion of speaker role by two criteria specifying the speaker's on-air presence, namely the number of speech turns and the cumulative duration of his or her speaking time in a show. Based on the available speech transcriptions and meta-data, we compute for each speaker the number of speech turns uttered as well as their total length. We then use the following criteria to define speaker's role: a speaker is considered as speaking often (respectively seldom) if he/she accumulates a total of turns higher (respectively lower) than 1% of the total number of speech turns in a given show. The same process is applied to identify speakers talking for a long period from those who do not. We end up with two salient roles called Anchors and Punctual speakers:

来源：S16

the Anchor speakers (A) are above the threshold of 1% for both criteria, meaning they are intervening often and for a long time thus holding an important place in interaction;

来源：S17

the Punctual speakers (PS) on the contrary are below the threshold of 1% for both the total number of turns and the total speech time.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

The authors define two categories for speaker role: Anchor speakers (A) and Punctual speakers (PS) [S16][S17].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

The authors define two categories for speaker role: Anchors and Punctual speakers [S15].

### qasper-structured-v1

程序状态：invalid_structure（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

</details>

## Q16 · Which architecture do they use for the encoder and decoder?

论文：Attention-based Wav2Text with Feature Transfer Learning；原标签：answerable
[完整上下文](contexts/Q16.md)

- 对象：Wav2Text encoder and decoder
- 属性：两端架构
- 建议验收：encoder含卷积、NIN、双向LSTM；decoder为单向LSTM，可补充attention。
- 易错点：必须同时覆盖编码器与解码器，不可互换方向。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S10

In this work, we use the raw waveform as the input representation instead of spectral-based features and a grapheme (character) sequence as the output representation. In contrast to most encoder-decoder architectures, which are purely based on recurrent neural network (RNNs) framework, we construct an encoder with several convolutional layers BIBREF14 followed by NIN layers BIBREF15 as the lower part in the encoder and integrate them with deep bidirectional long short-term memory (Bi-LSTM) BIBREF16 at the higher part. We use convolutional layers because they are suitable for extracting local information from raw speech. We use a striding mechanism to reduce the dimension from the input frames BIBREF17 , while the NIN layer represents more complex structures on the top of the convolutional layers. On the decoder side, we use a standard deep unidirectional LSTM with global attention BIBREF13 that is calculated by a multi-layer perceptron (MLP) as described in Eq. EQREF2 . For more details, we illustrate our architecture in Figure FIGREF4 .

来源：S17

On the top layers of the encoder after the transferred convolutional and NIN layers, we put three bidirectional LSTMs (Bi-LSTM) with 256 hidden units (total 512 units for both directions). To reduce the computational time, we used hierarchical subsampling BIBREF21 , BIBREF22 , BIBREF10 . We applied subsampling on all the Bi-LSTM layers and reduced the length by a factor of 8.

来源：S18

On the decoder side, the previous input phonemes / characters were converted into real vectors by a 128-dimensional embedding matrix. We used one unidirectional LSTM with 512 hidden units and followed by a softmax layer to output the character probability. For the end-to-end training phase, we froze the parameter values from the transferred layers from epoch 0 to epoch 10, and after epoch 10 we jointly optimized all the parameters together until the end of training (a total 40 epochs). We used an Adam BIBREF23 optimizer with a learning rate of 0.0005.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

The encoder consists of several convolutional layers followed by Network-in-Network (NIN) layers as the lower part, integrated with deep bidirectional long short-term memory (Bi-LSTM) at the higher part [S10]. Specifically, it uses four convolutional layers, two NIN layers, and three Bi-LSTMs with 256 hidden units each (total 512 units for both directions), with hierarchical subsampling applied to reduce sequence length by a factor of 8 [S16][S17].

The decoder uses a standard deep unidirectional LSTM with 512 hidden units, preceded by a 128-dimensional embedding matrix for previous characters, and followed by a softmax layer to output character probabilities; it employs global attention calculated by a multi-layer perceptron (MLP) [S10][S18].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

The encoder consists of four convolutional layers followed by two Network-in-Network (NIN) layers at the lower part, and three bidirectional LSTMs (Bi-LSTMs) with 256 hidden units each (total 512 per layer) at the higher part [S16][S17]. The decoder uses one unidirectional LSTM with 512 hidden units, preceded by a 128-dimensional embedding matrix for input characters, and followed by a softmax layer to output character probabilities [S18]. Global attention is computed via a multi-layer perceptron (MLP) on the decoder side [S10].

### qasper-structured-v1

程序状态：invalid_structure（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

</details>

## Q17 · Which parallel corpora are used?

论文：A Bayesian Model of Multilingual Unsupervised Semantic Role Induction；原标签：answerable
[完整上下文](contexts/Q17.md)

- 对象：experimental corpora
- 属性：语料名称及角色
- 建议验收：参考提及CoNLL2009英/德部分和Europarl EN-DE；区分Europarl平行句对与CoNLL训练部分。
- 易错点：不能把两者不加区别地宣称为同种平行语料。
- 争议：平行语料与实验语料角色需区分
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S35

Following titovcrosslingual, we run our experiments on the English (EN) and German (DE) sections of the CoNLL 2009 corpus BIBREF13 , and EN-DE section of the Europarl corpus BIBREF14 . We get about 40k EN and 36k DE sentences from the CoNLL 2009 training set, and about 1.5M parallel EN-DE sentences from Europarl. For appropriate comparison, we keep the same setting as in BIBREF6 for automatic parses and argument identification, which we briefly describe here. The EN sentences are parsed syntactically using MaltParser BIBREF15 and DE using LTH parser BIBREF16 . All the non-auxiliary verbs are selected as predicates. In CoNLL data, this gives us about 3k EN and 500 DE predicates. The total number of predicate instances are 3.4M in EN (89k CoNLL + 3.3M Europarl) and 2.62M in DE (17k CoNLL + 2.6M Europarl). The arguments for EN are identified using the heuristics proposed by lang2011unsupervised. However, we get an F1 score of 85.1% for argument identification on CoNLL 2009 EN data as opposed to 80.7% reported by titovcrosslingual. This could be due to implementation differences, which unfortunately makes our EN results incomparable. For DE, the arguments are identified using the LTH system BIBREF16 , which gives an F1 score of 86.5% on the CoNLL 2009 DE data. The word alignments for the EN-DE parallel Europarl corpus are computed using GIZA++ BIBREF17 . For high-precision, only the intersecting alignments in the two directions are kept. We define two semantic arguments as aligned if their head-words are aligned. In total we get 9.3M arguments for EN (240k CoNLL + 9.1M Europarl) and 4.43M for DE (32k CoNLL + 4.4M Europarl). Out of these, 0.76M arguments are aligned.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

The parallel corpus used is the EN-DE section of the Europarl corpus [S35].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

The parallel corpus used is the EN-DE section of the Europarl corpus [S35].

### qasper-structured-v1

程序状态：invalid_structure（不是正确性判定）

当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。

</details>

## Q18 · Which sports clubs are the targets?

论文：Stance Detection in Turkish Tweets；原标签：answerable
[完整上下文](contexts/Q18.md)

- 对象：stance targets
- 属性：俱乐部名称
- 建议验收：Galatasaray和Fenerbahçe，允许重音符号的合理变体。
- 易错点：需覆盖两个目标，不可只给出国家或体育类型。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S9

We have decided to consider tweets about popular sports clubs as our domain for stance detection. Considerable amounts of tweets are being published for sports-related events at every instant. Hence we have determined our targets as Galatasaray (namely Target-1) and Fenerbahçe (namely, Target-2) which are two of the most popular football clubs in Turkey. As is the case for the sentiment analysis tools, the outputs of the stance detection systems on a stream of tweets about these clubs can facilitate the use of the opinions of the football followers by these clubs.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

The targets are Galatasaray (Target-1) and Fenerbahçe (Target-2), two of the most popular football clubs in Turkey [S9].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

The targets are Galatasaray (Target-1) and Fenerbahçe (Target-2) [S9].

### qasper-structured-v1

程序状态：structured_passed（不是正确性判定）

Galatasaray (namely Target-1) and Fenerbahçe (namely, Target-2): Galatasaray (Target-1) and Fenerbahçe (Target-2), two of the most popular football clubs in Turkey. [S9][S6][S11]

</details>

## Q19 · What is the previous state of the art?

论文：TTTTTackling WinoGrande Schemas；原标签：answerable
[完整上下文](contexts/Q19.md)

- 对象：WinoGrande previous SOTA
- 属性：论文当时的模型
- 建议验收：RoBERTa或基于RoBERTa的方法；时间范围为该论文。
- 易错点：不要按今天排行榜替换论文中的历史描述。
- 争议：未预标；仍需独立检查
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S20

Looking at the current WinoGrande leaderboard, it appears that the previous state of the art is based on RoBERTa BIBREF2, which can be characterized as an encoder-only transformer architecture. Since T5-3B is larger than RoBERTa, it cannot be ruled out that model size alone explains the performance gain. However, when coupled with the observations of Nogueira et al. BIBREF7, T5's “generative capability”, i.e., its ability to generate fluent text, honed through pretraining, seems to play an important role. The fact that the choice of target tokens affects prediction accuracy is consistent with this observation. How and why is the subject of ongoing work.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

The previous state of the art is based on RoBERTa, an encoder-only transformer architecture [S20].

### qasper-evidence-plan-v1

程序状态：passed（不是正确性判定）

The previous state of the art is based on RoBERTa, an encoder-only transformer architecture [S20].

### qasper-structured-v1

程序状态：structured_passed（不是正确性判定）

RoBERTa: The previous state of the art is based on RoBERTa, an encoder-only transformer architecture. [S20]

</details>

## Q20 · Were other baselines tested to compare with the neural baseline?

论文：Question Answering for Privacy Policies: Combining Computational and Legal Perspectives；原标签：answerable
[完整上下文](contexts/Q20.md)

- 对象：privacy QA comparison systems
- 属性：其他基线
- 建议验收：参考变体含NA、Word Count、Human；另一变体还含SVM，应区分任务范围。
- 易错点：不要硬性只接受一种列表，也不要将所有实验混为同一任务。
- 争议：不同标注者列举的基线范围不同
- 人工确认：待复核

<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>

来源：S29

SVM: We define 3 sets of features to characterize each question. The first is a simple bag-of-words set of features over the question (SVM-BOW), the second is bag-of-words features of the question as well as length of the question in words (SVM-BOW + LEN), and lastly we extract bag-of-words features, length of the question in words as well as part-of-speech tags for the question (SVM-BOW + LEN + POS). This results in vectors of 200, 201 and 228 dimensions respectively, which are provided to an SVM with a linear kernel.

来源：S35

No-Answer Baseline (NA) : Most of the questions we receive are difficult to answer in a legally-sound way on the basis of information present in the privacy policy. We establish a simple baseline to quantify the effect of identifying every question as unanswerable.

来源：S36

Word Count Baseline : To quantify the effect of using simple lexical matching to answer the questions, we retrieve the top candidate policy sentences for each question using a word count baseline BIBREF53, which counts the number of question words that also appear in a sentence. We include the top 2, 3 and 5 candidates as baselines.

来源：S38

Human Performance: We pick each reference answer provided by an annotator, and compute the F1 with respect to the remaining references, as described in section 4.2.1. Each reference answer is treated as the prediction, and the remaining n-1 answers are treated as the gold reference. The average of the maximum F1 across all reference answers is computed as the human baseline.

</details>

<details><summary>三版回答（独立看完原文后再展开）</summary>

### qasper-guard-validation-v1

程序状态：passed（不是正确性判定）

Yes, other baselines were tested. These include:  
- No-Answer Baseline (NA) [S35],  
- Word Count Baseline [S36],  
- SVM with three feature variants (SVM-BOW, SVM-BOW + LEN, SVM-BOW + LEN + POS) [S29],  
- CNN using GloVe embeddings [S30],  
- BERT fine-tuned for answerability identification [S31],  
- Two BERT-based evidence identification baselines: Bert and Bert + Unanswerable [S37].  

Human performance was also used as a baseline [S38].

### qasper-evidence-plan-v1

程序状态：normalized_citations（不是正确性判定）

Yes, several non-neural and neural baselines were tested for comparison. These include:

- **No-Answer Baseline (NA)**: treats all questions as unanswerable [S35]; achieves 28 F1 [S40].  
- **Word Count Baseline**: uses lexical matching (top 2, 3, or 5 sentences by word overlap) [S36].  
- **SVM** with three feature sets: bag-of-words (SVM-BOW), + length (SVM-BOW + LEN), and + POS tags (SVM-BOW + LEN + POS) [S29].  
- **CNN** using GloVe embeddings and a convolutional encoder [S30].  
- **BERT-based baselines**: (i) BERT for binary evidence identification (Bert), and (ii) two-stage BERT + Unanswerable classifier [S37][S40].  
- **Human Performance** baseline computed via inter-annotator F1 [S38].

The best-performing baseline was *Bert + Unanswerable* at 39.8 F1 [S40], still far below human performance [S1][S38].

### qasper-structured-v1

程序状态：structured_passed（不是正确性判定）

No-Answer Baseline (NA): Yes, the No-Answer Baseline (NA) was tested as a simple baseline to quantify the effect of identifying every question as unanswerable. [S35]

Word Count Baseline: Yes, the Word Count Baseline was tested using lexical matching to retrieve top candidate policy sentences (top 2, 3, and 5) for each question. [S36]

BERT: Yes, two BERT-based baselines were implemented: one for binary evidence identification and another two-stage classifier (Bert + Unanswerable). [S37]

Human Performance: Yes, human performance was computed as a baseline by treating each reference answer as prediction and computing F1 against remaining references. [S38]

SVM: Yes, three SVM variants (SVM-BOW, SVM-BOW+LEN, SVM-BOW+LEN+POS) were tested as baselines for answerability identification. [S29]

CNN: Yes, a CNN neural encoder using GloVe embeddings and filter size 5 with 64 filters was used as a baseline for answerability prediction. [S30]

BERT (answerability): Yes, BERT was fine-tuned on the binary answerability identification task with learning rate 2e-5 for 3 epochs and max sequence length 128. [S31]

Bert + Unanswerable: Yes, Bert + Unanswerable was tested as the best-performing baseline achieving 39.8 F1 on answer sentence selection. [S40]

</details>

