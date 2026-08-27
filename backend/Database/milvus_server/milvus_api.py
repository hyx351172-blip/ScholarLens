import uuid
import json
import os
import requests
import time
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility
from dotenv import load_dotenv

# 加载仓库根目录 .env 文件
PROJECT_ROOT = Path(__file__).resolve().parents[3]
env_path = PROJECT_ROOT / '.env'
load_dotenv(dotenv_path=env_path, override=True)

# 环境变量配置
MILVUS_HOST = os.getenv("MILVUS_HOST")
MILVUS_PORT = os.getenv("MILVUS_PORT")
EMBEDDING_URL = os.getenv("EMBEDDING_URL")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")
UPLOAD_BASE_DIR = Path(os.getenv(
    "UPLOAD_BASE_DIR",
    str(PROJECT_ROOT / "backend" / "output" / "uploads")
))
EXTRACTION_RESULTS_DIR = Path(os.getenv(
    "EXTRACTION_RESULTS_DIR",
    str(PROJECT_ROOT / "backend" / "output" / "extraction_results")
))

# Pydantic 模型定义
class DocumentChunk(BaseModel):
    chunk_text: str
    filename: str
    file_id: Optional[str] = None
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = {}

class UploadKBRequest(BaseModel):
    collection_name: str
    file_data: Dict[str, Any]

class UploadResponse(BaseModel):
    filename: str
    file_id: str
    status: str
    message: str
    chunks_count: int = 0

class SearchRequest(BaseModel):
    collection_name: str
    query_text: str
    top_k: int = 10
    filter_expr: Optional[str] = None

class SearchByFilenameRequest(BaseModel):
    collection_name: str
    filename: str
    top_k: int = 10

class DeleteRequest(BaseModel):
    collection_name: str
    filename: str

class DeleteKBRequest(BaseModel):
    collection_name: str

class MilvusRAGService:
    def __init__(self):
        self.milvus_host = MILVUS_HOST
        self.milvus_port = MILVUS_PORT
        self.embedding_url = EMBEDDING_URL
        self.embedding_model_name = EMBEDDING_MODEL_NAME
        self.embedding_api_key = EMBEDDING_API_KEY

        print(f"Milvus配置: {self.milvus_host}:{self.milvus_port}")
        print(f"Embedding配置: URL={self.embedding_url}, Model={self.embedding_model_name}")

        self.connect_to_milvus()

    def connect_to_milvus(self):
        """连接到Milvus服务"""
        try:
            connections.connect(
                "default",
                host=self.milvus_host,
                port=self.milvus_port
            )
            print(f"Successfully connected to Milvus at {self.milvus_host}:{self.milvus_port}")
        except Exception as e:
            print(f"Failed to connect to Milvus: {e}")
            raise

    def generate_embedding(self, text: str) -> List[float]:
        """单个文本生成向量（用于query）"""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.embedding_api_key}"
            }

            payload = {
                "model": self.embedding_model_name,
                "input": [text]
            }

            response = requests.post(self.embedding_url, json=payload, headers=headers, timeout=30)

            if response.status_code == 200:
                result = response.json()
                embedding = result["data"][0]["embedding"]
                return embedding
            else:
                print(f"Embedding API error: {response.status_code}")
                fallback_dim = self.get_model_dimension(self.embedding_model_name)
                return np.random.rand(fallback_dim).tolist()

        except Exception as e:
            print(f"Embedding generation failed: {e}")
            fallback_dim = self.get_model_dimension(self.embedding_model_name)
            return np.random.rand(fallback_dim).tolist()

    def generate_embeddings_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        批量生成embeddings，使用线程池并行处理多个批次

        Args:
            texts: 文本列表
            batch_size: 每批次处理的文本数量

        Returns:
            按顺序返回的embedding列表
        """
        if not texts:
            return []

        total_texts = len(texts)
        print(f"开始批量生成 {total_texts} 个文本的embeddings，批次大小: {batch_size}")

        # 预分配结果列表
        all_embeddings = [None] * total_texts
        start_time = time.time()

        def process_batch(batch_idx: int, batch_texts: List[str]) -> tuple:
            """处理单个批次"""
            start_idx = batch_idx * batch_size

            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.embedding_api_key}"
                }

                payload = {
                    "model": self.embedding_model_name,
                    "input": batch_texts
                }

                response = requests.post(
                    self.embedding_url,
                    json=payload,
                    headers=headers,
                    timeout=60
                )

                if response.status_code == 200:
                    result = response.json()
                    batch_embeddings = [item["embedding"] for item in result["data"]]
                    return batch_idx, start_idx, batch_embeddings, None
                else:
                    error_msg = f"API返回错误: {response.status_code}"
                    print(f"批次 {batch_idx + 1} {error_msg}")
                    fallback_dim = self.get_model_dimension(self.embedding_model_name)
                    batch_embeddings = [np.random.rand(fallback_dim).tolist() for _ in batch_texts]
                    return batch_idx, start_idx, batch_embeddings, error_msg

            except Exception as e:
                error_msg = f"处理异常: {str(e)}"
                print(f"批次 {batch_idx + 1} {error_msg}")
                fallback_dim = self.get_model_dimension(self.embedding_model_name)
                batch_embeddings = [np.random.rand(fallback_dim).tolist() for _ in batch_texts]
                return batch_idx, start_idx, batch_embeddings, error_msg

        # 准备批次
        batches = []
        for i in range(0, total_texts, batch_size):
            batch_end = min(i + batch_size, total_texts)
            batches.append((i // batch_size, texts[i:batch_end]))

        # 使用线程池并行处理
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_batch = {
                executor.submit(process_batch, batch_idx, batch_texts): batch_idx
                for batch_idx, batch_texts in batches
            }

            for future in as_completed(future_to_batch):
                batch_idx, start_idx, batch_embeddings, error = future.result()

                # 填充结果
                for i, embedding in enumerate(batch_embeddings):
                    all_embeddings[start_idx + i] = embedding

        elapsed = time.time() - start_time
        rate = total_texts / elapsed if elapsed > 0 else 0
        print(f"批量生成完成，总耗时: {elapsed:.2f}秒，平均速率: {rate:.2f} 文本/秒")

        return all_embeddings

    def get_model_dimension(self, model_name: str) -> int:
        """获取模型的向量维度"""
        model_dimensions = {
            "jina-embeddings-v4": 2048,
            "jina-embeddings-v3": 1024,
            "jina-embeddings-v2-base-zh": 512,
            "text-embedding-ada-002": 1536,
            "text-embedding-v4": 1024
        }
        return model_dimensions.get(model_name, 1024)

    def create_collection_schema(self, embedding_dim: int = 1024) -> CollectionSchema:
        """创建Collection的Schema"""
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="chunk_text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="filename", dtype=DataType.VARCHAR, max_length=255),
            FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
            FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="created_at", dtype=DataType.VARCHAR, max_length=50)
        ]

        schema = CollectionSchema(
            fields=fields,
            description="RAG Knowledge Base Collection"
        )
        return schema

    def generate_collection_id(self) -> str:
        """生成符合Milvus规范的collection ID"""
        import time
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        return f"kb_{timestamp}"

    def save_name_mapping(self, collection_id: str, display_name: str):
        """保存collection ID和显示名称的映射关系到JSON文件"""
        import json
        from pathlib import Path

        # 映射文件路径
        mapping_file = Path(__file__).parent / "collection_name_mapping.json"

        # 读取现有映射
        mappings = {}
        if mapping_file.exists():
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mappings = json.load(f)

        # 更新映射
        mappings[collection_id] = {
            "display_name": display_name,
            "created_at": datetime.now().isoformat()
        }

        # 保存映射
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump(mappings, f, ensure_ascii=False, indent=2)

        print(f"Saved mapping: {collection_id} -> {display_name}")

    def get_name_mapping(self, collection_id: str = None) -> Dict[str, Any]:
        """获取名称映射"""
        import json
        from pathlib import Path

        mapping_file = Path(__file__).parent / "collection_name_mapping.json"

        if not mapping_file.exists():
            return {}

        with open(mapping_file, 'r', encoding='utf-8') as f:
            mappings = json.load(f)

        if collection_id:
            return mappings.get(collection_id, {})
        return mappings

    def delete_name_mapping(self, collection_id: str):
        """删除名称映射"""
        import json
        from pathlib import Path

        mapping_file = Path(__file__).parent / "collection_name_mapping.json"

        if not mapping_file.exists():
            return

        with open(mapping_file, 'r', encoding='utf-8') as f:
            mappings = json.load(f)

        if collection_id in mappings:
            del mappings[collection_id]

            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)

            print(f"Deleted mapping: {collection_id}")

    def create_knowledge_base(self, display_name: str, embedding_dim: int = None) -> tuple:
        """
        创建知识库（Collection）

        Args:
            display_name: 用户输入的显示名称（可以是中文）
            embedding_dim: embedding维度

        Returns:
            (collection_id, success): 返回collection ID和是否成功
        """
        try:
            # 生成符合Milvus规范的collection ID
            collection_id = self.generate_collection_id()

            if utility.has_collection(collection_id):
                # 理论上不会发生，因为使用时间戳
                collection_id = self.generate_collection_id()

            if embedding_dim is None:
                embedding_dim = self.get_model_dimension(self.embedding_model_name)

            schema = self.create_collection_schema(embedding_dim)
            collection = Collection(name=collection_id, schema=schema)

            # 创建索引
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024}
            }
            collection.create_index(field_name="embedding", index_params=index_params)

            # 参考milvus_kb_service: 创建后立即加载collection
            collection.load()

            # 保存名称映射
            self.save_name_mapping(collection_id, display_name)

            print(f"Created knowledge base: {collection_id} ('{display_name}') with embedding_dim: {embedding_dim}")
            return collection_id, True

        except Exception as e:
            print(f"Failed to create knowledge base: {e}")
            raise

    def delete_knowledge_base(self, collection_id: str) -> bool:
        """删除知识库"""
        try:
            if utility.has_collection(collection_id):
                utility.drop_collection(collection_id)
                # 同时删除名称映射
                self.delete_name_mapping(collection_id)
                print(f"Deleted knowledge base: {collection_id}")
                return True
            return False
        except Exception as e:
            print(f"Failed to delete knowledge base: {e}")
            raise

    def create_or_get_collection(self, collection_name: str, embedding_dim: int = None) -> Collection:
        """创建或获取Collection"""
        if utility.has_collection(collection_name):
            collection = Collection(collection_name)
            # 确保已加载
            try:
                collection.load()
            except Exception as e:
                print(f"加载已存在的collection时出错: {e}")
        else:
            if embedding_dim is None:
                embedding_dim = self.get_model_dimension(self.embedding_model_name)

            schema = self.create_collection_schema(embedding_dim)
            collection = Collection(name=collection_name, schema=schema)

            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024}
            }
            collection.create_index(field_name="embedding", index_params=index_params)

            # 参考milvus_kb_service: 创建后立即加载
            collection.load()

        return collection

    def parse_json_file(self, json_data: Dict[str, Any]) -> List[DocumentChunk]:
        """解析JSON文件并转换为DocumentChunk列表"""
        try:
            documents = []

            # 提取基本信息
            filename = json_data.get("filename", "unknown.txt")
            if filename.startswith("/"):
                filename = os.path.basename(filename)

            data_section = json_data.get("data", {})
            chunks = data_section.get("chunks", [])

            print(f"开始解析文件: {filename}, 包含 {len(chunks)} 个chunks")

            # 为每个chunk创建DocumentChunk
            for i, chunk in enumerate(chunks):
                chunk_text = chunk.get("text", "")
                if not chunk_text.strip():
                    print(f"跳过空chunk {i}")
                    continue

                # 构建metadata
                metadata = {
                    "page_start": chunk.get("page_start", 1),
                    "page_end": chunk.get("page_end", 1),
                    "pages": chunk.get("pages", [1]),
                    "text_length": chunk.get("text_length", len(chunk_text)),
                    "continued": chunk.get("continued", False),
                    "cross_page_bridge": chunk.get("cross_page_bridge", False),
                    "is_table_like": chunk.get("is_table_like", False),
                    "chunk_index": i
                }

                # 添加文档级别的metadata
                if "metadata" in data_section:
                    metadata.update(data_section["metadata"])

                doc = DocumentChunk(
                    chunk_text=chunk_text,
                    filename=filename,
                    file_id=str(uuid.uuid4()),
                    metadata=metadata
                )
                documents.append(doc)

            print(f"成功解析 {len(documents)} 个有效chunks")
            return documents

        except Exception as e:
            print(f"Failed to parse JSON file: {e}")
            raise HTTPException(status_code=400, detail=f"JSON解析失败: {str(e)}")

    def insert_documents(self, collection_name: str, documents: List[DocumentChunk]) -> List[str]:
        """
        批量插入文档到Collection
        参考milvus_kb_service.py的操作方式
        """
        if not documents:
            return []

        try:
            # 准备数据
            print(f"准备 {len(documents)} 个文档数据")

            chunk_texts = []
            filenames = []
            file_ids = []
            metadatas = []

            for doc in documents:
                chunk_texts.append(doc.chunk_text)
                filenames.append(doc.filename)
                file_ids.append(doc.file_id or str(uuid.uuid4()))
                metadatas.append(json.dumps(doc.metadata, ensure_ascii=False))

            # 批量生成embeddings
            print(f"批量生成embeddings")
            EMBED_BATCH_SIZE = 32
            embeddings = self.generate_embeddings_batch(chunk_texts, batch_size=EMBED_BATCH_SIZE)

            # 检测embedding维度
            embedding_dim = len(embeddings[0])
            print(f"检测到embedding维度: {embedding_dim}")

            # 创建或获取collection（会自动load）
            collection = self.create_or_get_collection(collection_name, embedding_dim)

            # 分批插入Milvus
            print(f"分批插入Milvus")
            MILVUS_BATCH_SIZE = 1000
            total_docs = len(documents)

            current_time = datetime.now().isoformat()

            for i in range(0, total_docs, MILVUS_BATCH_SIZE):
                end_idx = min(i + MILVUS_BATCH_SIZE, total_docs)

                # 准备当前批次数据 - 参考milvus_kb_service.py的entities格式
                entities = [
                    chunk_texts[i:end_idx],
                    filenames[i:end_idx],
                    file_ids[i:end_idx],
                    embeddings[i:end_idx],
                    metadatas[i:end_idx],
                    [current_time] * (end_idx - i)
                ]

                # 插入 - 参考milvus_kb_service.py，不调用flush
                collection.insert(entities)

            print(f"插入完成，共 {len(file_ids)} 条文档")

            # 插入完成后，确保collection保持加载状态（虽然理论上已经加载）
            try:
                if not collection.has_index():
                    collection.load()
                    print("插入后重新加载collection")
            except Exception as load_err:
                print(f"插入后加载collection警告: {load_err}")

            return file_ids

        except Exception as e:
            print(f"插入文档失败: {e}")
            raise HTTPException(status_code=500, detail=f"插入文档失败: {str(e)}")

    def search_by_text(self, collection_name: str, query_text: str,
                      top_k: int = 10, filter_expr: Optional[str] = None) -> List[Dict]:
        """根据文本搜索相似文档"""
        try:
            if not utility.has_collection(collection_name):
                raise HTTPException(status_code=404, detail=f"知识库 {collection_name} 不存在")

            # 生成查询向量
            print(f"为查询文本生成embedding: {query_text[:50]}...")
            query_embedding = self.generate_embedding(query_text)

            collection = Collection(collection_name)

            # 参考milvus_kb_service: 确保collection已加载
            try:
                # 检查collection是否有索引（间接判断是否需要load）
                if not collection.has_index():
                    print(f"Collection '{collection_name}' 没有索引，正在加载...")
                    collection.load()
                else:
                    # 即使有索引，也尝试load以确保在内存中
                    collection.load()
                print(f"Collection '{collection_name}' 已确保加载")
            except Exception as load_err:
                print(f"加载collection时出错: {load_err}")
                # 尝试继续，可能已经加载

            search_params = {
                "metric_type": "COSINE",
                "params": {"nprobe": 10}
            }

            output_fields = ["chunk_text", "filename", "file_id", "metadata", "created_at"]

            print(f"执行向量搜索，top_k: {top_k}")
            results = collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=filter_expr,
                output_fields=output_fields
            )

            # 格式化结果
            formatted_results = []
            for hits in results:
                for hit in hits:
                    result = {
                        "id": hit.id,
                        "score": hit.score,
                        "chunk_text": hit.entity.get("chunk_text"),
                        "filename": hit.entity.get("filename"),
                        "file_id": hit.entity.get("file_id"),
                        "metadata": json.loads(hit.entity.get("metadata", "{}")),
                        "created_at": hit.entity.get("created_at")
                    }
                    formatted_results.append(result)

            print(f"搜索完成，找到 {len(formatted_results)} 个结果")
            return formatted_results

        except Exception as e:
            print(f"搜索失败: {e}")
            import traceback
            print(f"详细错误: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")

    def search_by_filename(self, collection_name: str, filename: str, top_k: int = 10) -> List[Dict]:
        """根据文件名检索知识库内信息"""
        try:
            if not utility.has_collection(collection_name):
                raise HTTPException(status_code=404, detail=f"知识库 {collection_name} 不存在")

            collection = Collection(collection_name)

            # 确保collection已加载
            try:
                collection.load()
                print(f"Collection '{collection_name}' 已加载")
            except Exception as load_err:
                print(f"加载collection警告: {load_err}")

            # 构建查询表达式
            expr = f'filename == "{filename}"'
            print(f"根据文件名查询: {expr}")

            # 执行查询
            results = collection.query(
                expr=expr,
                limit=top_k,
                output_fields=["chunk_text", "filename", "file_id", "metadata", "created_at"]
            )

            # 格式化结果
            formatted_results = []
            for result in results:
                formatted_result = {
                    "id": result.get("id"),
                    "chunk_text": result.get("chunk_text"),
                    "filename": result.get("filename"),
                    "file_id": result.get("file_id"),
                    "metadata": json.loads(result.get("metadata", "{}")),
                    "created_at": result.get("created_at")
                }
                formatted_results.append(formatted_result)

            print(f"根据文件名 {filename} 找到 {len(formatted_results)} 个结果")
            return formatted_results

        except Exception as e:
            print(f"根据文件名检索失败: {e}")
            import traceback
            print(f"详细错误: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"根据文件名检索失败: {str(e)}")

    def delete_documents_by_filename(self, collection_name: str, filename: str) -> int:
        """根据文件名删除文档"""
        try:
            if not utility.has_collection(collection_name):
                raise HTTPException(status_code=404, detail=f"知识库 {collection_name} 不存在")

            collection = Collection(collection_name)

            # 删除前确保collection已加载
            try:
                collection.load()
            except Exception as load_err:
                print(f"加载collection警告: {load_err}")

            # 构建删除表达式
            expr = f'filename == "{filename}"'
            print(f"删除文件: {expr}")

            # 执行删除 - 参考milvus_kb_service.py，不调用flush
            collection.delete(expr)

            print(f"删除文件 {filename} 成功")
            return 1

        except Exception as e:
            print(f"删除失败: {e}")
            raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

    def list_knowledge_bases(self) -> List[Dict[str, Any]]:
        """列出所有知识库，包含display_name"""
        try:
            collection_ids = utility.list_collections()
            mappings = self.get_name_mapping()  # 获取所有映射

            result = []
            for collection_id in collection_ids:
                mapping = mappings.get(collection_id, {})
                result.append({
                    "collection_id": collection_id,
                    "display_name": mapping.get("display_name", collection_id),
                    "created_at": mapping.get("created_at", "")
                })

            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {str(e)}")

    def get_collection_stats(self, collection_id: str) -> Dict[str, Any]:
        """获取知识库统计信息"""
        try:
            if not utility.has_collection(collection_id):
                raise HTTPException(status_code=404, detail=f"知识库 {collection_id} 不存在")

            collection = Collection(collection_id)

            # 确保collection已加载
            try:
                collection.load()
            except Exception as load_err:
                print(f"加载collection警告: {load_err}")

            # 获取实体总数（chunk数）
            total_chunks = collection.num_entities

            # 查询所有文档，获取唯一文件名数量
            try:
                # 查询所有记录的filename字段
                results = collection.query(
                    expr="id > 0",
                    output_fields=["filename", "created_at"],
                    limit=16384  # Milvus默认最大限制
                )

                # 统计唯一文件名
                unique_filenames = set()
                latest_update = None

                for result in results:
                    filename = result.get("filename")
                    if filename:
                        unique_filenames.add(filename)

                    # 获取最新更新时间
                    created_at = result.get("created_at")
                    if created_at:
                        if latest_update is None or created_at > latest_update:
                            latest_update = created_at

                total_documents = len(unique_filenames)

            except Exception as query_err:
                print(f"查询统计信息失败: {query_err}")
                total_documents = 0
                latest_update = None

            # 获取显示名称
            mapping = self.get_name_mapping(collection_id)
            display_name = mapping.get("display_name", collection_id)

            return {
                "collection_id": collection_id,
                "collection_name": display_name,  # 前端显示的名称
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "last_updated": latest_update
            }

        except Exception as e:
            print(f"获取统计信息失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")

    def get_collection_documents(self, collection_id: str) -> List[Dict[str, Any]]:
        """获取知识库中的文档列表（按文件名去重）"""
        try:
            if not utility.has_collection(collection_id):
                raise HTTPException(status_code=404, detail=f"知识库 {collection_id} 不存在")

            collection = Collection(collection_id)

            # 确保collection已加载
            try:
                collection.load()
            except Exception as load_err:
                print(f"加载collection警告: {load_err}")

            # 查询所有记录
            try:
                results = collection.query(
                    expr="id > 0",
                    output_fields=["filename", "file_id", "metadata", "created_at"],
                    limit=16384
                )

                # 按文件名分组统计
                doc_stats = {}
                for result in results:
                    filename = result.get("filename")
                    if not filename:
                        continue

                    if filename not in doc_stats:
                        # 解析metadata获取额外信息
                        metadata_str = result.get("metadata", "{}")
                        try:
                            metadata = json.loads(metadata_str)
                        except:
                            metadata = {}

                        # 从metadata中提取实际的file_id（用于文件系统路径）
                        # metadata.file_id 是文件系统路径用的ID（如 file_20251016_d398cfa1）
                        # result.file_id 是Milvus中的UUID
                        actual_file_id = metadata.get("file_id", result.get("file_id"))

                        doc_stats[filename] = {
                            "filename": filename,
                            "file_id": actual_file_id,  # 使用metadata中的file_id
                            "chunks": 0,
                            "created_at": result.get("created_at"),
                            "metadata": metadata
                        }

                    doc_stats[filename]["chunks"] += 1

                # 转换为列表并排序（按创建时间倒序）
                documents = list(doc_stats.values())
                documents.sort(key=lambda x: x.get("created_at", ""), reverse=True)

                return documents

            except Exception as query_err:
                print(f"查询文档列表失败: {query_err}")
                return []

        except Exception as e:
            print(f"获取文档列表失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")

    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有知识库的汇总统计信息"""
        try:
            collections = utility.list_collections()

            total_collections = len(collections)
            total_documents = 0
            total_chunks = 0

            collection_details = []

            for collection_name in collections:
                try:
                    stats = self.get_collection_stats(collection_name)
                    total_documents += stats["total_documents"]
                    total_chunks += stats["total_chunks"]
                    collection_details.append(stats)
                except Exception as e:
                    print(f"获取 {collection_name} 统计信息失败: {e}")
                    continue

            return {
                "total_collections": total_collections,
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "collections": collection_details
            }

        except Exception as e:
            print(f"获取汇总统计失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取汇总统计失败: {str(e)}")

# FastAPI 应用
app = FastAPI(title="Milvus RAG Service", version="2.0.0")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有headers
)

# 初始化Milvus服务
milvus_service = MilvusRAGService()

@app.post("/knowledge_base/create")
async def create_knowledge_base(display_name: str):
    """创建知识库"""
    try:
        collection_id, success = milvus_service.create_knowledge_base(display_name)

        if success:
            return {
                "status": "success",
                "message": f"知识库 '{display_name}' 创建成功",
                "collection_id": collection_id,
                "display_name": display_name
            }
        else:
            return {
                "status": "error",
                "message": f"知识库创建失败"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DeleteKBByIdRequest(BaseModel):
    collection_id: str

@app.delete("/knowledge_base/delete")
async def delete_knowledge_base(request: DeleteKBByIdRequest):
    """删除知识库"""
    try:
        success = milvus_service.delete_knowledge_base(request.collection_id)
        if success:
            return {"status": "success", "message": f"知识库删除成功"}
        else:
            return {"status": "not_found", "message": f"知识库不存在"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge_base/list")
async def list_knowledge_bases():
    """列出所有知识库"""
    try:
        kbs = milvus_service.list_knowledge_bases()
        return {"status": "success", "knowledge_bases": kbs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload_json", response_model=UploadResponse)
async def upload_json_file(request: UploadKBRequest):
    """上传JSON文件到知识库"""
    try:
        # 解析JSON文件
        documents = milvus_service.parse_json_file(request.file_data)

        if not documents:
            raise HTTPException(status_code=400, detail="未找到有效的文档chunks")

        # 插入文档
        file_ids = milvus_service.insert_documents(request.collection_name, documents)

        # 获取文件名
        filename = request.file_data.get("filename", "unknown.txt")
        if filename.startswith("/"):
            filename = os.path.basename(filename)

        response = UploadResponse(
            filename=filename,
            file_id=documents[0].file_id if documents else str(uuid.uuid4()),
            status="success",
            message=f"文件上传成功，处理了{len(documents)}个chunks",
            chunks_count=len(documents)
        )

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search")
async def search_documents(request: SearchRequest):
    """根据问题搜索相似文档"""
    try:
        results = milvus_service.search_by_text(
            collection_name=request.collection_name,
            query_text=request.query_text,
            top_k=request.top_k,
            filter_expr=request.filter_expr
        )

        return {
            "status": "success",
            "query": request.query_text,
            "results": results,
            "total": len(results)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search_by_filename")
async def search_by_filename(request: SearchByFilenameRequest):
    """根据文件名检索知识库内信息"""
    try:
        results = milvus_service.search_by_filename(
            collection_name=request.collection_name,
            filename=request.filename,
            top_k=request.top_k
        )

        return {
            "status": "success",
            "filename": request.filename,
            "results": results,
            "total": len(results)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/delete")
async def delete_documents(request: DeleteRequest):
    """删除文档"""
    try:
        deleted_count = milvus_service.delete_documents_by_filename(
            collection_name=request.collection_name,
            filename=request.filename
        )

        return {
            "status": "success",
            "message": f"已删除文件 {request.filename}",
            "deleted_count": deleted_count
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "Milvus RAG Service"}

@app.get("/stats/collection/{collection_name}")
async def get_collection_stats(collection_name: str):
    """获取单个知识库的统计信息"""
    try:
        stats = milvus_service.get_collection_stats(collection_name)
        return {"status": "success", "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats/all")
async def get_all_stats():
    """获取所有知识库的汇总统计信息"""
    try:
        stats = milvus_service.get_all_stats()
        return {"status": "success", "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge_base/{collection_id}/documents")
async def get_knowledge_base_documents(collection_id: str):
    """获取知识库中的文档列表"""
    try:
        documents = milvus_service.get_collection_documents(collection_id)
        stats = milvus_service.get_collection_stats(collection_id)

        return {
            "status": "success",
            "collection_id": collection_id,
            "collection_name": stats["collection_name"],
            "total_documents": stats["total_documents"],
            "total_chunks": stats["total_chunks"],
            "last_updated": stats["last_updated"],
            "documents": documents
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/document/{file_id}/details")
async def get_document_details(file_id: str):
    """获取文档的详细信息，包括PDF、Markdown、chunks等"""
    try:
        # 定义基础路径
        base_upload_dir = UPLOAD_BASE_DIR
        base_extraction_dir = EXTRACTION_RESULTS_DIR

        # 查找文件
        extraction_dir = base_extraction_dir / file_id

        if not extraction_dir.exists():
            raise HTTPException(status_code=404, detail=f"文档 {file_id} 不存在")

        # 读取metadata.json
        metadata_path = extraction_dir / "metadata.json"
        chunks_path = extraction_dir / "chunks.json"

        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail="元数据文件不存在")

        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # 读取chunks
        chunks_data = []
        if chunks_path.exists():
            with open(chunks_path, 'r', encoding='utf-8') as f:
                full_chunks = json.load(f)
                # 只提取chunks数组部分
                if isinstance(full_chunks, dict) and 'chunks' in full_chunks:
                    chunks_data = full_chunks.get('chunks', [])
                else:
                    chunks_data = full_chunks

        # 读取markdown
        markdown_content = ""
        markdown_path = extraction_dir / f"{metadata['filename'].replace('.pdf', '.md')}"
        if markdown_path.exists():
            with open(markdown_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()

        # 查找PDF文件
        pdf_filename = f"{file_id}_{metadata['filename']}"
        pdf_path = None
        for root, dirs, files in os.walk(base_upload_dir):
            if pdf_filename in files:
                pdf_path = Path(root) / pdf_filename
                break

        return {
            "status": "success",
            "file_id": file_id,
            "filename": metadata['filename'],
            "metadata": metadata.get('metadata', {}),
            "extraction_time": metadata.get('extraction_time'),
            "markdown": markdown_content,
            "chunks": chunks_data,
            "pdf_url": f"/document/{file_id}/pdf" if pdf_path else None,
            "total_chunks": len(chunks_data),
            "total_pages": metadata.get('metadata', {}).get('total_pages', 0),
            "total_images": metadata.get('metadata', {}).get('total_images', 0)
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取文档详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取文档详情失败: {str(e)}")

@app.get("/document/{file_id}/pdf")
async def get_document_pdf(file_id: str):
    """直接返回PDF文件，Content-Disposition设置为inline以便浏览器内嵌显示"""
    try:
        base_upload_dir = UPLOAD_BASE_DIR
        base_extraction_dir = EXTRACTION_RESULTS_DIR

        # 读取metadata获取原始文件名
        extraction_dir = base_extraction_dir / file_id
        metadata_path = extraction_dir / "metadata.json"

        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail="文档不存在")

        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # 查找PDF文件
        pdf_filename = f"{file_id}_{metadata['filename']}"
        pdf_path = None
        for root, dirs, files in os.walk(base_upload_dir):
            if pdf_filename in files:
                pdf_path = Path(root) / pdf_filename
                break

        if not pdf_path or not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF文件不存在")

        # 返回PDF，设置为inline模式以便浏览器内嵌显示
        from fastapi.responses import Response
        from urllib.parse import quote
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()

        # URL encode the filename for proper handling of Chinese characters
        encoded_filename = quote(metadata['filename'])

        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}",
                "Cache-Control": "public, max-age=3600"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取PDF文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取PDF文件失败: {str(e)}")

@app.get("/document/{file_id}/images/{image_name}")
async def get_document_image(file_id: str, image_name: str):
    """获取文档提取的图片"""
    try:
        base_extraction_dir = EXTRACTION_RESULTS_DIR

        # 图片路径
        image_path = base_extraction_dir / file_id / "images" / image_name

        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")

        # 根据文件扩展名设置media_type
        ext = image_path.suffix.lower()
        media_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        media_type = media_types.get(ext, 'image/png')

        return FileResponse(
            path=str(image_path),
            media_type=media_type
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取图片失败: {str(e)}")

if __name__ == "__main__":
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8000"))

    print("\n" + "="*60)
    print("Starting Milvus RAG Service")
    print("="*60)
    print(f"Server: http://{host}:{port}")
    print(f"Docs: http://{host}:{port}/docs")
    print("="*60 + "\n")

    uvicorn.run(app, host=host, port=port)
