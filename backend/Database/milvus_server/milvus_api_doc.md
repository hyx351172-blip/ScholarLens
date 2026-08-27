# 🧠 数据库管理模块接口文档

**模块名称**：数据库管理（Milvus Vector Store API）
**入口文件**：`milvus_api.py`
**服务端口**：`8000`
**启动命令**：
```bash
python milvus_api.py
```

---

## 1. 接口概览

| 接口名称 | 方法 | URL | 描述 |
|-----------|------|-----|------|
| 创建知识库 | `POST` | `/knowledge_base/create` | 创建新的向量集合 |
| 删除知识库 | `DELETE` | `/knowledge_base/delete` | 删除指定集合 |
| 列出知识库 | `GET` | `/knowledge_base/list` | 查看所有集合 |
| 上传文件 | `POST` | `/upload_json` | 上传并写入文档分块向量 |
| 文本搜索 | `POST` | `/search` | 语义检索文本内容 |
| 文件名搜索 | `POST` | `/search_by_filename` | 根据文件名检索 |
| 删除文件 | `DELETE` | `/delete` | 删除指定文件向量 |
| 健康检查 | `GET` | `/health` | 服务运行状态 |

---

## 2. 创建知识库 `/knowledge_base/create`

### 请求
```json
{
  "collection_name": "kb_demo",
  "embedding_dim": 2048
}
```

### 返回
```json
{
  "status": "success",
  "message": "created"
}
```

---

## 3. 上传文件 `/upload_json`

### 请求示例
```json
{
  "filename": "demo.md",
  "data": {
    "metadata": { "source": "pdf-extract-fast" },
    "chunks": [
      {
        "text": "这是一个chunk内容。",
        "page_start": 1,
        "page_end": 1,
        "text_length": 100,
        "continued": false
      }
    ]
  }
}
```

### 返回
```json
{
  "filename": "demo.md",
  "status": "success",
  "chunks_count": 25,
  "message": "文件上传成功，处理了25个chunks"
}
```

---

## 4. 检索接口 `/search`

### 请求
```json
{
  "collection_name": "kb_demo",
  "query_text": "文档核心结论是什么？",
  "top_k": 5
}
```

### 返回
```json
{
  "status": "success",
  "results": [
    {
      "score": 0.83,
      "chunk_text": "结论：系统采用...",
      "filename": "demo.md",
      "file_id": "uuid",
      "metadata": { "source": "pdf-extract-fast" }
    }
  ]
}
```

---

## 5. 删除文件 `/delete`

### 请求
```json
{
  "collection_name": "kb_demo",
  "filename": "demo.md"
}
```

### 返回
```json
{
  "status": "success",
  "message": "文件 demo.md 的向量已删除"
}
```

---

## 6. 健康检查 `/health`

```bash
GET /health
```

### 返回
```json
{
  "status": "ok",
  "time": "2025-10-13T12:00:00Z"
}
```
