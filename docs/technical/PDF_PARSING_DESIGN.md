# ScholarLens PDF 解析模块技术设计

> 状态：Docling 解析 v1、SectionHierarchyPostProcessor 与 TablePostProcessor 已实现并评测；结构感知切分仍为 Proposed
> 本次实现范围：科研论文 PDF 解析、章节树重建、逻辑表后处理与解析质量评测
> 后续范围：结构化 Chunk、Embedding、Milvus 与 RAG 回归
> 不包含：检索、Reranker、答案生成和前端改版

## 1. 背景与目标

当前系统使用 PyMuPDF4LLM 将 PDF 转为 Markdown，再按标题和字符长度切分。该方案可以处理普通正文，但会丢失表格、图注、公式和章节之间的结构关系，并产生重复的跨页 Bridge Chunk。

本模块的目标是把 PDF 转换为可追踪的论文结构，再由结构生成 Chunk，使每个检索结果都能定位到论文、章节、页码和原始内容块。

## 2. 技术决策

- 保留现有 PDF 提取服务 `:8006` 作为模块入口，第一版不调整服务数量。
- 增加统一 `ParserAdapter` 接口，避免业务代码依赖具体解析器。
- Docling 作为科研论文主解析器；现有 PyMuPDF4LLM 作为失败回退和效果基线。
- VLM 只用于后续处理低置信度页面，不默认解析整篇论文。
- 第一版不接入 GROBID；标题、作者、摘要和章节先使用解析结果与规则提取。
- 结构化 JSON 是数据真源，Markdown 仅作为展示和调试产物。

## 3. 处理流程

```text
PDF 上传
  → 文件校验与 SHA-256 去重
  → ParserAdapter 结构化解析
  → 论文结构归一化
  → SectionHierarchyPostProcessor（标题类型、合并标题、父子层级、section_path）
  → TablePostProcessor（Caption 绑定、碎片归并、Figure/Table 类型纠正）
  → 解析质量检查
  ← 当前迭代止于此处
  → 科研结构感知切分
  → 保存 document.json / chunks.json / quality-report.json
  → 交给现有 Embedding 与 Milvus 入库流程
```

主解析器失败时允许对整篇文档回退到 PyMuPDF4LLM，但必须在质量报告中记录 `parser`、`fallback_reason` 和失败阶段，禁止静默降级。

## 4. 核心数据契约

### 4.1 PaperDocument

```json
{
  "schema_version": "1.0",
  "paper_id": "sha256:...",
  "file_id": "file_...",
  "filename": "paper.pdf",
  "parser": "docling",
  "metadata": {
    "title": "...",
    "authors": ["..."],
    "abstract": "...",
    "year": 2026,
    "doi": null,
    "arxiv_id": null,
    "language": "en"
  },
  "sections": [],
  "blocks": [],
  "quality": {}
}
```

### 4.2 ContentBlock

每个原始内容块至少包含：

```json
{
  "block_id": "block_0042",
  "type": "paragraph",
  "text": "...",
  "page": 5,
  "bbox": [72.0, 110.0, 520.0, 250.0],
  "section_path": ["3 Method", "3.2 Architecture"],
  "confidence": 0.97,
  "relations": []
}
```

`type` 允许：`title`、`abstract`、`heading`、`paragraph`、`table`、`table_caption`、`figure`、`figure_caption`、`formula`、`reference`、`footnote`。

SectionHierarchyPostProcessor 使用受约束的章节编号规则和栈重建 Section 树，
将论文标题从 `heading` 修正为 `title`，并为标题、正文、表格、公式等所有后续
block 回填完整 `section_path`。合并 heading 只生成多个逻辑 Section，不拆除原始
物理 block；无编号标题使用最近的编号章节作为上下文回退并写入质量警告。

TablePostProcessor 不删除物理块，而是在 `relations` 中写入
`logical_table_id`、`logical_table_label`、`source_block_ids`、
`caption_block_ids`、`fragment_index`、`fragment_count` 和
`postprocess_status`。同时生成 `tables.json`，供后续结构感知切分消费。

公式块优先使用 Docling 的标准化 `text`；当 `text` 为空时回退到原始识别字段
`orig`，并在 `relations.formula_text_source` 中记录 `text`、
`orig_fallback` 或 `missing`。该回退只恢复 Unicode 数学文本，不声称生成了精确 LaTeX。

### 4.3 ScientificChunk

```json
{
  "chunk_id": "paper_id:chunk_0021",
  "paper_id": "sha256:...",
  "file_id": "file_...",
  "chunk_index": 21,
  "content_type": "paragraph",
  "text": "...",
  "retrieval_text": "论文标题\n章节路径\n正文",
  "page_start": 5,
  "page_end": 6,
  "section_path": ["3 Method", "3.2 Architecture"],
  "source_block_ids": ["block_0042", "block_0043"],
  "table_id": null,
  "is_generated_description": false
}
```

Milvus 必须保存可过滤字段：`paper_id`、`file_id`、`content_type`、`page_start`、`page_end`、`section_path` 和 `chunk_index`。

## 5. 切分规则

### 正文

- 先按章节边界，再按段落和句子合并。
- 目标大小为 400～700 tokens，最多不超过 900 tokens。
- 不跨一级章节；每个 Chunk 在 `retrieval_text` 中补充论文标题与章节路径。
- 不再生成固定字符截断式 Bridge Chunk。

### 摘要

- 标题、作者和摘要组成独立高优先级 Chunk。
- 摘要不得和引言正文合并。

### 表格

- 表格标题、表头、数据和脚注绑定为同一逻辑证据。
- 大表按行组切分，每个子 Chunk 重复表格标题和表头。
- 保存 `table_id` 与行范围；禁止在表格行中间按字符截断。

### 图片与公式

- 图片与 Figure Caption、相邻解释段落绑定；纯图片路径不得单独入库。
- 公式与公式编号及前后解释段落绑定；只有公式符号的块不得单独入库。
- 后续 VLM 生成的图表描述必须标记 `is_generated_description=true`，不得冒充论文原文。

### 参考文献

- 参考文献独立标记为 `reference`，默认不进入正文问答候选集。
- 后续文献追踪功能可单独启用参考文献检索。

## 6. 文件产物

```text
backend/output/extraction_results/{file_id}/
├── original.pdf
├── document.json
├── content.md
├── chunks.json
├── tables.json
├── figures.json
└── quality-report.json
```

所有 JSON 写入必须使用 UTF-8，并包含 `schema_version`。解析器升级导致结构变化时必须增加版本转换或重建索引，不得直接改变旧数据含义。

## 7. 错误与质量策略

- 文件不是 PDF、超过大小限制或无法打开：上传阶段失败，不创建索引。
- 主解析器失败：记录原因后尝试一次回退解析器。
- 两个解析器均失败：文档状态为 `failed`，不得向 Milvus 写入任何 Chunk。
- Embedding 或 Milvus 失败：保留解析产物以便重试，但文档不得显示为可用。
- 空页、乱码比例高、表格无表头、阅读顺序异常等写入质量报告。
- 日志不得包含 API Key、PDF 全文或外部模型的完整错误响应体。

## 8. 验收标准

### 8.1 本次解析迭代

- `AC-101`：四篇测试论文均生成 `document.json`、`docling-document.json`、`content.md` 和 `quality-report.json`。
- `AC-102`：71/71 页解析成功，标题、人工标注作者列表和摘要识别率均为 100%。
- `AC-103`：结构块的页码与 BBox 覆盖率为 100%。
- `AC-104`：本阶段没有生成 `chunks.json`，Docling 上传模式不会调用切分服务。
- `AC-105`：表格保持独立物理结构块，通过 relations 归并为逻辑表，并修正带明确 Figure Caption 的 Table 误判。
- `AC-106`：对四篇论文的 34 张人工标注逻辑表，逻辑表召回率、Source block 精确映射率、Caption block 精确映射率和 Figure/Table 类型修正率均为 100%。
- `AC-107`：四篇测试论文中 Docling 已识别的 9 个公式均能生成非空公式文本，且保留页码、BBox 和文本来源。
- `AC-108`：四篇测试论文均只有一个 `title` block；78 个编号子章节父节点一致率为 100%，进入章节后的 block 的 `section_path` 覆盖率为 100%，MAP-Graph 合并标题得到修复。
- 完整数据见 `docs/evaluation/docling-parsing-v1.md`。
- TablePostProcessor 评测见 `docs/evaluation/table-postprocessor-v1.md`。
- SectionHierarchyPostProcessor 评测见 `docs/evaluation/section-hierarchy-v1.md`。

### 8.2 后续端到端迭代

- `AC-PDF-001`：现有四篇测试论文均能生成合法的 `document.json` 和 `chunks.json`。
- `AC-PDF-002`：每个 Chunk 都包含 `paper_id`、页码、章节路径和 `source_block_ids`。
- `AC-PDF-003`：四篇论文的标题、作者和摘要均能生成独立元数据及摘要 Chunk。
- `AC-PDF-004`：人工标注表格中至少 90% 的 Caption、表头和数据保持绑定。
- `AC-PDF-005`：纯图片路径 Chunk、字符截断式表格 Bridge Chunk 均为 0。
- `AC-PDF-006`：解析失败或向量入库失败时，前端不得显示上传成功。
- `AC-PDF-007`：重新运行 baseline 后，Q01 能召回完整表格证据，Q03 能召回包含 GAAP 全称的摘要证据。
- `AC-PDF-008`：同一文件重复解析时，`paper_id` 和结构顺序保持稳定。

## 9. 测试计划

- 单元测试：数据模型校验、正文切分、表格切分、图片路径过滤、解析器回退。
- 契约测试：解析服务输出能被 Milvus 入库服务完整消费。
- 集成测试：真实 PDF 完成解析、切分并生成可搜索 Chunk。
- 回归测试：使用当前四篇论文和固定问题集生成 `baseline-v2`，与 `baseline-v1` 对比。

## 10. 实施顺序

1. 定义并测试 `PaperDocument`、`ContentBlock`、`ScientificChunk`。
2. 实现 `ParserAdapter` 和 Docling Adapter。
3. 实现结构归一化及质量报告。
4. 实现 SectionHierarchyPostProcessor 与章节结构评测。
5. 实现 TablePostProcessor 与逻辑表评测。
6. 实现论文结构感知切分。
7. 调整 Milvus Schema 和入库契约。
8. 用四篇论文重建测试知识库并生成 baseline v2。

本设计通过评审后再进入实现；现有 `test2` 和 baseline v1 在新链路验收前保持不变。
