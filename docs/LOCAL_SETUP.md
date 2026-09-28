# ScholarLens 本地启动指南

*面向 Windows / PowerShell；按当前仓库代码整理。本文不是全新机器安装验收记录。*

---

## 📋 前置条件

- Python 3.11 环境；以下使用 Conda，已有合适环境可直接复用。
- Node.js 与 npm；本机为 Node 24.19.0，前端测试直接运行 `.ts` 文件，旧版 Node 可能不能运行测试。
- 已启动的 Docker Desktop，用于本地 Milvus、etcd 和 MinIO。
- 有效的生成模型、Embedding 模型 API 配置；VLM 修复和 Reranker 为可选能力。

所有后端命令均在**仓库根目录**执行，不是在 `backend` 或数据集目录。各终端都要激活同一个 Python 环境。下文不包含自动演示、付费实验或数据库清理。

## 🔧 安装与配置

### 安装依赖

```powershell
conda create -n scholarlens python=3.11 -y
conda activate scholarlens
python -m pip install -r backend/requirements.txt
python -m pip check
npm --prefix frontend ci
```

已有环境可跳过创建步骤。前端使用已有锁文件安装；表格专用离线实验依赖不是运行主流程的必需项，不需要额外安装 `scripts/requirements-table-specialist.txt`。

Docling 的 OCR/公式模型可能在第一次解析时下载，冷启动耗时不能当作每篇论文的稳定处理耗时。本轮未重新验证全新环境中的依赖安装。

### 创建配置文件

以下命令只创建缺失文件，不覆盖已经填写的密钥：

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
if (-not (Test-Path -LiteralPath 'frontend/.env')) {
    Copy-Item -LiteralPath 'frontend/.env.example' -Destination 'frontend/.env'
}
```

后端四个服务读取**仓库根目录 `.env`**。不要把唯一配置放在 `backend/.env`；不要把模型密钥写进前端的 `VITE_*` 变量。

| 配置组 | 变量 | 填写原则 |
| --- | --- | --- |
| 生成 / VLM | `API_KEY`、`MODEL_NAME`、`MODEL_URL` | 填写同一服务的模型与 OpenAI-compatible 基础地址 |
| Embedding | `EMBEDDING_API_KEY`、`EMBEDDING_MODEL_NAME`、`EMBEDDING_URL` | 独立 Embedding 模型；此处模板 URL 包含 `/embeddings` |
| Milvus | `MILVUS_HOST`、`MILVUS_PORT` | 本地模板为 `localhost:19530` |
| 服务 | 四组 `*_SERVICE_*` / `MILVUS_API_*` | 修改端口时同步消费者地址 |
| VLM repair / 重排 | `VLM_REPAIR_*`、`RERANKER_*` | 未启用对应能力时不必追加配置 |

模板当前使用 `qwen3-vl-plus` 和 `text-embedding-v4`。这是仓库配置示例，不是模型可用性、地区或价格保证；密钥所属服务、地域和模型权限需匹配。生成和 Embedding 可使用同一个具备相应权限的服务商密钥，但模型名与调用地址仍分别配置。

上传、解析、知识库查询须使用一致的 Embedding 模型和维度。更换 Embedding 后不要假设旧向量仍可比较，应使用隔离知识库重新索引，保留旧数据。

前端地址模板位于 [frontend/.env.example](../frontend/.env.example)。修改后端配置后重启对应服务；修改 `VITE_*` 后重启 Vite，已构建的页面则需要重新构建。

## ⚙️ 启动服务

### 先启动 Milvus

```powershell
docker compose -f backend/Database/milvus_server/docker-compose.yaml up -d
docker compose -f backend/Database/milvus_server/docker-compose.yaml ps
```

等待依赖和 Milvus 健康检查完成，而不是看到 `Started` 就直接上传。首次拉取镜像需要网络。不要删除 `volumes` 目录或重建已有数据来处理普通连接错误。

### 再启动四个后端

分别打开四个终端，进入同一仓库根目录并执行 `conda activate scholarlens`，每个终端只运行下列一条服务命令：

```powershell
# 终端 1：向量存储与检索
python -X utf8 backend/Database/milvus_server/milvus_api.py
```

```powershell
# 终端 2：快速/VLM 模式使用的 Markdown 切分
python -X utf8 backend/Text_segmentation/markdown_chunker_api.py
```

```powershell
# 终端 3：PDF 上传、解析与入库编排
python -X utf8 backend/Information-Extraction/unified/unified_pdf_extraction_service.py
```

```powershell
# 终端 4：检索问答
python -X utf8 backend/chat/kb_chat.py
```

`-X utf8` 用于统一这些 Python 进程的编码，避免 Windows 控制台字符编码差异。Docling 结构化切分在终端 3 的服务内执行；终端 2 仍为其他模式提供服务。

### 检查后端，再启动前端

```powershell
Invoke-RestMethod 'http://localhost:8000/health'
Invoke-RestMethod 'http://localhost:8001/health'
Invoke-RestMethod 'http://localhost:8006/health'
Invoke-RestMethod 'http://localhost:8501/health'
npm --prefix frontend run dev
```

访问终端实际显示的前端地址，默认 `http://localhost:5173`。如果端口被占用，Vite 可能使用其他端口；不要把旧标签页误认为本次服务。

健康接口表示进程能响应，不等于 Embedding、Milvus 检索、模型权限和完整链路均已通过。API 字段可在对应服务的 `/docs` 查看。若修改 8000 端口，还需核对 Chat 请求的 `milvus_api_url`；它默认仍是 `http://localhost:8000`。

## 📊 默认参数与无模型检查

前端上传默认 `docling`、VLM repair 关闭、`chunk_size=1500`、`chunk_overlap=200`、`max_page_span=3`。Docling 路径实际返回结构感知切分；直接调用上传 API 时应显式指定 `extraction_mode=docling`，否则 API 默认 `fast`。

前端问答默认 Top-K 10、阈值 0.1、Reranker 关闭；未发送多查询或回答模式参数，因此后端使用 `use_multi_query=false`、`answer_mode=legacy`。无需为运行主流程开启核验实验。

下面是可单独执行的代码检查，不发起真实模型评测；本轮文档整理不代表已重新运行全部命令：

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_*.py'
npm --prefix frontend test
npm --prefix frontend run build
python -m harness validate --config harness/configs/validated-replay-v1.json
```

Harness 冻结结果回放会在 `harness/runs/` 写入新的本地产物；不是重新解析、检索或生成，也不是当前在线模型的成绩。Live 配置可能计费，运行前另行确认范围。更多说明见 [Harness](../harness/README.md)。

## 💾 数据保存与停止

未设置路径覆盖时，上传和解析产物默认在 `backend/output/uploads/` 与 `backend/output/extraction_results/`。某些历史实验显式使用根目录 `output/`，应以相应运行配置或报告中的路径为准。

Milvus 的默认本地持久化目录在 `backend/Database/milvus_server/volumes/`，与 PDF 原件是不同的数据。`.gitignore` 不等于备份；需要备份时应同时考虑原件、解析产物、知识库映射与向量数据。

服务终端可用 `Ctrl+C` 停止。需要停止本项目容器且没有其他任务依赖它们时，执行：

```powershell
docker compose -f backend/Database/milvus_server/docker-compose.yaml stop
```

该操作停止服务，不删除已有持久化文件。

## ⚠️ 常见问题与安全边界

| 现象 | 优先检查 |
| --- | --- |
| 前端显示服务未启动 | 四个健康接口、前端 `.env` 地址和浏览器是否连接旧端口 |
| 上传时报 8000 错误 | Milvus 容器健康状态、8000 终端日志、Embedding 模型/维度/权限；不要直接清空库 |
| 上传后没有文档或 chunks | 检查解析、切分、存储三个阶段的实际状态及当前知识库，而不仅是文件上传成功提示 |
| 模型回答没有证据 | 知识库是否有 chunks、论文名称是否可匹配、返回候选与阈值；API 可用不等于召回正确 |
| 第一次 Docling 解析很慢 | 模型下载、OCR/公式模型加载、CPU 资源和日志；避免重复上传同一文件造成重复任务 |
| 修改配置后仍用旧模型 | 根目录 `.env`、运行进程是否重启、前端已有会话配置是否刷新 |

当前是本地开发配置，不含完整的公网部署安全方案。不要将密钥、论文正文或完整错误日志直接粘贴到公开 issue；对外发布前需要单独审查鉴权、CORS、配置接口和容器开发凭据。
