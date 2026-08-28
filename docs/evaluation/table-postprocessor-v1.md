# TablePostProcessor 评测（v1）

> 生成时间：2026-08-28T17:45:46.383204+08:00
> 人工基准：`docs/evaluation/table-ground-truth-v1.json`

## 评测边界

本报告评测逻辑表识别、物理 Source block 归并、Caption block 绑定和类型纠正。
它不评测逐单元格文本准确率，也不表示 Docling 已恢复原本损坏的表格网格。
例如 MemLineage Table 4 的 Caption 冲突已被正确归属，但 block_000254 内部的乱码网格仍需局部重解析。

## 总结

| 指标 | 结果 |
|---|---:|
| 论文 | 4 |
| 逻辑表 | 34 |
| 逻辑表召回率 | 100.0% |
| Source block 精确映射率 | 100.0% |
| Caption block 精确映射率 | 100.0% |
| Figure/Table 类型修正率 | 100.0% |
| 映射不一致 | 0 |

## 分论文结果

| 论文 | 预期/实际 | 召回 | Source 精确 | Caption 精确 | 类型修正 |
|---|---:|---:|---:|---:|---:|
| charactereval | 5/5 | 5 | 5 | 5 | 0 |
| gaap | 5/5 | 5 | 5 | 5 | 0 |
| memlineage | 13/13 | 13 | 13 | 13 | 1 |
| map_graph | 11/11 | 11 | 11 | 11 | 0 |

## 后处理状态

- `caption_attached`：4
- `caption_collision_recovered`：1
- `correct`：26
- `merged_fragments`：3

## 不一致项

- 无。
