# SciFact 核验器基线 v1：离线准备报告

日期：2026-09-27。状态：**prepared_not_run**。实际模型调用 **0**；尚无模型准确率。

## 这次测什么

给现有 `selected_claim_support_v1` 一条数据集断言及一篇完整候选摘要，判断
支持、反驳或证据不足。目的在于检验此前出现的“核验器过度放行”，不再把另一个
模型的主观意见当作真值。标签来自 SciFact 原始标注，项目人工复核栏仍为 null。

采用官方 dev 的 30 个 claim–abstract 对，而非无标签的 test。正例和反例选用
有标注的证据文献；证据不足题仅取 evidence 为空的断言及其 cited_doc_ids 候选文献。
三类都提供完整摘要，不能用空证据让拒答变得过于容易。
标签与候选文献含义参见 [官方数据定义](https://github.com/allenai/scifact/blob/master/doc/data.md)。

这是**给定候选文献的分类 smoke 测试**。没有 PDF 上传、解析、向量检索、重新生成回答；
不评测 rationale 句子召回，也不等同于 [官方 SciFact 评分](https://github.com/allenai/scifact/blob/master/doc/evaluation.md)。

## 抽样与兼容性检查

固定 seed：`scholarlens-scifact-dev-smoke-v1`。先按各类可用数量从少到多抽样，
类内按 seed + 样本 ID 的 SHA-256 排序。限制断言 ID、规范化断言文本和文献 ID 均不重复，
最后用另一固定 hash 排序打散展示顺序。此后不得按模型答题结果替换样本。

| 阶段 | 支持 | 反驳 | 证据不足 | 总计 |
| --- | ---: | ---: | ---: | ---: |
| 原始候选对 | 138 | 71 | 113 | 322 |
| 通过现有输入契约 | 132 | 65 | 106 | 303 |
| 冻结测试对 | 10 | 10 | 10 | 30 |

源文件：300 条 dev 断言、5,183 篇摘要。抽中 30 条不同断言及 30 篇不同文献。
322 是候选对数，不是断言数；一条断言可能对应多篇候选文献。

19 个候选对在抽样前被排除，全部记录在 `audit.json`，不是模型错误，也不是答题后剔除：

- 14 个完整摘要超过现有 8-anchor 上限。没有截断原文或只保留 gold 证据句。
- 5 个原始断言不通过现有单句输出契约。其中 ID 300 是两句；ID 75、577、1041、1274
  分别含 `H. pylori`、`P. chabaudi`、`H2A.Z`、`E. coli` 等带点名称，触发了过严的句界规则。
  **这揭示了当前结构校验对科研缩写的兼容性问题**；本次只记录，不修改已冻结的核验器。

另有源记录 ID 1245 的 `cited_doc_ids` 将 7662395 重复列出两次。
仅在构造候选对时去重，原始文件不修改，重复引用和去重结果保留在审计记录中。
实际抽中过程无需因重复断言/文献跳过候选，但代码强制执行去重限制并有专门测试。

## 输入隔离与可复现性

使用现有 `fixed_v1` 的默认 480 字符分段，选中摘要的**全部** anchors；按偏移拼接必须
逐字等于原始摘要句子以换行连接的文本。断言不改写，system policy 不改。
30 题的 anchor 数分布为 2/3/4/5/6/7 段各 3/11/8/3/3/2 题。
摘要合计 41,097 字符，完整请求消息合计 127,206 字符；字符数不是 token 数。

- `entries.json` / `request-*.json`：只有断言、完整摘要 anchors 和现有核验策略，无 gold 标签、人工理由或证据句下标。
- `gold.json`：标签、文献标题、所有替代 rationale 句集合及待复核字段，不能传给模型。
- `audit.json`：资格过滤、重复数据警告和未入选候选清单。
- `manifest.json`：冻结 278 项来源哈希和 34 个产物哈希，包含历史实验、当前代码、源数据和请求。
- `summary.json`：离线统计，`provider_calls=0`、`accuracy=null`。

产物目录：`output/scifact-verifier-v1/`。下载数据和 output 仍按项目规则本地保存，不自动推送。
本次未读取 test split，未读取 API Key，未创建 API 客户端。

## 计分规则

| 核验器原始决定 | 分类结果 |
| --- | --- |
| supported / entailed | SUPPORT |
| unsupported / contradicted | CONTRADICT |
| unsupported / not_in_evidence | NOT_ENOUGH_INFO |
| uncertain / ambiguous_* | UNCERTAIN，单列弃权，不算正确 NEI |
| 异常、截断、拒绝、无效 JSON/绑定 | ERROR，保留在分母 |
| 没有结果 | MISSING，保留在分母 |

通过现有严格解析器重读 raw response，而不是信任结果文件中的解析缓存。
结果必须匹配冻结请求 hash；重复 ID、未知 ID、错配请求直接中止评分。

输出三分类混淆矩阵、各类 precision/recall/F1、macro-F1、全 30 题分母准确率。
错误/弃权/缺失不是第四个 gold 类，但作为预测列保留，均不能拿到正确分。
无预测时模型指标为 null；部分完成的分数只表示固定分母上的当前结果，不是最终成绩。

门控指标另外记录：

- 错误放行：20 道反驳或证据不足题中，被判断为 supported 的数量及比例。
- 正例阻断：10 道支持题中所有未被放行的数量，包含 uncertain/error/missing。
- 正例被明确判负：只计被判 CONTRADICT/NEI，与基础设施错误或未完成分开。

## 验证

按 ai-product-dev-pack 的测试流程，先写契约测试得到 RED，再实现适配器与计分器得到 GREEN。
随后为真实数据的重复引用和非规范文献 ID 补充失败用例并修复。

- 新增离线测试：20/20 通过，覆盖完整摘要、标签隔离、三类平衡、重复样本、超限排除、
  数据异常、write-once、哈希变化阻断、严格响应解析及计分分母。
- 测试中的完美/全支持/全弃权预测均为注入的假响应，只验证计算逻辑，**不是模型实验成绩**。
- 全量离线回归：**705/705 通过**，37.558 秒；验收追踪 **193/193** 对齐。
- 最终 `verify`：278 项来源哈希及 34 个产物哈希全部通过，历史实验未漂移。
  新增文件密钥模式扫描命中 0，`git diff --check` 通过。
- 冻结 manifest 的 SHA-256：`be4ceceb7e21fe97ed75a029a4ea999053a5e71a21be5e6839c0bfd8737ff4fd`。
  `kb_chat.py` SHA-256 仍为 `61dc1f00552a4f4c4722acaf8507e682ea3dd7a6e9ac9648fb93af69629637cc`。
- 历史 22 条评审、其提示词、模型决定及生产默认值不变。本次无数据库/服务变更，无 Git 提交或推送。

## 如何复核与后续运行

在项目根目录执行（现有 Python 环境即可）：

```powershell
python -X utf8 -m unittest tests.test_scifact_verifier -v
python -X utf8 -m tests.integration.prepare_scifact_verifier verify
# 有真实结果 JSON 列表后离线计分；此命令本身不调用模型：
python -X utf8 -m tests.integration.prepare_scifact_verifier score --results <results.json>
```

首次准备命令是 `python -X utf8 -m tests.integration.prepare_scifact_verifier prepare`；
当前目录已生成，再次 prepare 会拒绝覆盖，应使用 verify。真实模型执行适配器尚未在本轮加入。

下一步需单独批准：仅向当前配置的阿里云百炼发送这 30 条断言及相应完整摘要，
最多 30 次 qwen3-vl-plus 调用、每次最多 1,000 输出 token，单次 60 秒，无自动重试。
不发送 gold 标签，不重新生成答案，不调用第二个评审模型；错误应停止并保留未完成项。

## 结论边界

30 题用于发现方向性问题，不足以证明稳定泛化，更不能称为生产准确率或申请材料中的全链路指标。
均衡抽样不保留自然类别分布；完整摘要的 fixed_v1 输入也不同于上轮局部句级证据，不能直接当作新旧方法 A/B。
SciFact 的领域偏向生物医学，不能替代原有 LoRA/BERT 22 条限定词、参数和公式专项回归。
公开数据可能存在模型预训练污染。本轮筛掉的长摘要和缩写问题应作为独立兼容性回归跟进。
