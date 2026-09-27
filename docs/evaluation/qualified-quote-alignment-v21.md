# 引用空白匹配 v2.1：离线修复与重放

日期：2026-09-27。本轮 **0 次新 API 调用**，不重跑模型、不自动续跑 stopped_error 实验。

## 结论

上一轮唯一保存的真实响应，在独立 v2.1 解析器中能够完成引用契约校验：
**5 处精确匹配、1 处仅空白差异匹配**。原 v2 记录仍是 ERROR，原始响应未改写。
重新解释得到的最终判断为 `unsupported / not_in_evidence`，不是“引用修好就放行”。

这只验证了一个格式兼容问题已修复，**不代表语义核验准确率提升**。52 条计划输入中仍然只有
1 条有真实响应，51 条从未调用；人工复核字段和语义准确率仍为 null。

## 受限匹配规则

新模块 `backend/chat/quote_alignment.py` 只把非空的 ASCII 空格、TAB、CR、LF 连续段折叠
为一个空格，再在**本条选定的单个 anchor 内**查找唯一匹配。每个规范化字符都保存其原文
半开区间，匹配后映射回原文坐标。坐标单位沿用现有系统的 Python Unicode 码点。

- 不删除分隔符，不添加原来没有的分隔符，不做 trim、大小写转换或 Unicode 规范化。
- 不改词、数字、标点和公式符号，不去连字符，不做语义或编辑距离模糊匹配。
- NBSP、细空格、零宽字符、Unicode 行分隔符、VT、FF 不在这次容错白名单中。
- 原文中若出现两处规范化等价内容，就拒绝；即使其中一处本来精确匹配，也不优先选它。
- 检查重叠出现；同一检查中多个引用最终落到同一原文区间也拒绝。
- 不跨 anchor 拼接，不借用其他断言或未选择的片段。
- 输入引文及映射后的原文引文各不超过 1,200 字符，单个源片段不超过 64,000 字符。

每处合法引用保留：

| 字段 | 含义 |
| --- | --- |
| model_quote | 模型原样输出的引文 |
| quote | 实际匹配的原文，保留其真实换行/空白 |
| source_start / source_end | 相对于源文本的原始坐标 |
| match_mode | exact 或 whitespace_only |
| anchor_id / source_id / filename | 原有证据来源标识 |

前后带有空白的引文不会被 trim；源坐标覆盖所匹配的完整空白段。若这导致原文引文超过
长度限制，也拒绝，不悄悄裁剪证据。引文内容和坐标能互相校验，不以模型提供的坐标为准。

## 与原核验器的关系

独立入口：`backend/chat/qualified_claim_support_v21.py::parse_decision`。

输入仍是冻结的 v2 packet 和保存的原始模型响应。v2.1 仅在内存副本中将引用映射回原文，
再交给**未修改的 v2 解析器**检查完整字段、身份、引用数量、重复引用、长度及三项判定规则。
结果带有新解析器版本、原输入契约版本、匹配规则版本和原始响应 SHA-256。

这不是模型的新回复，也不是新的提示词实验。未重写 claim、reason、status、basis、relation；
未 monkeypatch v2，未修改其 packet_id 或 policy。`semantic_verified=false`、
`human_verified=false` 保持不变。

未接入 `kb_chat` 默认流程，未修改原执行器。后续实际调用需显式选用新解析器并建立独立
运行记录；不能修改已冻结 v2 实验或在原目录里恢复运行。

## 实际失败样本的离线重放

输入样本：`SCIFACT-SF-72-6076903`。

```text
模型引文：... ALK-2 receptor. It is unable ...
实际原文：... ALK-2 receptor.\nIt is unable ...
```

失败引用属于 `content.citations[0]`，选定来源是 `S1:E0002`。
v2.1 恢复的原始源区间为 **[498, 626)**，模式是 `whitespace_only`。
另 5 处引用不需要转换；全部恢复坐标均经对应 anchor 原文切片校验。

| 项目 | 原 v2 实验 | 本轮离线重放 |
| --- | --- | --- |
| 新模型调用 | 1 次（历史用量） | 0 次 |
| 本条响应契约 | ERROR | contract_valid |
| 正式决定 | null | unsupported / not_in_evidence |
| 原始响应 | 保留 | 读取同一份，不改写 |
| 其他 51 条 | 未调用 | 仍未调用 |
| 语义能力对照 | 未完成 | 仍无法得出 |

本条模型给出的内容/条件状态依旧是 missing，范围是 uncertain、claim_broader；空白匹配
只修复可定位性，不会消除这些证据不足因素。没有将旧 ERROR 事后改记为成功，也未按此
单例计算准确率。原始计费总量仍是上一轮的 2,160 tokens，本轮没有新增用量。

## 可复现产物与检查

离线脚本：`tests/integration/replay_qualified_quote_alignment.py`。
输出目录：`output/qualified-quote-alignment-replay-v21/`，采用独占写入。
`replay.json` 保留全部 52 条身份、原状态、重放状态、来源哈希与新解释；
`summary.json` 单列 1 条已有响应与 51 条 not_run，`manifest.json` 冻结历史和新实现。

```powershell
python -X utf8 -m unittest tests.test_qualified_quote_alignment tests.test_qualified_quote_alignment_replay
python -X utf8 -m tests.integration.replay_qualified_quote_alignment replay
python -X utf8 -m tests.integration.replay_qualified_quote_alignment verify
```

导出后只使用 verify；再次执行 replay 会拒绝覆盖。脚本不读取凭据、不创建客户端、不调用
live.run，不继承旧实验预算。旧实验仍是 stopped_error，缓存验证不会触发模型请求。

按 ai-product-dev-pack 先建立失败测试，再完成实现。专项测试覆盖实际失败响应、36 种空白
组合、Unicode 原文坐标、精确匹配加空白变体造成的歧义、跨来源/重复/篡改引文和 JSON 契约，
另枚举 60 种 scope 状态/basis/relation 组合，与未改动的 v2 决定逐项对照。

最终验证结果：

- 专项 **24/24 通过**，3.536 秒；全量 **790/790 通过**，184.933 秒。
- 验收要求与测试引用 **218/218** 对齐；未弱化旧断言或改写旧测试。
- 新重放验证 **551 项来源哈希、2 项产物哈希**，重复本地重放与导出结果一致。
- manifest SHA-256：`30152cd21a756067906aa6c73d5cf8037c35e82842cc39852d6de7d202598c89`。
- replay SHA-256：`d1145450e2c75f6a911d011f0ecd6e9d3450e431de6778fb4b79acddcc94a03b`。
- 原 v2 summary SHA-256 仍为 `4fd1aafe09317d4dc5d10c766073ce8fa7da193a8ca8e9beb366d65339a5349c`。
- 生产 `kb_chat.py` SHA-256 仍为 `61dc1f00552a4f4c4722acaf8507e682ea3dd7a6e9ac9648fb93af69629637cc`。

代码复查重点为输入边界、失败关闭、原始坐标映射、契约兼容与历史防篡改。本轮没有数据库、
前端或生产 API 契约变更，没有 Git 提交/推送。这里的验收是本次手动执行的检查，不代表已
自动接入 CI 或发布为生产默认版本。

## 下一步

本修复不处理模型语义误判、PDF 解析、检索或生成。先确认这次独立修复，再明确后续真实
实验范围：是仅测试剩余 51 条，还是另做完整独立批次；不能混用离线重放与新响应宣称同一
完整实验。新的计费调用需重新确认，原 52 条准备输入与 v2 历史结果继续保留。
