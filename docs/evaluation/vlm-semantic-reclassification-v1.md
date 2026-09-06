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
新 Prompt 对在线模型是否稳定使用 `reclassifications` 字段，仍需下一轮付费实时回归评测。
