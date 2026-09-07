# Caption-owned LogicalTable 评测（v1）

> 评测时间：2026-09-07  
> 分支：`codex/caption-owned-logical-tables`

## 目标

本迭代把逻辑表的归并依据从“文档内相同的整数表号”改为“一个主 Caption
拥有一个有界的物理表区域”。它解决了 `Table 3.1` 至 `Table 3.12` 被错误归并为
同一张 `Table 3` 的问题，并保留物理 block，供后续 Chunker 追溯。

## 归并规则

- 识别 `3`、`3.1`、`A.1`、`S1`、`3a` 等完整标识符；`Figure` 与 `Fig.` 使用同一套标识符规则。
- 一个物理 table 只能有一个主 Caption；冲突恢复结果优先，否则选择同页最近的 Caption。
- Caption 在目标方向上认领连续 table block：前置 Caption 向后扫描，后置 Caption 向前扫描。
- 扫描遇到正文、标题、跨页、另一 Caption 的目标，或不同的显式表标识符时停止。
- 兼容 Docling 的“带标识表格 → 重复后置 Caption → 无标识续表”输出模式。
- 没有 Caption 时，仅将直接相邻且完整标识符相同的 table block 合并；匿名表保持独立。
- VLM 后绑定 Caption 时复用完整标识符契约，不会再把 `Table 3.1` 截断成 `Table 3`。

每个被绑定的物理块写入 `logical_table_id`、`logical_table_identifier`、
`caption_block_ids`、`source_block_ids`、`fragment_index` 和 `fragment_count`。

## 自动化测试

专门验收场景：

| 编号 | 场景 | 结果 |
|---|---|---:|
| AC-TABLE-OWN-001 | 小数层级表号互不合并，并且重复处理幂等 | 通过 |
| AC-TABLE-OWN-002 | 前置 Caption 认领其后的连续物理表 | 通过 |
| AC-TABLE-OWN-003 | 后置 Caption 认领其前的连续物理表 | 通过 |
| AC-TABLE-OWN-004 | 遇到不同显式表号停止 | 通过 |
| AC-TABLE-OWN-005 | 前置 Caption 不吸收其上方无关表 | 通过 |
| AC-TABLE-OWN-006 | 两个 Caption 不能共同认领同一物理表 | 通过 |

`tests/test_table_postprocessor.py` 共 12 项通过；项目 `tests/` 全量测试共
60 项通过。AST 解析和 `git diff --check` 均通过。

## 真实论文回归

论文：*Language Models are Few-Shot Learners*（75 页）。

从 PDF 完整运行 Docling、语义后处理与 Chunker：

| 指标 | 结果 |
|---|---:|
| Content blocks | 743 |
| Logical tables | 34 |
| Logical figures | 50 |
| Logical formulas | 1 |
| Chunks | 184 |
| Oversized chunks | 7 |
| 悬空 block 引用 | 0 |

在同一份已保存的 743-block 结构化输入上重放旧、新算法，排除 PDF 解析波动：

| 指标 | 旧算法 | Caption ownership |
|---|---:|---:|
| Logical tables | 37 | 34 |
| Logical figures | 34 | 50 |
| Chunks | 303 | 184 |
| Oversized chunks | 134 | 7 |
| 重复 Caption owner | — | 0 |
| 重复 Source owner | — | 0 |
| 悬空 block 引用 | — | 0 |

新算法将 `Table 3.1` 至 `Table 3.12` 保持为 12 个独立逻辑表。逻辑 Figure
增加是因为完整 Figure 标识符使更多被 Docling 误判为 table 的图得到纠正，并非凭空
生成内容。

## 已知限制

- Caption 区域目前限定为同页；明确的跨页续表需要单独的 continuation 规则和测试。
- 只消费已被识别为 `caption` 的 block；仍被解析成 `paragraph` 的 Caption 依赖
  VLM 语义重分类或后续规则修复。
- 剩余 7 个超限 Chunk 属于“大型逻辑核心如何安全拆分”的 Chunker 问题，不在本次
  Caption 归属修改范围内。
