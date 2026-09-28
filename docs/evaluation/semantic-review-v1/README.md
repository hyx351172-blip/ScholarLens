# 人工语义验收集 v1（待审核）

当前评测范围：按用户要求暂时排除 Q02、Q06、Q08、Q17、Q20，保留15题。见 [过滤后汇总](FILTERED.md) 与 `selection-v1.json`。下方20题说明及原始review.json为完整归档，不代表5道争议题仍计入本轮子集；其余题也未自动获批。

从 [REVIEW.md](REVIEW.md) 开始阅读。20道开发题、60份历史回答，零新增模型调用。这里是AI整理草稿，**不是已人工标注的Gold**，不提供虚假的准确率。

## 如何检查

1. 先看问题与完整上下文，不先看模型回答；核对问题到底问谁、问什么。
2. 核对建议验收及原始证据。接受合理同义改写，不要求逐字复述参考答案。原标签可能有噪声，不自动当真。
3. 确定是可回答、无答案、有歧义或标签冲突。歧义/冲突题先单列，不能为了提升分数静默剔除或改标签。
4. 再展开三版回答，分别检查对象是否正确、是否回应属性、证据是否支持、是否足够完整、拒答是否合理。

你可以直接反馈“Q06 对象应改成……”“Q08 接受有条件的肯定回答……”；不必自己操作JSON。也可以在 `review.json` 中填写：

- `review.status`：`pending` 或 `approved`。
- `review.reviewer`：实际审核人，不自动填AI。
- `review.decision`：`answerable`、`unanswerable`、`ambiguous`、`label_conflict`。
- `review.notes`：确认范围、争议裁决及依据。
- 每版 `judgment` 五个维度：true/false/null，null表示尚未判断或不适用，并在notes说明。
- `error_tags`：可用 `wrong_target`、`wrong_attribute`、`unsupported_claim`、`incomplete`、`false_refusal`、`format_failure`、`label_conflict`。

`system_status=passed`不代表答案正确；`invalid_structure`引发拒答也不能计为正确识别无答案。正确引用的原文如果没有支持回答，仍判证据不支持。

## 优先检查

Q02（性能描述与原标签冲突）、Q06（真实会话/模拟集指代）、Q08（realistic含义）、Q17（平行语料范围）、Q20（基线任务范围）。Q01与Q05适合检查“回答有引用但没有回应问题”。所有20题仍需确认，未标争议不表示已通过。

## 文件与限制

- `review.json`：机器可读草稿、全部原始参考答案与三版回答。
- `REVIEW.md`：阅读版快照；若修改JSON，不应把旧Markdown当最新裁决。
- `contexts/`：完整QASPER文本，保留各题S编号；不是PDF页码。
- `provenance.json`：来源输入和历史输出SHA-256。

来源为已下载的QASPER v0.3 dev数据；原始论文和数据集的权利/许可不因生成此复核包而改变。此批次已反复用于开发，后续泛化评测需另留未参与修改的新批次。生成脚本拒绝覆盖目录，避免抹去人工编辑。确认门仅验证审批字段齐备，不自动判断审核内容正确，也尚未接入生产评测流水线。
