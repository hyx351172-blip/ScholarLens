# VLM 语义重分类评测（v1）

> 评测时间：2026-09-06  
> 范围：Docling `table` → 逻辑 `figure` 的证据受限重分类

## 问题来源

在三篇论文、100 个候选页的 Accurate 模式审计中，GPT-3 论文有 27 条建议把以
`Figure/Fig.` 开头的 Caption 绑定为 Table，分布于 11 页。这些建议的空间关系可能正确，
但对象语义错误，会虚增 Table Caption 覆盖率，并让 Chunker 生成错误类型的 Chunk。

## 验收规则

- 只接受 `table → figure`，拒绝反向或其他转换。
- Caption 必须以 `Figure/Fig.` 和可识别编号开头。
- Object 必须完整且唯一对应同页、尚未绑定 Caption 的 LogicalTable。
- 置信度必须达到阈值，所有 Block ID 必须来自当前解析结果。
- 保留物理 `ContentBlock.type=table`，仅迁移逻辑对象并记录审计关系。
- Chunker 必须将迁移后的对象输出为 Figure Chunk。

## 自动测试

- 全量单元与集成测试：54/54 通过。
- 覆盖主文、附录与补充材料编号：`Figure 2`、`Figure G.1`、`Figure S1`、
  `Fig A1`、`Table 3a`。
- 覆盖低置信度、无显式 Figure 标签、反向转换、普通 Binding 类型冲突等拒绝路径。
- 集成测试确认 API 结果的 LogicalTable/LogicalFigure 计数、关系字段和 Chunk 类型一致。

## 真实解析产物离线回放

使用 `2005.14165_language-models-are-few-shot-learners.pdf` 的既有完整 Docling 产物，
回放第 50 页的真实误分类对象：

| 检查项 | 结果 |
|---|---|
| Caption | `Figure G.1` |
| 重分类建议 | 接受 1 条 |
| 物理 Block 类型 | 保持 `table` |
| 逻辑类型 | `figure` |
| LogicalTable 数 | 37 → 36 |
| LogicalFigure 数 | 34 → 35 |
| 下游 Chunk 类型 | `figure` |

本轮回放不调用模型 API，验证的是已记录 VLM 建议进入新校验器后的迁移与下游行为。

## Accurate 在线回归

使用 `qwen3-vl-plus`、置信度阈值 0.8、144 DPI，对三篇论文的全部 100 个候选页
重新调用模型。总耗时 595.5 秒，平均 5.96 秒/页；API 运行警告为 0。

| 论文 | 候选页 | Caption Binding | 重分类 | 拒绝 | LogicalTable | LogicalFigure |
|---|---:|---:|---:|---:|---:|---:|
| Llama 3 | 46 | 61 | 0 | 2 | 34 → 34 | 27 → 27 |
| DeepSeek-R1 | 32 | 34 | 0 | 3 | 16 → 16 | 19 → 19 |
| GPT-3 | 22 | 16 | 28 | 35 | 37 → 9 | 34 → 62 |
| 合计 | 100 | 111 | 28 | 40 | 87 → 59 | 80 → 108 |

在线一致性检查结果：

- 28 条重分类全部来自 GPT-3 论文，Caption 均有显式 `Figure/Fig.` 标签。
- 28 个物理 Block 全部继续保持 `type=table`，并记录 `semantic_type=figure`。
- 28 个对象全部迁移到 LogicalFigure，且对应 28 个下游 Chunk 全部为 Figure Chunk。
- 没有任何以 Figure 开头的 Caption 被接受为 Table Binding。
- 模型对这 28 个对象同时重复输出了普通 Binding；校验器全部拒绝，没有产生双重绑定。
- GPT-3 剩余 9 个 LogicalTable 中，8 个是正常表格，1 个是首页作者列表的 Docling 物理误分类；
  没有遗留的 Figure→Table 漏分。

与上一轮相比，原先 27 条被错误计入 Table 覆盖率的 Figure 关系不再被接受；新 Prompt 还识别出
`Figure F.1`，因此本轮共完成 28 条语义重分类。

本轮也暴露出独立的模型稳定性问题：Llama 3 摘要在上一轮恢复成功，本轮模型没有返回摘要 Block ID，
因此仍保持缺失。该现象与重分类校验无关，后续应为元数据恢复设计独立 Prompt、有限重试或确定性回退。

完整实验产物保存在本地 `output/vlm_reclassifier_accurate_2026_09_06/`，该目录按项目规则
不进入 Git；本文件只保存可复核的聚合指标和结论。
