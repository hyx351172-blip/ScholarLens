# Docling PDF 解析评测（v1）

> 生成时间：2026-08-28T12:12:35.044641+08:00

## 范围

本报告只评测 Docling 的 PDF 解析结果，不包含切分、Embedding、Milvus、检索或回答生成。

## 总结

| 指标 | 结果 |
|---|---:|
| 成功解析 | 4/4 |
| 总页数 | 71 |
| 页数一致率 | 100.0% |
| 总结构块 | 1042 |
| 结构化表格 | 38 |
| 非空表格率 | 100.0% |
| 带 Table Caption 的表格块 | 30/38 (78.9%) |
| 无 Caption / 疑似续表块 | 7 |
| Figure 误归为 Table | 1 |
| 平均页码+BBox 覆盖率 | 100.0% |
| 标题识别率 | 100.0% |
| 摘要识别率 | 100.0% |
| 作者列表精确匹配率 | 100.0% |
| 无 Chunk 产物 | 100.0% |
| 总耗时 | 261.3s |

## 分论文结果

| 论文 | 页数 | 耗时 | Blocks | Tables | Caption proxy | Figure→Table | Provenance | Gates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CharacterEval | 15/15 | 97.2s | 183 | 7 | 71.4% | 0 | 100.0% | 91% |
| GAAP | 18/18 | 35.8s | 274 | 6 | 83.3% | 0 | 100.0% | 91% |
| MemLineage | 24/24 | 64.5s | 372 | 14 | 92.3% | 1 | 100.0% | 91% |
| MAP-Graph | 14/14 | 63.8s | 213 | 11 | 72.7% | 0 | 100.0% | 91% |

## 元数据与人工抽查入口

### CharacterEval

- 标题：CharacterEval : A Chinese Benchmark for Role-Playing Conversational Agent Evaluation
- 作者：Quan Tu, Shilong Fan, Zihang Tian, Tianhao Shen, Shuo Shang, Xin Gao, Rui Yan
- 摘要预览：Recently, the advent of large language models (LLMs) has revolutionized generative agents. Among them, Role-Playing Conversational Agents (RPCAs) attract considerable attention due to their ability to emotionally engage users. However, the absence of a comprehensive benchmark impedes progress in this field. To bridge this gap, we introduce CharacterEval , a…
- 标识符：DOI=-；arXiv=-
- 空页：无
- 警告：无

表格样本：

- 第 6 页 / 6.1 Dataset Statistic：Table 1: The statistic of CharacterEval dataset. | | Training | Test | |---------------------|------------|--------| | # Characters | 77 | | | # Conversations | 1,785 | | | Avg. Turns / Conv. | 9.28 | | | Avg. Tokens / Conv. | 369.69 | | | # Examples | 6,811 …
- 第 7 页 / 6.2 Experimental Setting：Table 2: LLMs evaluated in our experiments. | Models | Specialized | Model Size | Open Source | Primarily Language | Creator | |--------------|---------------|--------------|---------------|----------------------|----------------------------| | ChatGLM3 | ✗ |…
- 第 7 页 / 6.2 Experimental Setting：Table 3: Pearson correlation coefficient (Pearson, 1901) with human judgments of GPT-4 and our CharacterRM (abbr. Char-RM). We report the performance of GPT4 under different settings: 1-shot, 2-shot, and 3-shot. Bold indicates the highest score. | Metric | Ch…

### GAAP

- 标题：An AI Agent Execution Environment to Safeguard User Data
- 作者：Robert Stanley, Avi Verma, Konstantinos Kallas, Sam Kumar, Lillian Tsai
- 摘要预览：AI agents promise to serve as general-purpose personal assistants for their users, which requires them to have access to private user data (e.g., personal and financial information). This poses a serious risk to security and privacy. Adversaries may attack the AI model (e.g., via prompt injection) to exfiltrate user data. Furthermore, sharing private data w…
- 标识符：DOI=-；arXiv=2604.19657
- 空页：无
- 警告：无

表格样本：

- 第 3 页 / 2 Related Work：Table 1. Features of systems providing privacy for agentic AI (example systems in parentheses). Like other IFC systems, GAAP provides data disclosure guarantees (f1) , and does so deterministically (unlike model-generated policies ). GAAP does not rely on tru…
- 第 8 页 / 4.2 Private Data Database：Table 2. GAAP API used by code artifacts. | Function | Description | |--------------------------------------------|-----------------------------------------------------------------------------------------------| | priv_data_db. access_<key>() | Access the pri…
- 第 10 页 / 6.1 Experimental Methodology：Table 3. A sample of tasks from our benchmark suite, with the number of tools potentially used and the task's source. | Task ID | Description | Tools Source | |-----------|-------------------------------------|----------------| | 1 | Order food. | 3 [1] | | 2…

### MemLineage

- 标题：MemLineage : Lineage-Guided Enforcement for LLM Agent Memory
- 作者：Ciyan Ouyang, Rui Hou
- 摘要预览：We introduce MemLineage , a defence for LLM agent memory that attaches both cryptographic provenance and LLM-mediated derivation lineage to every entry. Recent and concurrent work shows that untrusted content can be written into persistent agent state and re-enter later sessions as an instruction; the remaining systems question is how to preserve useful mem…
- 标识符：DOI=-；arXiv=2605.14421
- 空页：无
- 警告：无

表格样本：

- 第 13 页 / 6.1 Experimental Setup：Table 1: ASR matrix (deterministic harness). Source: paper/data/asr\_matrix\_v1.csv ; CI verifies byte-equality with the runner output. Lower is better. | Defence | Poison | ↓ Graft ↓ | Sleeper ↓ | |-------------------|----------|-------------|-------------| …
- 第 14 页 / 6.2 RQ1: Attack Success Rate Across Defences：Figure 3: ASR matrix on the deterministic harness, rendered from paper/data/asr\_matrix\_v1.csv . Green cells are defended ( ASR = 0); red cells are attacker wins ( ASR = 1). Cell text gives the value and verdict, the right strip reports blocked attack famili…
- 第 14 页 / 6.2 RQ1: Attack Success Rate Across Defences：Table 2: Two-session RAG-to-memory workflow. The EXTERNAL document is summarised into persistent memory in session 1 and recalled in session 2. MemLineage and coarse taint preserve the untrusted parent edge; Memory Sandbox blocks by removing recall. Source: p…

### MAP-Graph

- 标题：MAP-Graph: Provenance-Aware Shared Memory for Multi-Agent Workflows
- 作者：Yiqi Wang, Zihao Yan, Jiaqi Zhang, Zhangkai Wu, Mingkai Zheng, Zequn Sun, Yanming Zhu, Taotao Cai
- 摘要预览：Shared memory helps language-model agents reuse information across long workflows, yet relevant evidence may not be admissible for a particular agent or action. Because restrictions propagate through derivations, summaries can conceal private, poisoned, untrusted, or revoked sources, enabling unauthorized reads or unsafe actions. Existing approaches provide…
- 标识符：DOI=-；arXiv=2608.10509
- 空页：无
- 警告：无

表格样本：

- 第 6 页 / 4.2 Baselines：Table 1: Main results over 2,700 tasks per method (percent). UAcc is conditional unauthorized access; N/A means no observed attempt. B3-B5 are benchmark adaptations, and B6 is the flat-metadata control. Additional diagnostic rates are reported in Appendix F. …
- 第 7 页 / 4.6 Ablation Results：Table 2: Single-run ablations over 2,700 tasks per variant (percent). Clean is clean-task TSR; UAcc is conditional unauthorized access. Full diagnostics appear in Appendix F.4. | Variant | TSR ↑ | Acc ↑ | Clean ↑ | Unsafe ↓ | ASR ↓ | UAcc ↓ | Rev. ↓ | |------…
- 第 7 页 / 4.6 Ablation Results：Table 3: Backbone transfer on the same stratified 540-task subset (percent). Boundary-specific diagnostics are reported in Appendix F.5. | Method | Qwen2.5-7B | Qwen2.5-7B | Qwen2.5-7B | GLM-4-9B | GLM-4-9B | GLM-4-9B | Llama-3.1-8B | Llama-3.1-8B | Llama-3.1…

## 人工页面核对

- CharacterEval 第 9 页：源 PDF 中 Table 4 是同一 Caption 下的上下两个面板；Docling 输出为两个 table blocks，第二块没有 Caption，说明复杂表格仍存在碎片化。
- MemLineage 第 14 页：源 PDF 左栏是 Figure 3 热力图；Docling 将其输出为 table block。内容可读，但语义类型和 Caption 关系不正确。
- 因此 `非空表格率=100%` 只说明结构块有内容，不代表逻辑表格完整率或类型精度为 100%。

## 与 baseline-v1 的关系

baseline-v1 的 58 个“疑似表格相关 Chunk”是基于旧 Markdown/Chunk 信号的诊断值，不能直接当作真实表格数量。本报告统计的是 Docling 独立识别的结构化 `table` blocks。切分效果与 RAG 问答效果应在下一阶段分别评测。

## 产物

每篇论文目录包含 `content.md`、`document.json`、`docling-document.json`、`quality-report.json` 和 `evaluation.json`；不会生成 `chunks.json`。
