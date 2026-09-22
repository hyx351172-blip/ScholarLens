# ScholarLens

> Evidence-grounded scientific paper reading and question answering.

ScholarLens 是一个面向学生与科研人员的论文阅读工作台。系统将 PDF 解析、结构化切分、向量检索和大模型问答串成完整链路，目标是让回答能够回到具体论文片段，而不是只生成不可验证的总结。

## 当前能力

- 上传 PDF，并使用快速、视觉语言模型或 Docling 模式提取结构化论文内容。
- 可选使用 VLM 对 Docling 困难页面进行证据受限的标题、摘要、Caption 关系修复及 Table→Figure 语义重分类；逻辑表按完整表号和主 Caption 的有界所有权归并。
- 按章节及表格、Figure、Formula 绑定关系生成可追溯的 ScientificChunk。
- Chunker 对无结构大表、超长表格行和 Figure 描述执行有界切分，并保留精确页码、物理 block 与稳定 Chunk ID。
- 按标题与页面边界切分文档，保留跨页上下文。
- 使用 Embedding 模型生成向量，并通过 Milvus 完成 Dense Top-K 检索。
- 使用相似度阈值过滤低相关片段。
- 后端可选启用跨论文 Query Planner、多路并行 Dense 召回、Query RRF
  去重和覆盖感知 Top-K；默认关闭并保留单查询降级路径。
- 基于召回片段进行流式或非流式问答。
- 后端已提供可选 Reranker 接口；前端当前默认关闭。
- 管理多个论文知识库，并查看文档、切片和原始 PDF。

当前版本尚未实现 BM25 + Dense 混合召回。跨论文多查询能力已完成开发集
验证和后端原型接入，但自动规划器仍需新的独立 Held-out 验收，因此不作为
生产准确率声明。

## 系统结构

```text
PDF
 └─> Extraction API :8006
      └─> Chunking API :8001
           └─> Milvus API :8000 ──> Milvus :19530
                └─> Chat API :8501
                     └─> React frontend :5173
```

```text
backend/
├── Information-Extraction/unified/  # PDF 与 VLM 提取
├── Text_segmentation/               # Markdown 结构化切分
├── Database/milvus_server/          # 向量存储、知识库和检索 API
├── chat/                            # RAG 问答与可选重排序
└── requirements.txt
frontend/                            # React + Vite 用户界面
docs/PROJECT_OVERVIEW.md             # 产品定位、范围和路线图
```

## 环境要求

- Python 3.11
- Node.js 18+
- Docker Desktop
- 可调用的生成模型和 Embedding 模型 API

## 本地启动

### 1. 配置环境变量

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env
```

编辑根目录 `.env`，至少填写 `API_KEY` 和 `EMBEDDING_API_KEY`。不要提交 `.env`，仓库只保留不含密钥的模板。

### 2. 安装后端依赖

```powershell
conda create -n scholarlens python=3.11 -y
conda activate scholarlens
python -m pip install -r backend/requirements.txt
```

### 3. 启动 Milvus

```powershell
docker compose -f backend/Database/milvus_server/docker-compose.yaml up -d
docker compose -f backend/Database/milvus_server/docker-compose.yaml ps
```

### 4. 启动四个后端服务

分别打开四个终端，在仓库根目录执行：

```powershell
python backend/Information-Extraction/unified/unified_pdf_extraction_service.py
python backend/Text_segmentation/markdown_chunker_api.py
python backend/Database/milvus_server/milvus_api.py
python backend/chat/kb_chat.py
```

健康检查地址：

- PDF 提取：`http://localhost:8006/health`
- 文本切分：`http://localhost:8001/health`
- Milvus API：`http://localhost:8000/health`
- RAG 对话：`http://localhost:8501/health`

### 5. 启动前端

```powershell
Set-Location frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。

## 检索基线

当前默认链路是：

```text
Query → Dense Embedding → Milvus Top-K → Score Threshold → LLM Answer
```

默认参数：`top_k=10`、`score_threshold=0.1`、`use_reranker=false`。后续将通过同一评测集对比 Dense、Dense + Reranker、BM25 + Dense + RRF + Reranker。

跨论文问题可以在 `/chat` 请求中设置 `use_multi_query=true`。后端会调用同一
生成模型产生结构化子查询，然后并行召回、去重并执行覆盖感知选择；任何规划
或子查询失败都会退回原始单查询。配置和返回 Trace 见
[`docs/technical/MULTI_QUERY_RETRIEVAL.md`](docs/technical/MULTI_QUERY_RETRIEVAL.md)。

## 路线图

- [ ] 为每个 Chunk 增加论文标题、章节、页码、DOI/arXiv ID 等科研元数据。
- [ ] 回答中生成可点击、可定位原文的引用。
- [ ] 增加 BM25 + Dense + RRF 混合检索。
- [x] 建立 Chunk 级完整证据 Hit@K、MRR、nDCG 和延迟评测。
- [x] 实现跨论文 Query Planner、多路召回及覆盖感知选择原型。
- [ ] 用新的独立 Held-out 集验收自动 Query Planner 和回答引用质量。
- [ ] 在前端加入多论文检索开关与执行 Trace。

## 安全与数据

- API Key 仅保存在本地 `.env` 中。
- 上传论文、解析结果、日志、PID、数据库数据与向量数据默认不进入 Git。
- 请仅上传有权处理的论文，并遵守相应论文与模型服务的使用条款。

## 项目状态与许可

ScholarLens 当前处于 MVP 重构阶段。仓库暂未授予开源许可证；在许可证明确前，公开可见不代表允许复制、修改或再分发。
