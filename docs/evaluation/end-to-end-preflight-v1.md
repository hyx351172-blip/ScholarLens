# 完整链路验收 v1：环境预检受阻

后续：用户恢复Docker后已继续真实验收，见[完整链路实测报告](end-to-end-live-v1.md)。
以下保留首次预检原始结论，不代表当前环境仍受阻。

日期：2026-09-25。目标：上传 PDF → 解析/切分 → Milvus 入库 → 检索 → 回答 → 引用溯源。

## 实测状态

| 检查项 | 结果 |
|---|---|
| Extraction API 8006/health | 连接被拒绝 |
| Chunking API 8001/health | 连接被拒绝 |
| Milvus API 8000/health | 连接被拒绝 |
| Chat API 8501/health | 连接被拒绝 |
| 前端 5173 | 连接被拒绝 |
| Docker 引擎 | 不可用，Linux engine 命名管道不存在 |

排除沙箱影响后再次检查，Docker 引擎仍不可用。尝试启动已安装的 Docker Desktop，
进程启动后 backend 崩溃。启动日志明确报告：

```text
starting services: initializing Ingest server:
listening on unix://C:/Users/hp/AppData/Local/Docker/run/sailor-ingest.sock:
remove .../sailor-ingest.sock: The file cannot be accessed by the system.
```

证据来源：`C:/Users/hp/AppData/Local/Docker/log/host/com.docker.backend.exe.log`，
2026-09-25 15:05:38 UTC（本地 23:05:38）。这说明 Docker 启动失败，
尚不能据此确定该 socket 无法访问的更深层原因。

## 验收结论

**BLOCKED / NOT RUN，不是通过，也不是 RAG 质量失败。**

本轮未创建知识库、未上传文件、未调用 Embedding/LLM、未删除或重建容器，
未修改产品代码。没有执行恢复出厂设置、清空 Docker 数据或删除 socket。
此前 133 项离线回归通过不能证明真实用户链路通过。

ai-product-dev-pack 测试路由将本任务归为完整功能链路验收；环境编排是当前缺口。
该技能提供测试范围与判据，本身不替代实际执行证据或 CI 门。

## 环境恢复后的执行范围

1. 确认 Docker/Milvus 就绪，启动四个后端及前端；核对健康状态。
2. 创建独立验收知识库，不操作已有用户知识库。
3. 使用原始 PDF 走真实上传接口，检查 extraction/chunking/storage 全部完成。
4. 检查文档列表、Chunk 数、论文名称、章节、页码与原始内容对应。
5. 执行正文方法、表格数字、结论、无答案问题；多论文场景另测比较问题。
6. 保存每题的召回证据、回答、引用来源、耗时；核对引用页码与原 PDF。
7. 前端检查文档可见、回答流式完成、引用可点击并打开对应证据。
8. 分别报告传输/契约通过与内容质量，不把 HTTP 200 或来源编号存在视为事实正确。

首次可先用已存在的 Attention 论文做开发集冒烟，明确不宣称 held-out 泛化。
环境故障处理属于额外系统修复，需要先取得用户方向；不要恢复出厂设置。
