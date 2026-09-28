# 证据 ID 引用协议 v3：离线实现与验收

日期：2026-09-27。状态：**离线实现、831 项全量回归和产物冻结校验完成，尚未进行 v3 真实模型评测。**

本轮新增 API 调用 **0**。不消耗上一批剩余预算、不续跑失败批次、不改生产默认入口，
也没有 Git 提交或推送。v3 的模型准确率仍为 **null**。

## 改了什么

旧协议要求模型复制原文 quote；先后出现换行改空格、用 `[...]` 省略原文等契约错误。
新模块 `backend/chat/qualified_evidence_ids.py` 改为：**模型选择证据 ID，程序回填原文与坐标**。

| 环节 | v2 / v2.1 | v3 |
| --- | --- | --- |
| 模型返回 | 每项检查的 anchor_id + 自写 quote | 每项检查的 evidence_ids |
| 原文来源 | 对模型 quote 进行精确/有限空白匹配 | 按合法 ID 读取完整的已选 anchor |
| 引用范围 | anchor 内被模型摘取的连续子串 | 完整已有 anchor，显式标记 selected_anchor |
| 来源坐标 | 搜索匹配后推导 | 直接取经过验证的原始 start / end |
| 内容、范围、条件判断 | 模型判断 + 程序规则 | 本轮保持不变 |

例如模型的一项检查可以返回：

```json
{
  "status": "entailed",
  "reason": "简短说明该证据支持哪项事实。",
  "evidence_ids": ["S1:E0006"]
}
```

程序输出的引用包含 `anchor_id`、`source_id`、`filename`、`quote`、`source_start`、
`source_end`、`granularity=selected_anchor`、`provenance=program_resolved_id`。
原文保持换行、空格、公式、Unicode 和重复句，不需要模型重新复制。
理由中的文字不是已验证引文，不能被前端误当成程序还原的原文展示。

每项检查最多 3 个 ID；entailed / contradicted 必须至少 1 个，missing / uncertain 可为空。
不存在、未选择、重复、错误类型的 ID，以及自写 quote / offset / 总体 verdict 都会被拒绝。
三个检查和 packet/claim 身份仍必须完整匹配。

## 不做什么

- 不扩大检索上下文，不补相邻块，也不借另一条断言的证据。
- 不把两个不连续 anchor 拼成一段原文；它们保留独立引用和坐标。
- 不新增句子分割：E 仍是已有固定片段，U 仍是已有句/段单元。不是新增逐句精确标注能力。
- 不自动接受旧响应、不忽略旧引文错误、不修改已有统计。
- 不宣称 ID 合法便代表语义成立；`semantic_verified`、`human_verified` 始终为 false。

新版有独立版本与策略绑定的 packet_id。旧版结果不能换个版本号就直接当成 v3 实测结果。
`gate_answer` 只是显式调用的本地入口：检查缺失、无效、未支持或未确定时，不放行候选答案。
没有引入客户端、凭据读取、自动重试或默认服务接线。

## 历史响应的离线演示

读取原先保存的 **6 份**响应：首批 v2 的 1 份，加上上一轮剩余批次的 5 份。
所有来源先通过冻结哈希和原实验校验，原文件保持不变。

1. 未修改的 6 份旧响应在 v3 下全部拒绝，验证不存在偷偷兼容/升级历史结果。
2. 仅在测试脚本中显式构造格式适配输入：保留旧模型各项判断、理由、basis、relation；
   将已引用 anchor_id 转为 evidence_ids，使用新 packet_id，不保留旧 quote。
3. 这 **6 份注入的格式模拟输入**通过新契约，引用都等于所选 anchor 的原始文本和坐标。

这些记录明确标记 `schema_adapter_simulation_not_model_review`，不是新模型回答，
也不是对旧模型语义结论的重新评审。弃用旧 quote、改为完整 anchor 本身改变了引用粒度，
不能把它叫作无损恢复旧摘录。人工判定仍为 null。

### `[...]` 失败样本

SF-415 的旧响应仍是 `ERROR / missing_quote`；无任何追溯改分。
模拟选择其原先已引用的 `S1:E0002` 和 `S1:E0006` 后，程序能完整还原对应原文，
不含模型新插入的省略号。模拟最终结论仍是 **unsupported / not_in_evidence**，
因为保留的旧 conditions 判断为 missing。引用协议改变没有替模型推翻这个判断。

## 为什么暂时不同时修改范围/条件规则

本轮保留 v2 的语义提示词前缀和所有确定性规则，单独观察引用格式变化。
测试穷举 **2,880 组**组合：3 类量词文本 × 三项检查的 4³ 种状态 × 5 种 basis × 3 种 relation，
逐项核对 verdict、reason_code、guard_codes 和 effective_checks 与 v2 一致。
这证明规则迁移的一致性，不证明模型会做出正确判断。

上轮观察到的问题仍保留待校准（以下为助手分析，非人工 Gold）：

- SF-525：模型要求普通类别断言对“所有”核受体成立，还要求摘要描述特定实验设计，
  存在额外加严的迹象；但 recruitment / transient decrease 的支持边界需独立复核。
- SF-415：原始理由把生殖期长短分组的 RR 解释为携带者与非携带者比较，是比较对象问题；
  换成合法 ID 不能纠正这种语义误读。
- SF-852：条件句与总体效果的推断边界仍存在数据集口径分歧。

下一轮校准应覆盖普通类别陈述与显式 all/often 的对照、真正必要条件与一般研究背景的对照、
以及数值的比较对象。不能只为对齐单道 Gold 删掉所有范围约束。

## 数据准备与验证

新离线脚本：`tests/integration/prepare_qualified_evidence_ids.py`，仅提供 prepare / verify。
目标产物目录：`output/qualified-evidence-ids-v3/`。

- 保留原 **30 条 SciFact + 22 条专项回归**，断言、selected anchors 和 Gold 均不改。
- Gold 只存在 labels.json，不进入模型请求；22 条回归仍没有人工 Gold，不计算语义准确率。
- 准备 52 份新协议请求，合计 **301,717 字符**；字符数不是 token 数或费用。
- 保存 6 份带来源哈希、原错误诊断、注入响应和模拟结果的 simulations.json。
- 所有 **52 条 v3 仍未真实运行**；历史 6 份响应不占用这次未运行分母。
- future_call_proposal 的 approved=false；不得继承上一批授权或自动发起新调用。

测试先 RED 后 GREEN：分别观察到新模块和准备器缺失时的失败，再实现到通过。
专项测试 **26 项通过，7.182 秒**。覆盖包篡改、来源隔离、严格 JSON、坏 ID、原文还原、
规则等价、整答案门控、历史漂移、写入不可覆盖、模拟/实测隔离及网络禁用。
AC 追踪 **231 / 231 对齐**。

最终验证：

- 全量测试 **831 / 831 通过**，279.701 秒；本轮新增 26 项。
- 冻结 **635 个来源文件、56 个产物**；52 份请求、0 份真实模型结果。
- prepare 后的 verify 成功，重建的输入、标签、模拟记录、请求与汇总全部一致。
- 新文件及产物的凭据模式扫描命中 0；`git diff --check` 通过。
- Manifest SHA-256：`9365298cb07795cca0d4497bea3ca09549125ce076caa4dd6034c4364e02308e`。
- Summary SHA-256：`988e42a56908157aca80e0277fbb90b7f63ec4088d7535431ab26cd68fe2dc4e`。
- 上一轮 summary SHA-256 仍为 `8b2add6c861f6b87fd72b91fa79839de3be228957e21892fdbea52399c8c5796`。
- 生产入口 `kb_chat.py` SHA-256 仍为 `61dc1f00552a4f4c4722acaf8507e682ea3dd7a6e9ac9648fb93af69629637cc`。

完整产物位于 `output/qualified-evidence-ids-v3/`：entries.json、labels.json、
simulations.json、summary.json、manifest.json 和 request-*.json。

代码审查范围：请求边界、契约/版本一致性、null/类型/大小校验、无网络与生产写入，
以及历史文件不变性。本轮不涉及数据库迁移、前端设计或完整上传到回答的端到端验收。
这些检查不是 CI/hook 强制发布机制，也不等同于线上质量已验收。

离线复核命令：

```powershell
python -X utf8 -m unittest tests.test_qualified_evidence_ids tests.test_prepare_qualified_evidence_ids
python -X utf8 tests/integration/prepare_qualified_evidence_ids.py verify
```
