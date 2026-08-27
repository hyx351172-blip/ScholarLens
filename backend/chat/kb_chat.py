"""
RAG对话模块 - FastAPI接口版本
支持向量召回、可选重排序、流式/非流式问答
"""
import asyncio
import json
import time
import uuid
import os
import sys
from typing import List, Dict, Any, Optional, AsyncIterable
from datetime import datetime

import uvicorn
import requests
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from dotenv import load_dotenv
from pathlib import Path

# 加载仓库根目录 .env 文件
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=PROJECT_ROOT / '.env', override=True)

# Avoid GBK UnicodeEncodeError on Windows when status symbols are printed to
# redirected logs. Logging must never interrupt a streaming chat response.
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

# 服务配置
SERVICE_PORT = int(os.getenv("CHAT_SERVICE_PORT", "8501"))
SERVICE_HOST = os.getenv("CHAT_SERVICE_HOST", "0.0.0.0")

# ============ 数据模型 ============

class Message(BaseModel):
    """对话消息"""
    role: str = Field(..., description="角色: user/assistant/system")
    content: str = Field(..., description="消息内容")

class LLMConfig(BaseModel):
    """大模型配置"""
    api_url: str = Field(..., description="LLM API地址")
    api_key: str = Field(..., description="LLM API密钥")
    model_name: str = Field(..., description="模型名称")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="采样温度")
    max_tokens: int = Field(2000, ge=1, description="最大生成token数")

class RerankerConfig(BaseModel):
    """重排序配置"""
    api_url: str = Field(..., description="Reranker API地址")
    api_key: str = Field(..., description="Reranker API密钥")
    model_name: str = Field(..., description="Reranker模型名称")
    top_n: int = Field(5, ge=1, description="重排序后保留的文档数量")

class SourceDocument(BaseModel):
    """来源文档"""
    chunk_text: str
    filename: str
    score: float  # 主分数（如果有重排序则为重排序分数，否则为召回分数）
    retrieval_score: Optional[float] = None  # 原始召回分数
    rerank_score: Optional[float] = None  # 重排序分数
    metadata: Dict[str, Any] = {}

class ChatRequest(BaseModel):
    """对话请求"""
    query: str = Field(..., description="用户问题")
    collection_name: str = Field(..., description="Milvus集合名称")
    llm_config: LLMConfig = Field(..., description="大模型配置")

    # 召回配置
    top_k: int = Field(10, ge=1, le=50, description="召回文档数量")
    score_threshold: float = Field(0.1, ge=0.0, le=1.0, description="相似度阈值")

    # 重排序配置
    use_reranker: bool = Field(False, description="是否使用重排序")
    reranker_config: Optional[RerankerConfig] = Field(None, description="重排序配置")

    # 对话配置
    history: List[Message] = Field(default=[], description="历史对话")
    stream: bool = Field(True, description="是否流式输出")
    prompt_template: Optional[str] = Field(None, description="自定义prompt模板")
    return_source: bool = Field(True, description="是否返回来源文档")

    # Milvus服务地址
    milvus_api_url: str = Field("http://localhost:8000", description="Milvus API地址")

class ChatResponse(BaseModel):
    """对话响应（非流式）"""
    success: bool
    message: str
    answer: str
    sources: Optional[List[SourceDocument]] = None
    metadata: Dict[str, Any] = {}

# ============ 对话服务 ============

class ChatService:
    """RAG对话服务"""

    def __init__(self):
        self.default_prompt_template = """你是一个专业的AI助手。请根据以下检索到的相关信息回答用户的问题。

相关信息：
{context}

用户问题：{query}

请基于以上信息给出准确、详细的回答。如果信息不足以回答问题，请如实说明。"""

    async def retrieve_documents(
        self,
        query: str,
        collection_name: str,
        milvus_api_url: str,
        top_k: int = 10,
        score_threshold: float = 0.1
    ) -> List[Dict[str, Any]]:
        """
        从Milvus召回相关文档

        Returns:
            List of documents with format:
            {
                "id": int,
                "score": float,
                "chunk_text": str,
                "filename": str,
                "file_id": str,
                "metadata": dict,
                "created_at": str
            }
        """
        try:
            url = f"{milvus_api_url}/search"
            payload = {
                "collection_name": collection_name,
                "query_text": query,
                "top_k": top_k
            }

            print(f"正在从Milvus召回文档: {url}")
            response = requests.post(url, json=payload, timeout=30)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Milvus召回失败: {response.text}"
                )

            result = response.json()

            if result.get("status") != "success":
                raise HTTPException(
                    status_code=500,
                    detail=f"Milvus召回失败: {result}"
                )

            documents = result.get("results", [])

            # 过滤低于阈值的文档
            filtered_docs = [
                doc for doc in documents
                if doc["score"] >= score_threshold
            ]

            print(f"✓ 召回 {len(documents)} 个文档，过滤后保留 {len(filtered_docs)} 个")
            return filtered_docs

        except requests.exceptions.RequestException as e:
            raise HTTPException(
                status_code=500,
                detail=f"调用Milvus API失败: {str(e)}"
            )

    async def rerank_documents(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        reranker_config: RerankerConfig
    ) -> List[Dict[str, Any]]:
        """
        使用重排序模型对文档进行重排序
        自动识别并适配不同的重排序服务：
        - BGE (BAAI): bge-reranker-*
        - 千问/阿里云: gte-rerank-*
        - Jina AI: jina-reranker-*
        """
        try:
            import httpx

            rerank_start = time.time()
            model_name = reranker_config.model_name.lower()
            print(f"正在使用重排序模型: {reranker_config.model_name}")

            # 准备文档文本列表
            doc_texts = [doc["chunk_text"] for doc in documents]

            # 根据模型名称自动识别服务类型
            if "jina" in model_name:
                # ============ Jina AI 重排序 ============
                rerank_payload = {
                    "model": reranker_config.model_name,
                    "query": query,
                    "documents": doc_texts,
                    "top_n": reranker_config.top_n
                }
                headers = {
                    "Authorization": f"Bearer {reranker_config.api_key}",
                    "Content-Type": "application/json"
                }
                rerank_url = f"{reranker_config.api_url.rstrip('/')}/rerank"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        rerank_url,
                        json=rerank_payload,
                        headers=headers
                    )
                    response.raise_for_status()
                    result = response.json()

                # 解析 Jina 格式: {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
                reranked_docs = []
                for item in result.get("results", []):
                    idx = item["index"]
                    doc = documents[idx].copy()
                    doc["retrieval_score"] = doc["score"]
                    doc["rerank_score"] = item["relevance_score"]
                    doc["score"] = doc["rerank_score"]
                    reranked_docs.append(doc)

            elif "gte-rerank" in model_name or "dashscope" in reranker_config.api_url:
                # ============ 千问/阿里云 重排序 ============
                rerank_payload = {
                    "model": reranker_config.model_name,
                    "input": {
                        "query": query,
                        "documents": doc_texts
                    },
                    "parameters": {
                        "return_documents": False,
                        "top_n": reranker_config.top_n
                    }
                }
                headers = {
                    "Authorization": f"Bearer {reranker_config.api_key}",
                    "Content-Type": "application/json"
                }
                # 移除 /compatible-mode/v1 后缀
                base_url = reranker_config.api_url.replace("/compatible-mode/v1", "").rstrip('/')
                rerank_url = f"{base_url}/services/embeddings/text-embedding/text-rerank"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        rerank_url,
                        json=rerank_payload,
                        headers=headers
                    )
                    response.raise_for_status()
                    result = response.json()

                # 解析千问格式: {"output": {"results": [{"index": 0, "relevance_score": 0.95}, ...]}}
                if "output" in result and "results" in result["output"]:
                    index_to_score = {
                        item["index"]: item["relevance_score"]
                        for item in result["output"]["results"]
                    }

                    reranked_docs = []
                    for idx in sorted(index_to_score.keys(),
                                    key=lambda x: index_to_score[x],
                                    reverse=True)[:reranker_config.top_n]:
                        doc = documents[idx].copy()
                        doc["retrieval_score"] = doc["score"]
                        doc["rerank_score"] = index_to_score[idx]
                        doc["score"] = doc["rerank_score"]
                        reranked_docs.append(doc)
                else:
                    raise ValueError(f"千问重排序响应格式错误: {result}")

            elif "bge-reranker" in model_name:
                # ============ BGE/BAAI 重排序 ============
                # BGE 模型可能通过 OpenAI 兼容接口或自定义接口调用

                # 方式1: 如果使用 OpenAI 兼容接口（推荐）
                if "openai" in reranker_config.api_url or "v1" in reranker_config.api_url:
                    from openai import AsyncOpenAI

                    client = AsyncOpenAI(
                        api_key=reranker_config.api_key,
                        base_url=reranker_config.api_url
                    )

                    # 构造重排序请求（使用 embeddings 接口的扩展）
                    response = await client.post(
                        "/rerank",
                        json={
                            "model": reranker_config.model_name,
                            "query": query,
                            "documents": doc_texts,
                            "top_n": reranker_config.top_n
                        }
                    )
                    result = response.json()

                    # 解析标准格式
                    reranked_docs = []
                    for item in result.get("results", []):
                        idx = item["index"]
                        doc = documents[idx].copy()
                        doc["retrieval_score"] = doc["score"]
                        doc["rerank_score"] = item.get("score", item.get("relevance_score"))
                        doc["score"] = doc["rerank_score"]
                        reranked_docs.append(doc)

                # 方式2: 使用原生 BGE 接口
                else:
                    rerank_payload = {
                        "query": query,
                        "passages": doc_texts,
                        "top_n": reranker_config.top_n
                    }
                    headers = {
                        "Authorization": f"Bearer {reranker_config.api_key}",
                        "Content-Type": "application/json"
                    }
                    rerank_url = f"{reranker_config.api_url.rstrip('/')}/rerank"

                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            rerank_url,
                            json=rerank_payload,
                            headers=headers
                        )
                        response.raise_for_status()
                        result = response.json()

                    # 解析 BGE 格式: {"scores": [0.95, 0.89, ...], "indices": [0, 5, ...]}
                    if "scores" in result and "indices" in result:
                        reranked_docs = []
                        for idx, score in zip(result["indices"], result["scores"]):
                            doc = documents[idx].copy()
                            doc["retrieval_score"] = doc["score"]
                            doc["rerank_score"] = score
                            doc["score"] = doc["rerank_score"]
                            reranked_docs.append(doc)
                    else:
                        raise ValueError(f"BGE重排序响应格式错误: {result}")

            else:
                # ============ 通用格式（尝试自动适配） ============
                print(f"⚠️ 未识别的模型类型，尝试通用格式")

                rerank_payload = {
                    "model": reranker_config.model_name,
                    "query": query,
                    "documents": doc_texts,
                    "top_n": reranker_config.top_n
                }
                headers = {
                    "Authorization": f"Bearer {reranker_config.api_key}",
                    "Content-Type": "application/json"
                }
                rerank_url = f"{reranker_config.api_url.rstrip('/')}/rerank"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        rerank_url,
                        json=rerank_payload,
                        headers=headers
                    )
                    response.raise_for_status()
                    result = response.json()

                # 尝试解析常见格式
                reranked_docs = []
                if "results" in result:
                    # Jina/标准格式
                    for item in result["results"]:
                        idx = item["index"]
                        doc = documents[idx].copy()
                        doc["retrieval_score"] = doc["score"]
                        doc["rerank_score"] = item.get("relevance_score", item.get("score"))
                        doc["score"] = doc["rerank_score"]
                        reranked_docs.append(doc)
                else:
                    raise ValueError(f"无法解析重排序响应: {result}")

            rerank_time = time.time() - rerank_start
            print(f"✓ 重排序完成，保留 {len(reranked_docs)} 个文档 (耗时: {rerank_time:.2f}秒)")

            return reranked_docs

        except Exception as e:
            import traceback
            print(f"⚠️ 重排序失败: {str(e)}")
            print(f"⚠️ 错误详情:\n{traceback.format_exc()}")
            print(f"⚠️ 降级使用原始召回排序")

            # 重排序失败时，保留原始排序的前 top_n 个文档
            fallback_docs = []
            for doc in documents[:reranker_config.top_n]:
                doc_copy = doc.copy()
                doc_copy["retrieval_score"] = doc["score"]
                doc_copy["rerank_score"] = None
                fallback_docs.append(doc_copy)
            return fallback_docs

    def format_context(self, documents: List[Dict[str, Any]]) -> str:
        """
        格式化文档为上下文字符串
        """
        context_parts = []

        for i, doc in enumerate(documents):
            filename = doc.get("filename", "未知文件")
            text = doc.get("chunk_text", "")
            score = doc.get("score", 0.0)

            # 提取metadata中的页码信息（如果有）
            metadata = doc.get("metadata", {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}

            page_info = ""
            if "page_start" in metadata:
                page_start = metadata["page_start"]
                page_end = metadata.get("page_end", page_start)
                if page_start == page_end:
                    page_info = f"(第{page_start}页)"
                else:
                    page_info = f"(第{page_start}-{page_end}页)"

            context_parts.append(
                f"[文档片段 {i+1}] 来源: {filename}{page_info} | 相关度: {score:.3f}\n{text}"
            )

        return "\n\n".join(context_parts)

    async def call_llm_stream(
        self,
        messages: List[Dict[str, str]],
        llm_config: LLMConfig
    ) -> AsyncIterable[str]:
        """
        流式调用大模型
        """
        try:
            client = AsyncOpenAI(
                api_key=llm_config.api_key,
                base_url=llm_config.api_url
            )

            stream = await client.chat.completions.create(
                model=llm_config.model_name,
                messages=messages,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens,
                stream=True
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"调用LLM失败: {str(e)}"
            )

    async def call_llm_non_stream(
        self,
        messages: List[Dict[str, str]],
        llm_config: LLMConfig
    ) -> str:
        """
        非流式调用大模型
        """
        try:
            client = AsyncOpenAI(
                api_key=llm_config.api_key,
                base_url=llm_config.api_url
            )

            response = await client.chat.completions.create(
                model=llm_config.model_name,
                messages=messages,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens,
                stream=False
            )

            return response.choices[0].message.content

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"调用LLM失败: {str(e)}"
            )

    async def chat_stream(
        self,
        request: ChatRequest
    ) -> AsyncIterable[str]:
        """
        流式对话处理
        """
        try:
            start_time = time.time()

            # 1. 召回文档

            retrieve_start = time.time()
            documents = await self.retrieve_documents(
                query=request.query,
                collection_name=request.collection_name,
                milvus_api_url=request.milvus_api_url,
                top_k=request.top_k,
                score_threshold=request.score_threshold
            )
            retrieve_time = time.time() - retrieve_start

            if not documents:
                # 没有找到相关文档，直接用LLM回答
                print("⚠️ 未找到相关文档，使用LLM直接回答")
                messages = []

                # 添加历史对话
                for msg in request.history:
                    messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })

                # 添加当前问题
                messages.append({
                    "role": "user",
                    "content": request.query
                })

                # 流式返回
                async for token in self.call_llm_stream(messages, request.llm_config):
                    yield json.dumps({
                        "type": "content",
                        "data": token
                    }, ensure_ascii=False) + "\n"

                # 返回元数据
                yield json.dumps({
                    "type": "metadata",
                    "data": {
                        "retrieve_time": retrieve_time,
                        "total_time": time.time() - start_time,
                        "documents_count": 0
                    }
                }, ensure_ascii=False) + "\n"
                return

            # 2. 重排序（可选）
            if request.use_reranker and request.reranker_config:
                rerank_start = time.time()
                documents = await self.rerank_documents(
                    query=request.query,
                    documents=documents,
                    reranker_config=request.reranker_config
                )
                rerank_time = time.time() - rerank_start
                print(f"✓ 重排序耗时: {rerank_time:.2f}秒")
            else:
                rerank_time = 0

            # 3. 构建上下文
            context = self.format_context(documents)

            # 4. 构建prompt
            prompt_template = request.prompt_template or self.default_prompt_template
            user_message = prompt_template.format(
                context=context,
                query=request.query
            )

            # 5. 构建消息列表
            messages = []

            # 添加历史对话
            for msg in request.history:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

            # 添加当前问题
            messages.append({
                "role": "user",
                "content": user_message
            })

            # 6. 调用LLM（流式）
            llm_start = time.time()
            async for token in self.call_llm_stream(messages, request.llm_config):
                yield json.dumps({
                    "type": "content",
                    "data": token
                }, ensure_ascii=False) + "\n"
            llm_time = time.time() - llm_start

            # 7. 发送来源文档
            if request.return_source and documents:
                sources = []
                for doc in documents:
                    sources.append({
                        "chunk_text": doc["chunk_text"],
                        "filename": doc["filename"],
                        "score": doc["score"],
                        "retrieval_score": doc.get("retrieval_score"),
                        "rerank_score": doc.get("rerank_score"),
                        "metadata": doc.get("metadata", {})
                    })

                yield json.dumps({
                    "type": "sources",
                    "data": sources
                }, ensure_ascii=False) + "\n"

            # 8. 返回元数据
            total_time = time.time() - start_time
            yield json.dumps({
                "type": "metadata",
                "data": {
                    "retrieve_time": retrieve_time,
                    "rerank_time": rerank_time,
                    "llm_time": llm_time,
                    "total_time": total_time,
                    "documents_count": len(documents)
                }
            }, ensure_ascii=False) + "\n"

            print(f"\n{'='*60}")
            print(f"✓ RAG对话完成")
            print(f"  - 召回耗时: {retrieve_time:.2f}秒")
            print(f"  - 重排序耗时: {rerank_time:.2f}秒")
            print(f"  - LLM耗时: {llm_time:.2f}秒")
            print(f"  - 总耗时: {total_time:.2f}秒")
            print(f"  - 文档数量: {len(documents)}")
            print(f"{'='*60}\n")

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"❌ RAG对话失败: {error_trace}")
            yield json.dumps({
                "type": "error",
                "data": {
                    "error": str(e),
                    "traceback": error_trace
                }
            }, ensure_ascii=False) + "\n"

    async def chat_non_stream(
        self,
        request: ChatRequest
    ) -> ChatResponse:
        """
        非流式对话处理
        """
        start_time = time.time()

        try:
            # 1. 召回文档
            print(f"\n{'='*60}")
            print(f"开始RAG对话流程（非流式）")
            print(f"{'='*60}\n")

            retrieve_start = time.time()
            documents = await self.retrieve_documents(
                query=request.query,
                collection_name=request.collection_name,
                milvus_api_url=request.milvus_api_url,
                top_k=request.top_k,
                score_threshold=request.score_threshold
            )
            retrieve_time = time.time() - retrieve_start

            if not documents:
                # 没有找到相关文档，直接用LLM回答
                print("⚠️ 未找到相关文档，使用LLM直接回答")
                messages = []

                for msg in request.history:
                    messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })

                messages.append({
                    "role": "user",
                    "content": request.query
                })

                answer = await self.call_llm_non_stream(messages, request.llm_config)

                return ChatResponse(
                    success=True,
                    message="对话完成（未找到相关文档）",
                    answer=answer,
                    sources=None,
                    metadata={
                        "retrieve_time": retrieve_time,
                        "total_time": time.time() - start_time,
                        "documents_count": 0
                    }
                )

            # 2. 重排序（可选）
            if request.use_reranker and request.reranker_config:
                rerank_start = time.time()
                documents = await self.rerank_documents(
                    query=request.query,
                    documents=documents,
                    reranker_config=request.reranker_config
                )
                rerank_time = time.time() - rerank_start
            else:
                rerank_time = 0

            # 3. 构建上下文
            context = self.format_context(documents)

            # 4. 构建prompt
            prompt_template = request.prompt_template or self.default_prompt_template
            user_message = prompt_template.format(
                context=context,
                query=request.query
            )

            # 5. 构建消息列表
            messages = []
            for msg in request.history:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            messages.append({
                "role": "user",
                "content": user_message
            })

            # 6. 调用LLM（非流式）
            llm_start = time.time()
            answer = await self.call_llm_non_stream(messages, request.llm_config)
            llm_time = time.time() - llm_start

            # 7. 构建来源文档
            sources = None
            if request.return_source:
                sources = []
                for doc in documents:
                    source_doc = SourceDocument(
                        chunk_text=doc["chunk_text"],
                        filename=doc["filename"],
                        score=doc["score"],  # 主分数
                        retrieval_score=doc.get("retrieval_score"),  # 原始召回分数
                        rerank_score=doc.get("rerank_score"),  # 重排序分数
                        metadata=doc.get("metadata", {})
                    )
                    sources.append(source_doc)

            # 8. 返回结果
            total_time = time.time() - start_time

            print(f"\n{'='*60}")
            print(f"✓ RAG对话完成")
            print(f"  - 召回耗时: {retrieve_time:.2f}秒")
            print(f"  - 重排序耗时: {rerank_time:.2f}秒")
            print(f"  - LLM耗时: {llm_time:.2f}秒")
            print(f"  - 总耗时: {total_time:.2f}秒")
            print(f"  - 文档数量: {len(documents)}")
            print(f"{'='*60}\n")

            return ChatResponse(
                success=True,
                message="对话完成",
                answer=answer,
                sources=sources,
                metadata={
                    "retrieve_time": retrieve_time,
                    "rerank_time": rerank_time,
                    "llm_time": llm_time,
                    "total_time": total_time,
                    "documents_count": len(documents)
                }
            )

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"❌ RAG对话失败: {error_trace}")
            raise HTTPException(
                status_code=500,
                detail=f"对话失败: {str(e)}"
            )

# ============ FastAPI应用 ============

app = FastAPI(
    title="RAG对话服务API",
    description="支持向量召回、重排序、流式/非流式问答",
    version="1.0.0"
)

# 添加CORS支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = ChatService()

@app.get("/")
async def root():
    """健康检查"""
    return {
        "status": "running",
        "service": "RAG Chat API",
        "version": "1.0.0",
        "features": ["vector_retrieval", "reranking", "streaming", "non_streaming"]
    }

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    RAG对话接口

    支持流式和非流式两种模式：

    **流式模式** (stream=True):
    返回格式为 NDJSON (换行分隔的JSON)，每行是一个事件：
    - {"type": "content", "data": "..."} - 内容片段
    - {"type": "sources", "data": [...]} - 来源文档（可选）
    - {"type": "metadata", "data": {...}} - 元数据
    - {"type": "error", "data": {...}} - 错误信息

    **非流式模式** (stream=False):
    返回完整的JSON响应
    """
    try:
        if request.stream:
            # 流式返回
            return StreamingResponse(
                service.chat_stream(request),
                media_type="application/x-ndjson"
            )
        else:
            # 非流式返回
            return await service.chat_non_stream(request)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"对话失败: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """服务健康检查"""
    return {
        "status": "healthy",
        "service": "rag-chat",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/config/default")
async def get_default_config():
    """获取默认的LLM配置"""
    return {
        "status": "success",
        "config": {
            "llm": {
                "api_url": os.getenv("MODEL_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                "api_key": os.getenv("API_KEY", ""),
                "model_name": os.getenv("MODEL_NAME", "qwen-plus"),
                "temperature": 0.7,
                "max_tokens": 2000
            },
            "retrieval": {
                "top_k": 10,
                "score_threshold": 0.1
            },
            "available_models": [
                {"name": "qwen-plus", "display": "通义千问 Plus", "provider": "阿里云"},
                {"name": "qwen-max", "display": "通义千问 Max", "provider": "阿里云"},
                {"name": "qwen-turbo", "display": "通义千问 Turbo", "provider": "阿里云"},
                {"name": "qwen3-vl-plus", "display": "通义千问 3 VL Plus", "provider": "阿里云"}
            ]
        }
    }

# ============ 启动服务 ============

if __name__ == "__main__":
    import os

    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8501"))

    print("\n" + "="*60)
    print("启动RAG对话服务")
    print("="*60)
    print(f"服务地址: http://{host}:{port}")
    print(f"API文档: http://{host}:{port}/docs")
    print("="*60 + "\n")

    uvicorn.run(
        app,
        host=SERVICE_HOST,
        port=SERVICE_PORT,
        log_level="info"
    )
