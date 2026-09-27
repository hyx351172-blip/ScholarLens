# Answer Guard v2：新论文批次验证

日期：2026-09-26。使用 ai-product-dev-pack 的冻结样本与分层验证流程；测试过程中未修改防护规则、提示词或标签。

## 范围与可复现性

- QASPER dev：20 篇论文，各 1 题；15 道可回答、5 道所有标注者均标为无答案的题。
- 排除上一轮 `qasper-guard-dev-v1` 的全部 20 篇论文及已收集的 207 个规范化问题。不是全历史论文污染审计，也不是未触碰的官方 test 集。
- 仅选择正文证据可映射的可回答题；排除视觉证据题、标注分歧题以及上下文超过 60,000 字符的论文。全文输入，无截断。
- 模型：`qwen3-vl-plus`，temperature=0，max_tokens=700；20 次真实调用，无重试。生成过程不读取 labels。
- 直接调用模型，再执行当前本地 guard v2；并非运行中的 `/chat` 服务、检索或 PDF 上传端到端测试。
- 原始产物（gitignored）：`output/qasper-guard-validation-v1/`，包含 inputs、labels、manifest、20 份原始/防护后回答及 scores。

冻结哈希：

| 文件 | SHA-256 |
| --- | --- |
| QASPER dev 源数据 | `2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93` |
| inputs.json | `47267de5d902a1db606f408421edab3ad11b6323c497a3e297fe3e0425cd399c` |
| labels.json | `256dc7deef47a329cb756581e8da1f385d5e8f80cb411b80b1e1ed9eb35b90cb` |
| answer_guard.py | `95c5a1eae60e7146085dd0e94d538aba4d44c4bc924a3428e72dbcee97f192cb` |

```powershell
python tests/integration/prepare_qasper_guard.py --output-dir output/qasper-guard-validation-v1 --exclude-batch output/qasper-guard-dev-v1 --seed scholarlens-qasper-validation-v1
python tests/integration/run_qasper_guard.py --output-dir output/qasper-guard-validation-v1
python tests/integration/score_qasper_guard.py --output-dir output/qasper-guard-validation-v1
```

准备脚本拒绝覆盖已有目录；再次实验应指定新目录。生成器验证冻结输入和 guard 哈希。

## 结果

| 指标 | 结果 |
| --- | --- |
| 完成 / 截断 | 20/20；0 次长度截断 |
| 可回答题返回固定拒答 | 2/15（13.3%） |
| 无答案题返回固定拒答 | 4/5（80%） |
| 防护状态 | passed 12、normalized_citations 2、insufficient_evidence 6 |
| 引用格式导致拒答 | 0 |
| 可回答题原始 / 最终 token F1 | 0.25127 / 0.24855 |
| 平均生成加防护耗时 | 4.17 秒 |
| 输入 / 输出 / 总 tokens | 96,394 / 2,359 / 98,753 |

token F1 使用官方函数，移除引用后与参考答案取最佳匹配；不是官方全量成绩，也不是语义准确率。未评测 Evidence F1 或逐声明蕴含关系。尤其 Yes/No 和简短答案与解释型输出的长度差异会影响 token F1。

## 失败与标签冲突复核

1. `prediction-05.json`：How big is their created dataset?
   原始回答将问题理解为模拟训练集大小，提及 100k 训练样本和评估集，但遗漏参考答案的 **353 段会话、40 名说话者**。原始回答已经明确无法回答，guard 将其标准化。属于问题指代/目标数据集识别失败，不是有效答案被格式规则误拦。
2. `prediction-07.json`：Is the template-based model realistic?
   两份标注均为 Yes，依据包含合成模型实验和总结段落。模型直接输出证据不足；guard 仅标准化。属于模型未完成所需的证据推断；“realistic”的问法也较宽泛。
3. `prediction-01.json`：What is the performance of their method?
   单份标签为无答案，但全文 S1、S36、S37–38、S41、S43–44 确实包含性能描述、相对基线改善和局限。模型给出了对应回答，guard 仅展开组合引用。**保留原标签计分**，标记为标签与正文存在可回答性冲突、待人工复核；不能把此例直接算作已证实的幻觉。部分原文指标被 INLINEFORM 占位，亦不能由当前核对宣布每个细节完全正确。
4. 其余四道无答案题原始回答均表达所问细节缺失，最终输出标准拒答。这只是对回答意图的核对，并非全文缺失事实的完整人工审计。

## 判断与后续

新批次未出现引用格式误杀，但可回答题的模型端拒答仍存在。上一轮回放的 0/15 拒答没有在新批次完全复现，不能宣称泛化问题已解决。当前规则不负责判断所有事实是否受证据支持。

下一步优先处理模糊指代与证据定位，先在开发样本设计“目标实体识别 / 证据候选整理”方案，不继续为个别问法增加拒答正则。此批次一旦参与改进，应视为开发集，再留新样本验证。上线前另做真实检索及前端链路回归。

工程验证：抽样准备测试 6 项、防护测试 9 项通过；完整 Python 回归 **413 项通过**（21.961 秒）；112 条 AC 双向可追溯检查通过。仅修改评测脚本及本报告，本轮未改业务防护规则，未提交或推送。
