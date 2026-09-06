# ScholarLens 当前 PDF 解析器批量评测

> 生成时间：2026-08-30T19:46:00+08:00
> 数据集：`C:\Users\hp\Desktop\ScholarLens\backend\data\evaluation_papers`

## 评测边界

本报告评测 Docling 解析及 Reading Order、章节层级、表格、Figure/Formula 关系后处理。
指标主要是自动化结构代理指标，不等同于人工标注后的语义准确率；不包含 Chunker、Embedding、检索和回答生成。

## 总体结果

| 指标 | 结果 |
|---|---:|
| 成功解析 | 19/19 (100.0%) |
| 总页数 | 682 |
| 页数一致率 | 89.5% |
| 总耗时 | 2114.4s |
| 平均每页耗时 | 3.100s |
| 总 Blocks | 8469 |
| 平均 Provenance 覆盖 | 100.0% |
| 标题识别率 | 100.0% |
| 摘要识别率 | 84.2% |
| Section path 覆盖 | 99.2% |
| 逻辑表格 / Caption 覆盖 | 216 / 47.7% |
| 跨 Block 合并表格 | 5 |
| 逻辑 Figure / Caption 覆盖 | 301 / 55.5% |
| Figure 显式解释覆盖 | 28.2% |
| 逻辑 Formula / 上下文覆盖 | 138 / 95.7% |
| 公式编号覆盖 | 56.5% |
| 悬空关系 | 0 |
| 全部门禁通过论文 | 16/19 |

## 关键发现

- **工程稳定性较好**：19/19 篇任务成功，完整页解析率 89.5%，Provenance 平均 100.0%，悬空关系 0。
- **章节路径总体可靠**：Section path 覆盖 99.2%；但无编号标题仍依赖启发式回退，不能据此宣称层级语义完全正确。
- **摘要识别存在缺口**：`2106.10379_alphafold.pdf`, `2407.21783_llama-3-herd-of-models.pdf`, `PMC2950080_structured-digital-tables.pdf`。
- **标题非空率不等于标题准确率**：多语言噪声样本被识别为 arXiv URL，PMC 样本仅识别为 “PERSPECTIVE”；标题仍需人工准确率标注。
- **表格 Caption 绑定是当前最大结构短板**：总体仅 47.7%；完全未绑定的样本包括 `2106.10379_alphafold.pdf`, `2407.21783_llama-3-herd-of-models.pdf`, `2501.12948_deepseek-r1.pdf`, `PMC2950080_structured-digital-tables.pdf`。
- **Figure Caption 与解释段覆盖偏低**：Caption 55.5%，显式解释段 28.2%；完全未绑定 Caption 的样本包括 `2407.21783_llama-3-herd-of-models.pdf`, `2501.12948_deepseek-r1.pdf`, `PMC2950080_structured-digital-tables.pdf`。
- **公式上下文较稳定**：总体 95.7%；上下文不完整集中在 `1806.07366_neural-ordinary-differential-equations.pdf`, `2308.13418_nougat.pdf`。
- **测试数据存在一处命名/内容错误**：`2106.10379_alphafold.pdf` 实际标题为 “Electron- and hole-doping on ScH2 and YH2...”，不是 AlphaFold，应重新下载正确论文后复测。
- **同步解析延迟较高**：最慢 5 篇为 `2103.00020_clip.pdf` 383.9s; `2005.14165_language-models-are-few-shot-learners.pdf` 380.5s; `2407.21783_llama-3-herd-of-models.pdf` 216.0s; `2205.14135_flashattention.pdf` 186.8s; `2501.12948_deepseek-r1.pdf` 147.9s。
- **警告集中而非均匀分布**：`2303.08774_gpt-4-technical-report.pdf` 140 条; `2304.02643_segment-anything.pdf` 57 条; `2501.12948_deepseek-r1.pdf` 49 条; `2407.21783_llama-3-herd-of-models.pdf` 33 条; `2307.12037_multilingual-noisy-materials-paper.pdf` 24 条。

## 改进优先级

1. 为 Llama 3、DeepSeek-R1、GPT-3、Nougat 和 PMC 样本建立 Table/Figure Caption 人工标注，修复 Caption 与对象相距较远、跨栏或跨页时的绑定。
2. 针对 GPT-4、DeepSeek-R1 的无编号标题回退建立层级 ground truth，区分真实标题与图内文本。
3. 修复 Llama 3 与 PMC 摘要识别，并替换错误的 AlphaFold 测试文件。
4. 对 Neural ODE 与 Nougat 的无上下文公式逐页核对，确认是正文绑定失败还是独立展示公式。
5. 将 PDF 解析改为异步任务，并提供 Fast/Accurate 模式；长论文不应阻塞上传请求。

## 分论文结果

| 论文 | 页数 | 秒 | Blocks | Provenance | Path | Tables | Figures | Formulae | Gates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1706.03762_attention-is-all-you-need.pdf | 15/15 | 66.6 | 167 | 100.0% | 97.0% | 4 | 6 | 5 | 100.0% |
| 1806.07366_neural-ordinary-differential-equations.pdf | 18/18 | 30.5 | 466 | 100.0% | 99.3% | 3 | 10 | 46 | 100.0% |
| 1810.04805_bert.pdf | 16/16 | 53.3 | 259 | 100.0% | 98.6% | 8 | 5 | 0 | 100.0% |
| 2005.14165_language-models-are-few-shot-learners.pdf | 75/75 | 380.5 | 743 | 100.0% | 99.9% | 37 | 34 | 1 | 100.0% |
| 2103.00020_clip.pdf | 48/48 | 383.9 | 538 | 100.0% | 99.8% | 20 | 21 | 0 | 100.0% |
| 2106.09685_lora.pdf | 26/26 | 118.4 | 284 | 100.0% | 96.2% | 18 | 8 | 6 | 100.0% |
| 2106.10379_alphafold.pdf | 8/8 | 15.4 | 123 | 100.0% | 95.2% | 1 | 8 | 5 | 85.7% |
| 2111.15664_donut.pdf | 29/29 | 43.8 | 243 | 100.0% | 96.0% | 3 | 14 | 0 | 100.0% |
| 2204.08387_layoutlmv3.pdf | 10/10 | 39.9 | 183 | 100.0% | 95.5% | 4 | 5 | 3 | 100.0% |
| 2205.14135_flashattention.pdf | 34/34 | 186.8 | 512 | 100.0% | 99.1% | 21 | 8 | 32 | 100.0% |
| 2303.08774_gpt-4-technical-report.pdf | 100/100 | 143.8 | 1275 | 100.0% | 100.0% | 12 | 29 | 6 | 100.0% |
| 2304.02643_segment-anything.pdf | 30/30 | 70.9 | 615 | 100.0% | 99.8% | 8 | 55 | 0 | 100.0% |
| 2307.12037_multilingual-noisy-materials-paper.pdf | 20/20 | 29.0 | 139 | 100.0% | 100.0% | 0 | 8 | 2 | 100.0% |
| 2308.13418_nougat.pdf | 17/17 | 41.6 | 238 | 100.0% | 97.9% | 9 | 18 | 10 | 100.0% |
| 2312.00752_mamba.pdf | 36/36 | 102.2 | 545 | 100.0% | 99.4% | 15 | 11 | 8 | 100.0% |
| 2407.21783_llama-3-herd-of-models.pdf | 91/92 | 216.0 | 1028 | 100.0% | 100.0% | 34 | 27 | 2 | 57.1% |
| 2408.09869_docling-technical-report.pdf | 9/9 | 21.7 | 115 | 100.0% | 100.0% | 2 | 6 | 0 | 100.0% |
| 2501.12948_deepseek-r1.pdf | 86/86 | 147.9 | 796 | 100.0% | 99.7% | 16 | 19 | 12 | 100.0% |
| PMC2950080_structured-digital-tables.pdf | 12/13 | 22.1 | 200 | 100.0% | 100.0% | 1 | 9 | 0 | 57.1% |

## 自动发现的问题

- `1706.03762_attention-is-all-you-need.pdf`：3 条警告：block_000030: inferred unnumbered heading level 3 for 'Scaled Dot-Product Attention'; block_000158: inferred unnumbered heading level 2 for 'Attention Visualizations Input-Input Layer5'; block_000031: figure caption missing
- `1806.07366_neural-ordinary-differential-equations.pdf`：5 条警告：block_000254: inferred unnumbered heading level 2 for 'Algorithm 2 Complete reverse-mode derivative of an ODE initial value problem'; block_000078: formula context missing; block_000228: formula context missing …
- `1810.04805_bert.pdf`：1 条警告：block_000181: inferred unnumbered heading level 2 for "Appendix for 'BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding'"
- `2005.14165_language-models-are-few-shot-learners.pdf`：15 条警告：block_000006: inferred unnumbered heading level 2 for 'Contents'; block_000327: inferred unnumbered heading level 2 for 'Contributions'; block_000224: Figure 3 caption has no matching figure block …
- `2103.00020_clip.pdf`：1 条警告：block_000036: Figure 3 caption has no matching figure block
- `2106.10379_alphafold.pdf`：abstract_present
- `2106.10379_alphafold.pdf`：4 条警告：未识别论文摘要; block_000014: inferred unnumbered heading level 2 for 'II. COMPUTATIONAL DETAILS'; block_000027: inferred unnumbered heading level 2 for 'III. RESULTS AND DISCUSSION' …
- `2111.15664_donut.pdf`：8 条警告：block_000213: inferred unnumbered heading level 3 for '(a) Input Image'; block_000214: inferred unnumbered heading level 3 for '(b) Prediction'; block_000215: inferred unnumbered heading level 3 for '(c) Ground Truth' …
- `2204.08387_layoutlmv3.pdf`：4 条警告：block_000005: inferred unnumbered heading level 2 for 'CCS CONCEPTS'; block_000007: inferred unnumbered heading level 2 for 'KEYWORDS'; block_000009: inferred unnumbered heading level 2 for 'ACMReference Format:' …
- `2205.14135_flashattention.pdf`：6 条警告：block_000040: inferred unnumbered heading level 3 for 'Algorithm 0 Standard Attention Implementation'; block_000058: inferred unnumbered heading level 3 for 'Algorithm 1 FlashAttention'; block_000309: inferred unnumbered heading level 3 for 'Algorithm 2 FlashAttention Forward Pass' …
- `2303.08774_gpt-4-technical-report.pdf`：140 条警告：block_000001: inferred unnumbered heading level 1 for 'OpenAI ∗'; block_000055: inferred unnumbered heading level 2 for 'GPT-4 3-shot accuracy on MMLU across languages'; block_000062: inferred unnumbered heading level 3 for 'Example of GPT-4 visual input :' …
- `2304.02643_segment-anything.pdf`：57 条警告：block_000243: inferred unnumbered heading level 2 for 'Table of contents:'; block_000338: inferred unnumbered heading level 4 for 'Motivation'; block_000343: inferred unnumbered heading level 4 for 'Composition' …
- `2307.12037_multilingual-noisy-materials-paper.pdf`：24 条警告：block_000001: inferred unnumbered heading level 1 for 'Superconductor Pb10-xCux(PO4)6O showing levitation at room temperature and atmospheric pressure and mechanism'; block_000013: inferred unnumbered heading level 2 for 'https://arxiv.org/abs/2307.12037'; block_000017: inferred unnumbered heading level 2 for 'II. RESULTS and DISCUSSIONS' …
- `2308.13418_nougat.pdf`：18 条警告：3 个公式没有可用文本; block_000188: inferred unnumbered heading level 2 for 'EXPERIMENTAL ASPECTS'; block_000193: inferred unnumbered heading level 2 for 'SELECTION OF GAS MIXTURES' …
- `2312.00752_mamba.pdf`：5 条警告：block_000022: inferred unnumbered heading level 2 for 'Selective State Space Model'; block_000066: inferred unnumbered heading level 3 for 'Selective Copying'; block_000065: inferred unnumbered heading level 3 for 'Copying' …
- `2407.21783_llama-3-herd-of-models.pdf`：page_count_match, no_empty_pages, abstract_present
- `2407.21783_llama-3-herd-of-models.pdf`：33 条警告：未识别论文摘要; 部分页面没有带文本的结构块; block_000001: inferred unnumbered heading level 1 for 'Llama Team, AI @ Meta 1' …
- `2408.09869_docling-technical-report.pdf`：8 条警告：block_000002: inferred unnumbered heading level 1 for 'Version 1.0'; block_000034: inferred unnumbered heading level 3 for 'Layout Analysis Model'; block_000037: inferred unnumbered heading level 3 for 'Table Structure Recognition' …
- `2501.12948_deepseek-r1.pdf`：49 条警告：block_000215: inferred unnumbered heading level 5 for 'Listing 7 | An example SFT trajectory from non-reasoning data related to writing.'; block_000217: inferred unnumbered heading level 5 for '## Response <think>'; block_000295: inferred unnumbered heading level 4 for 'Warning: This section contains potentially risky and offensive content!' …
- `PMC2950080_structured-digital-tables.pdf`：page_count_match, no_empty_pages, abstract_present
- `PMC2950080_structured-digital-tables.pdf`：19 条警告：未识别论文摘要; 部分页面没有带文本的结构块; block_000001: inferred unnumbered heading level 1 for 'Structured digital tables on the Semantic Web: toward a structured digital literature' …

## 结论与限制

- 页数、Provenance、关系完整性用于判断工程链路是否稳定。
- Caption/上下文覆盖率只表示建立了关系，不能证明绑定对象在语义上一定正确。
- 公式编号只统计可从解析文本恢复的显式编号；无编号公式会自然降低该指标。
- 下一步应从失败门禁、低覆盖和高警告论文中抽取页面，建立人工 ground truth。

## 复现

```powershell
python scripts/evaluate_parser_dataset.py --input-dir <evaluation_papers>
```
