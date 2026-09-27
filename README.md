# ScholarLens

*Evidence-grounded scientific paper reading and question answering.*

---

ScholarLens 是面向学生与科研人员的论文阅读工作台：上传 PDF，围绕论文方法、公式和实验结果提问，再从回答中的引用回到论文原文。

项目的重点不是生成更长的总结，而是保留从 **论文结构 → 检索片段 → 回答引用** 的对应关系。当前为本地开发型 MVP；核心链路已有真实运行记录，实验模块与默认功能分开说明，不宣称生产就绪或所有回答均正确。

## 📋 能做什么

- **论文解析**：支持 Docling、快速文本和 VLM 模式；Docling 路径包含阅读顺序、章节层级、逻辑表，以及图/公式与正文关系的后处理。
- **结构化切分**：按正文、表格、图和公式组织 ScientificChunk，保留章节、页码、物理 block 与稳定 Chunk ID；对超长内容做有界拆分。
- **论文问答**：通过 Milvus Dense 检索证据；针对可解析的显式论文名称约束检索范围，生成带 `[S1]` 等来源编号的回答。
- **原文核对**：文献库、文档详情、切片浏览、引用证据抽屉和 PDF 页码跳转；区分答案实际引用与未引用检索候选。
- **可复核评测**：覆盖解析、切分、检索、回答和引用；Evaluation Harness 保存运行快照、检查质量门并对比实验。

出处与贡献边界见 [项目说明](docs/PROJECT_OVERVIEW.md)，配置步骤见 [本地启动指南](docs/LOCAL_SETUP.md)，结果与失败记录见 [评测索引](docs/evaluation/README.md)。

## ⚙️ 当前默认与可选功能

| 项目 | 当前行为 | 边界 |
| --- | --- | --- |
| 前端 PDF 上传 | `docling`，VLM repair 关闭 | 上传 API 自身默认仍为 `fast`；API 调用需显式选择 |
| Docling 切分 | 解析服务内部的 `StructureAwareChunker` | 快速/VLM 路径使用独立切分服务 |
| 检索 | `top_k=10`、`score_threshold=0.1` | 单查询 Dense；含章节意图等应用层选择逻辑 |
| 多查询规划 | `use_multi_query=false` | 后端可选；当前前端未提供开关 |
| 重排序 | `use_reranker=false` | 后端可选，需额外配置服务 |
| 回答 | `answer_mode="legacy"` | `claim_bound` 为可选实验分支，未切为默认 |

多查询中的 Query RRF 是对多路 **Dense** 结果融合，不是 BM25 + Dense 混合召回；后者尚未实现。独立表格重识别实验和 qualified-support 核验器也没有成为默认问答或解析步骤。

## 🔗 系统结构

以下展示入库与问答的数据流；Docling 的结构化切分不是强制绕经 8001 服务。

```mermaid
flowchart TB
    accTitle: ScholarLens Ingestion and Answer Flow
    accDescr: PDF uploads enter extraction and chunking before vector storage. Questions retrieve evidence through the chat service and return citations to the reader.
    reader["论文阅读界面 :5173"] -->|上传 PDF| extraction["解析与上传编排 :8006"]
    extraction -->|Docling| structured["论文 blocks 与结构化切分"]
    extraction -->|快速或 VLM| markdown_chunker["Markdown 切分 :8001"]
    structured -->|入库| milvus_api["向量与文档 API :8000"]
    markdown_chunker -->|产物经编排入库| milvus_api
    milvus_api --> vector_store[("Milvus :19530")]
    reader -->|问题| chat_api["检索与回答 :8501"]
    chat_api -->|证据检索| milvus_api
    chat_api -->|答案与引用| reader
```

生成模型、Embedding 以及可选 VLM/Reranker 通过外部 API 调用，不属于本地 Milvus。解析后处理与切分实现位于 [unified](backend/Information-Extraction/unified)；各服务职责见 [项目说明](docs/PROJECT_OVERVIEW.md)。

## 🔧 本地运行

使用 Python 3.11、Docker Desktop，以及能够运行本项目 TypeScript 测试的 Node.js 环境；当前本机 Node 为 24.19.0。后端依赖和前端锁文件分别位于 [requirements.txt](backend/requirements.txt)、[package-lock.json](frontend/package-lock.json)。

1. 在仓库根目录按 [本地启动指南](docs/LOCAL_SETUP.md) 创建环境、安装依赖。
2. 从 [.env.example](.env.example) 创建根目录 `.env`，填写生成与 Embedding 配置；前端仅配置服务地址。
3. 启动 Milvus、四个后端服务及前端，检查健康状态后访问 `http://localhost:5173`。

安装、首次模型下载以及真实问答需要相应网络连接；Embedding、生成和可选 VLM/Reranker 可能计费。不要直接批量运行 `tests/integration` 下的 live 脚本。

## 📊 已有验证与结果边界

以下均为历史报告中的指定版本和配置，不是本次文档整理重新测得的结果。

| 验证范围 | 已记录结果 | 不能据此声称 |
| --- | --- | --- |
| 三论文端到端开发验收 | Attention、BERT、LoRA 共 57 页、205 chunks；原始严格契约 13/16 | 所有 PDF 内容或浏览器操作均正确 |
| 文档范围修复回归 | 复用同批 16 题，在线检索/回答机械契约 16/16；无答案/空库拒答 4/4 | 泛化回答准确率或引用蕴含率 100% |
| 最新已记录后端回归 | v3 核验实验报告记录 844 项测试通过；专用追踪目录 237 条验收项对齐 | 已完成新版本发布或真实模型质量验收 |

详细证据：[原始多论文验收](docs/evaluation/multipaper-e2e-20260926.md)、[范围约束修复](docs/evaluation/document-scope-fix-20260926.md)、[最近一次回归记录](docs/evaluation/qualified-ids-pilot-v3.md)。修复复测没有重新上传论文或重跑全部浏览器操作；报告中的 AI 内容核对不等于用户确认的人工 Gold。

如需检查已冻结结果，可先使用不调用模型的 Harness 验证命令：

```powershell
python -m harness validate --config harness/configs/validated-replay-v1.json
```

该命令验证配置与输入，不重新测试系统。运行回放、比较和付费 live 模式的区别见 [Harness 说明](harness/README.md)。

## ⚠️ 已知限制

- 复杂表头、跨行跨列、扫描件、公式以及浮动图表的语义章节归属仍可能出错；已保留失败样本，未用离线特例改进替代整体效果结论。
- 来源 ID、页码和原文一致，只证明可追溯，不证明每项结论都被引用充分支持。
- 显式论文范围依赖目录名称/别名，不保证任意译名或代词解析，也不等同于用户权限隔离。
- 多论文验收中曾出现一次页面内容区空白、刷新后恢复，尚待复现；上传拖拽、取消、断网恢复等未全部完成浏览器验收。
- 当前优先收尾现有能力；暂停扩展表格与核验器实验，不自动消耗旧实验剩余调用额度。
- 全目录验收追踪存在扫描范围不一致：5 个早期编号定义在技术设计中，未纳入 `docs/specs` 扫描；发布前需统一追踪入口，见 [文档检查记录](docs/evaluation/README.md)。

## 📚 文档导航

- [项目定位、架构与改进范围](docs/PROJECT_OVERVIEW.md)
- [环境配置、启动、检查与排错](docs/LOCAL_SETUP.md)
- [评测结果与实验索引](docs/evaluation/README.md)
- [PDF 解析设计](docs/technical/PDF_PARSING_DESIGN.md) · [VLM 页面修复](docs/technical/VLM_PAGE_REPAIR.md)
- [多查询检索](docs/technical/MULTI_QUERY_RETRIEVAL.md) · [回答引用评测](docs/technical/ANSWER_CITATION_EVALUATION.md)
- [Evaluation Harness](harness/README.md)

## 🔐 数据与项目许可

密钥和本地配置不提交 Git；上传文件、解析产物、数据库数据及运行日志按 `.gitignore` 排除。调用外部模型时，问题、论文片段或页面图像会按所选流程发往服务商，使用前应确认处理权限与费用。

当前配置面向本地开发，部分服务绑定 `0.0.0.0`，容器包含开发凭据；未经鉴权、密钥暴露面和网络边界审查，不应直接暴露到公网。

基础工程沿用已有文档 RAG 的服务划分，ScholarLens 的论文场景改进另行记录，不把整套框架或外部模型宣称为原创。仓库暂未授予开源许可证，也不改变依赖与数据集自身的许可要求。
