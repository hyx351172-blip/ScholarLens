# Structure-Aware Chunker 评测（v1）

> 日期：2026-08-29
> 范围：Docling 结构化结果 → ScientificChunk；不包含在线 Embedding 质量和检索指标

## 1. 实现范围

- 输入 `PaperDocument`、`LogicalTable`、`LogicalFigure` 和 `LogicalFormula`，不再从扁平 Markdown 猜测证据关系。
- 正文按 `section_path`、段落和句子切分，目标 600 tokens、上限 900 tokens。
- Abstract 独立成块；References 默认排除。
- 大表按照完整数据行分块，每块重复 Caption 和表头，不生成字符截断式 Bridge Chunk。
- Figure 重复 Caption，并携带绑定的解释段；没有 Caption 或文字描述的纯图片不入库。
- Formula 重复公式本体并携带绑定上下文；没有上下文的孤立公式不入库。
- 每个 Chunk 保存来源、上下文及 Caption block IDs，并为 Milvus 生成带论文标题和章节路径的 `retrieval_text`。

## 2. 自动化测试

在 `multimodal-rag` Conda 环境执行：

```powershell
E:\Anaconda\envs\multimodal-rag\python.exe -m unittest discover -s tests -v
```

结果：45/45 通过，其中新增 7 个 Chunker/接入测试，覆盖：

- 摘要独立与正文不跨章节；
- 超长段落按句子边界切分；
- 大表按行切分且重复 Caption/表头；
- Figure Caption/解释段绑定；
- Formula 上下文绑定和孤立公式过滤；
- 输出确定性、旧消费者兼容字段；
- Docling 结果生成并持久化 `chunks.json`。

## 3. 真实 PDF 冒烟测试

| 论文 | 页数 | Blocks | 表/图/公式 | Chunks | 最大 tokens | 超长 | 悬空关系 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BERT (`1810.04805`) | 16 | 259 | 8 / 5 / 0 | 44 | 658 | 0 | 0 |
| Mamba (`2312.00752`) | 36 | 545 | 15 / 11 / 8 | 104 | 875 | 0 | 0 |

Mamba 的 15 个逻辑表生成 24 个 Table Chunks，8 个有上下文的公式生成 8 个 Formula Chunks。
两张既无 Caption 也无文本描述的 Figure 被跳过并记录质量警告，没有生成纯图片路径 Chunk。

复现命令：

```powershell
E:\Anaconda\envs\multimodal-rag\python.exe scripts\smoke_structure_aware_chunker.py <PDF_PATH>
```

## 4. 当前边界

- `token_count` 是确定性本地估算值，不是具体 Embedding 模型的官方 tokenizer 结果。
- 本轮验证了 Milvus 入库契约转换，但没有调用在线 Embedding API 或真实 Milvus 执行检索评测。
- 当前 Figure 没有 Caption/文字描述时选择跳过；后续可接 VLM 描述并标记 `is_generated_description=true`。
- 19 篇压力测试集尚未全部执行，BERT 和 Mamba 分别覆盖普通双栏/表格及长附录/公式场景。
