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
- 回答上下文和来源响应使用稳定的 `[S1]`、`[S2]` 编号；默认提示词要求事实陈述逐句引用检索证据。
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

答案引用契约、确定性检查、语义判分边界和开发集实验结果见
[`docs/technical/ANSWER_CITATION_EVALUATION.md`](docs/technical/ANSWER_CITATION_EVALUATION.md)。

## 统一评测 Harness

项目提供配置化 Evaluation Harness，用同一入口编排已有检索、回答引用和
Claim–Citation Entailment 评测，保存不可覆盖的运行快照、执行质量门并比较
两次实验。先运行不调用外部模型的冻结结果回放：

```powershell
python -m harness validate --config harness/configs/validated-replay-v1.json
python -m harness run --config harness/configs/validated-replay-v1.json
```

完整命令、产物结构和可能产生模型费用的 Live 配置见
[`harness/README.md`](harness/README.md)。

局部表格 VLM 重识别为独立离线实验，不改变正式解析或知识库。裁图依据预测框，
Gold 仅用于单独评分；保存原始响应、失败记录及可视化对照，最多 3 次调用且不自动重试。
设计与验收见 [`docs/specs/table_vlm_experiment/implementation.md`](docs/specs/table_vlm_experiment/implementation.md)，
实测结果见 [`docs/evaluation/omnidocbench-table-vlm-v5.md`](docs/evaluation/omnidocbench-table-vlm-v5.md)。

后续 HTML 转录对照实现了流式计时、独立总超时、HTML → cells 校验及双模型实验，
最多 6 次请求且不重试。当前仅一张对照表改进，复杂表仍未通过，不接入生产；
见 [`表格 HTML A/B v6 报告`](docs/evaluation/omnidocbench-table-html-v6.md)。

表格专用方案 v7 增加独立 CPU PP-TableMagic 与 Qwen 原生 `table_parsing` 实验，
沿用固定裁图与严格结构准入。两组新候选均未通过，已保留失败结构、识别长度线索和回归记录；
未替换生产解析。见 [`表格专用解析 v7 报告`](docs/evaluation/omnidocbench-table-specialist-v7.md)。

解码上限审计 v8 通过真实概率张量及独立静态图副本，确认两张长表受长度上限截断。
延长后结构有效率从 0/3 提升至 2/3；尚未验证 OCR 内容，未接入生产。
见 [`表格解码上限 v8 报告`](docs/evaluation/omnidocbench-table-decoder-v8.md)。

OCR 绑定 v9 补充逐单元格追踪、完整 TEDS 与坐标内容诊断。科研表有提升，但另一张表
暴露空单元格错位；两者均未通过保守绑定门，继续保留生产基线。
见 [`表格 OCR 绑定 v9 报告`](docs/evaluation/omnidocbench-table-ocr-binding-v9.md)。

几何网格绑定 v10 修复了 EEPROM 样本的空格错列：保留空格并按坐标绑定，
完整 TEDS 达 0.9972（Docling 基线 0.9597），仍有 2 处 OCR 字符错误。
复杂表头继续拒绝并保留基线；只完成离线实验，未接入生产。
见 [`表格几何网格 v10 报告`](docs/evaluation/omnidocbench-table-grid-binding-v10.md)。

多层表头 v11 结合局部分隔线与 OCR 层次，恢复科研表的三层表头、跨行/跨列及
列标题路径。该样本结构 TEDS 为 1.0，完整 TEDS 为 0.9909；v10 已通过输出不变。
仍有 OCR/格式差异，规则适用范围有限，暂不接入生产。
见 [`多层表头修复 v11 报告`](docs/evaluation/omnidocbench-table-header-v11.md)。

冻结规则后的 v12 新页面扩测覆盖 20 张表，只有 2 张候选通过几何门，1 张改善、
1 张轻微退步；发现多记录被合并仍可能通过校验，以及旋转表、表内公式等缺口。
尚未通过泛化验收，仍不接入生产。官方分数、单例负值审计及 320 项测试记录见
[`20 张表扩测 v12 报告`](docs/evaluation/omnidocbench-table-unseen-v12.md)。

v13 增加多记录合并的保守拦截和有界四方向探测。开发回归集 20 张表完整
TEDS 均值从 0.5356 到 0.5843，2 张改善、0 张退步；其中旋转样本通过
校正方向后重新运行 Docling 达到 0.9399。尚未接入生产，仍需独立测试。
351 项回归/评分器测试及首次超时记录见
[`表格可靠性修复 v13 报告`](docs/evaluation/omnidocbench-table-safety-v13.md)。

v14 对有独立记录锚点的合并行进行受控重建，保留续行与 OCR 来源。
目标样本 TEDS 从 0.2885 到 0.9975；20 张表开发集均值从 0.5843 到 0.6198，
其余 19 张有效输出不变。真实正例仍只有 1 张，未接入生产。
见 [`合并行重建 v14 报告`](docs/evaluation/omnidocbench-table-records-v14.md)。

v15 固定选取 12 个未使用页面做离线验收：全部被上游网格或 HTML 检查拦截，
没有样本进入 v14 重建，两组 TEDS 同为 0.6814。因此尚未验证重建的泛化或
条件误拆率，仍不接入生产。见 [`新页面验收 v15 报告`](docs/evaluation/omnidocbench-table-records-validation-v15.md)。

v16 用缓存结果完成网格/OCR 叠加诊断：确认 4 张表触及检测模型 300 框上限，
修复 1 例孤立 HTML 包装标签，但其 5 条跨列 OCR 仍被拦截，最终输出及指标不变。
见 [`上游网格诊断 v16 报告`](docs/evaluation/omnidocbench-table-geometry-audit-v16.md)。

单元格 OCR 重读 v17 已完成：9 格局部重读改善跨列粘连，但未超过现有回退，
且低置信度结果触发拒绝；12 例有效输出保持不变。当前暂停追加表格解析优化，
转向端到端验证。见 [v17 实验报告](docs/evaluation/omnidocbench-table-cell-ocr-v17.md)。

## 路线图

- [ ] 为每个 Chunk 增加论文标题、章节、页码、DOI/arXiv ID 等科研元数据。
- [x] 后端生成稳定来源编号并完成逐句引用质量开发集验收。
- [x] 将回答中的 `[Sx]` 渲染为可点击引用，并展示论文、页码、章节、Chunk 与原文证据。
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
