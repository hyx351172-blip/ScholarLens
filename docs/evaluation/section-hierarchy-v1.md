# SectionHierarchyPostProcessor 评测（v1）

> 生成时间：2026-08-28T19:39:03.653234+08:00

## 评测边界

本报告验证编号章节的结构一致性、合并标题修复和 section_path 覆盖率。
无编号标题使用上下文回退，尚未建立人工层级 ground truth，因此不宣称其准确率为 100%。

## 总结

| 指标 | 结果 |
|---|---:|
| 单一论文标题 | 4/4 |
| 编号子章节 | 78 |
| 编号父节点一致率 | 100.0% |
| Section path 覆盖率 | 100.0% |
| 合并标题修复 | 1 |
| 待人工复核无编号标题 | 4 |
| 编号父节点不一致 | 0 |
| Abstract 章节 | 4 |
| Appendix 章节 | 25 |
| 特殊章节正文绑定率 | 100.0% |
| Appendix 字母层级不一致 | 0 |

## 分论文结果

| 论文 | 标题 | Sections | Level 分布 | 编号父节点 | Path 覆盖 | 合并修复 | 回退标题 |
|---|---:|---:|---|---:|---:|---:|---:|
| charactereval | 1 | 27 | L1:14, L2:13 | 12/12 | 100.0% | 0 | 1 |
| gaap | 1 | 24 | L1:11, L2:13 | 13/13 | 100.0% | 0 | 0 |
| memlineage | 1 | 53 | L1:11, L2:40, L3:2 | 39/39 | 100.0% | 0 | 3 |
| map_graph | 1 | 41 | L1:8, L2:20, L3:13 | 14/14 | 100.0% | 1 | 0 |

## 待人工复核

- `charactereval`：block_000108: inferred unnumbered heading level 2 for 'Ethical Consideration'
- `memlineage`：block_000018: inferred unnumbered heading level 2 for 'Contributions.'
- `memlineage`：block_000062: inferred unnumbered heading level 3 for 'G3: Cross-session persistence of provenance.'
- `memlineage`：block_000180: inferred unnumbered heading level 3 for 'Adapter sequence.'
