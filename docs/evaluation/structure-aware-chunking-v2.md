# Structure-Aware Chunker 评测（v2）

> 日期：2026-09-19  
> 分支：`codex/oversized-evidence-chunking`  
> 输入：19 篇已保存的 Docling 结构化论文产物

## 1. 改进范围

- 无 Markdown 表头的表格使用有界逐行降级切分，不再整表生成超限 Chunk。
- 多物理 block 逻辑表逐 block 切分，每个子 Chunk 只引用实际来源 block 和页码。
- 超长表格行安全拆分，并保留相同 `row_start` / `row_end`。
- Figure 将 Caption 作为稳定锚点，长描述分段时重复 Caption。
- Table、Figure、Formula、Heading 等结构对象作为正文合并边界。
- `chunk_id` 由证据对象与 part 生成，不再依赖全局顺序；旧顺序 ID 保存在
  `legacy_chunk_id`。
- 新增 `table_identifier`、`fragment_indexes`，Chunk Schema 升级到 `1.1`。
- 支持注入生产模型 tokenizer；未注入时继续使用确定性本地估算器。
- 空文本 table block 不生成空 Chunk，并写入质量警告。

## 2. 自动化测试

新增 7 个验收场景：

| AC | 场景 | 结果 |
|---|---|---:|
| AC-CHUNK-V2-001 | 无结构大表严格遵守 token 上限 | 通过 |
| AC-CHUNK-V2-002 | 多 block 表格保存精确页码和来源 | 通过 |
| AC-CHUNK-V2-003 | 超长 Figure 描述切分并重复 Caption | 通过 |
| AC-CHUNK-V2-004 | 正文不跨结构证据合并 | 通过 |
| AC-CHUNK-V2-005 | 前序 Chunk 插入不改变证据 Chunk ID | 通过 |
| AC-CHUNK-V2-006 | 可注入真实 tokenizer | 通过 |
| AC-CHUNK-V2-007 | 空表跳过并记录警告 | 通过 |

Chunker 专项测试 13/13 通过；项目全量测试 67/67 通过。

## 3. 19 篇论文回归

复现命令：

```powershell
E:\Anaconda\envs\multimodal-rag\python.exe scripts/evaluate_chunker_v2.py `
  C:\Users\hp\Desktop\ScholarLens\output\parser_dataset_full_2026_09_06\papers
```

| 指标 | 结果 |
|---|---:|
| 论文 | 19 |
| Chunks | 2,057 |
| 最大 Chunk tokens | 900 |
| 超限 Chunk | 0 |
| 悬空 block 引用 | 0 |
| 重复 Chunk ID | 0 |
| 未覆盖的非空 table source | 0 |

GPT-3 论文在 v1 Caption ownership 回归中仍有 7 个超限 Chunk；v2 在相同的
900-token 上限下将其降为 0。Chunk 数从 184 增至 215，原因是正文不再跨 Figure、
Table 和 Formula 合并，同时多页表格使用更精确的物理来源边界。

Nougat 论文存在 4 个 Docling 输出的空文本 table block。v2 不为它们伪造内容，
而是跳过并产生 `no textual table evidence` 警告；这四项不计入非空来源缺失。

## 4. 边界

- 默认 token 计数仍是本地估算；接入实际 Embedding 模型时应注入对应 tokenizer。
- 本报告验证切分、来源完整性和预算边界，不代表检索相关性已经提高。
- Chunk Schema 1.1 是兼容性扩展，但 `chunk_id` 语义发生变化；重新上线时需要重建
  Milvus 索引，迁移期间可使用 `legacy_chunk_id` 对照旧产物。

