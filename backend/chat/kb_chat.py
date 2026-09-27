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
from typing import List, Dict, Any, Optional, AsyncIterable, Literal
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

try:
    from backend.chat.answer_guard import guard_answer, GROUNDING_POLICY, INSUFFICIENT_EVIDENCE
    from backend.chat.claim_bound_answer import build_catalog, build_messages
    from backend.chat.claim_bound_output_v2 import (
        render_claim_answer, empty_binding, CLAIM_EVIDENCE_ERROR, CLAIM_GENERATION_ERROR,
    )
    from backend.chat import evidence_units
    from backend.chat.document_scope import DocumentScope, resolve_document_scope
    from backend.chat.multi_query_retrieval import (
        RetrievalExecution,
        RetrievalPlan,
        create_query_plan,
        execute_retrieval_plan,
        resolve_target_filename,
        single_query_plan,
    )
    from backend.chat.section_intent_retrieval import rerank_section_intent
except ModuleNotFoundError:  # Direct execution from backend/chat.
    from answer_guard import guard_answer, GROUNDING_POLICY, INSUFFICIENT_EVIDENCE
    from claim_bound_answer import build_catalog, build_messages
    from claim_bound_output_v2 import (
        render_claim_answer, empty_binding, CLAIM_EVIDENCE_ERROR, CLAIM_GENERATION_ERROR,
    )
    import evidence_units
    from document_scope import DocumentScope, resolve_document_scope
    from multi_query_retrieval import (
        RetrievalExecution,
        RetrievalPlan,
        create_query_plan,
        execute_retrieval_plan,
        resolve_target_filename,
        single_query_plan,
    )
    from section_intent_retrieval import rerank_section_intent

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

class MultiQueryConfig(BaseModel):
    """跨论文多查询召回配置。"""
    planner_timeout_seconds: float = Field(12.0, ge=0.1, le=60.0)
    max_subqueries: int = Field(3, ge=2, le=3)
    candidate_k_per_query: int = Field(10, ge=1, le=50)
    rrf_k: int = Field(60, ge=1)
    original_reserve: int = Field(4, ge=0, le=50)
    per_target_reserve: int = Field(2, ge=1, le=25)

class SourceDocument(BaseModel):
    """来源文档"""
    source_id: Optional[str] = None
    file_id: Optional[str] = None
    chunk_text: str
    filename: str
    score: float  # 主分数（如果有重排序则为重排序分数，否则为召回分数）
    retrieval_score: Optional[float] = None  # 原始召回分数
    rerank_score: Optional[float] = None  # 重排序分数
    query_rrf_score: Optional[float] = None
    matched_query_ids: Optional[List[str]] = None
    query_ranks: Optional[Dict[str, int]] = None
    section_intent: Optional[str] = None
    section_boost: Optional[float] = None
    metadata: Dict[str, Any] = {}

class ChatRequest(BaseModel):
    """对话请求"""
    query: str = Field(..., description="用户问题")
    collection_name: str = Field(..., description="Milvus集合名称")
    llm_config: LLMConfig = Field(..., description="大模型配置")

    # 召回配置
    top_k: int = Field(10, ge=1, le=50, description="召回文档数量")
    score_threshold: float = Field(0.1, ge=0.0, le=1.0, description="相似度阈值")

    # 跨论文多查询召回（默认关闭，保持旧接口行为）
    use_multi_query: bool = Field(False, description="是否启用自动问题拆分和多路召回")
    multi_query_config: MultiQueryConfig = Field(default_factory=MultiQueryConfig)

    # 重排序配置
    use_reranker: bool = Field(False, description="是否使用重排序")
    reranker_config: Optional[RerankerConfig] = Field(None, description="重排序配置")

    # 对话配置
    history: List[Message] = Field(default=[], description="历史对话")
    stream: bool = Field(True, description="是否流式输出")
    prompt_template: Optional[str] = Field(None, description="自定义prompt模板")
    return_source: bool = Field(True, description="是否返回来源文档")
    answer_mode: Literal["legacy", "claim_bound"] = Field(
        "legacy", description="回答格式；claim_bound 为待真实模型验证的逐条结论引用模式")
    claim_evidence_mode: Literal["fixed_v1", "sentence_v2"] = Field(
        "fixed_v1", description="仅 claim_bound 使用；sentence_v2 为待真实模型复测的完整句证据模式")

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
        self.default_prompt_template = """你是一个严谨的科研论文助手。请仅根据以下检索证据回答用户问题。

检索证据：
{context}

用户问题：{query}

回答要求：
1. 每个事实性陈述后必须在同一句或同一条项目末尾紧跟来源编号，例如 [S1] 或 [S1][S2]；不要用段末的一次引用覆盖前面的多个句子。
2. 只能使用上面实际存在的 [S1]、[S2] 等编号，不得编造来源。
3. 段首概述、带事实的过渡句、每个列表项和总结中的事实同样必须引用；只有不包含事实的纯标题可以不引用。
4. 回答第一行就必须包含有效来源编号；不要先写无引用的概述，也不要单独写“具体如下：”或“Specifically:”等引导句。
5. 每条列表项尽量只写一个事实句；如含多个事实句，则每句分别引用。
6. 比较类问题必须分别回答每个比较对象，并引用支持各对象的证据。
7. 不要使用检索证据之外的知识补全；证据不足时明确说明缺少什么。
8. 回答保持紧凑，删除没有证据或仅重复后文的引言，不要单独列出未在正文中使用的参考文献列表。"""

    async def retrieve_documents(
        self,
        query: str,
        collection_name: str,
        milvus_api_url: str,
        top_k: int = 10,
        score_threshold: float = 0.1,
        filter_expr: Optional[str] = None,
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
            # Broad cross-language questions can rank the correct scientific
            # section below the final Top-K. Pull a bounded candidate pool,
            # apply deterministic section-intent scoring, then truncate.
            candidate_top_k = min(50, max(top_k, top_k * 5))
            payload = {
                "collection_name": collection_name,
                "query_text": query,
                "top_k": candidate_top_k,
                "filter_expr": filter_expr,
            }

            print(f"正在从Milvus召回文档: {url}")
            response = await asyncio.to_thread(
                requests.post,
                url,
                json=payload,
                timeout=30,
            )

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
            ranked_docs = rerank_section_intent(query, filtered_docs)
            section_matches = [
                doc for doc in ranked_docs
                if doc.get("section_intent") and float(doc.get("section_boost", 0.0)) > 0
            ]
            if section_matches:
                ranked_docs = section_matches
            ranked_docs = ranked_docs[:top_k]

            print(
                f"✓ 候选 {len(documents)} 个，阈值后 {len(filtered_docs)} 个，"
                f"章节排序后返回 {len(ranked_docs)} 个"
            )
            return ranked_docs

        except requests.exceptions.RequestException as e:
            raise HTTPException(
                status_code=500,
                detail=f"调用Milvus API失败: {str(e)}"
            )

    async def list_collection_documents(
        self,
        collection_name: str,
        milvus_api_url: str,
    ) -> List[Dict[str, Any]]:
        """Read the current corpus catalog used for safe target resolution."""

        try:
            url = (
                f"{milvus_api_url.rstrip('/')}/knowledge_base/"
                f"{collection_name}/documents"
            )
            response = await asyncio.to_thread(
                requests.get,
                url,
                timeout=30,
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"知识库文档目录读取失败: {response.text}",
                )
            result = response.json()
            if result.get("status") != "success":
                raise HTTPException(
                    status_code=500,
                    detail=f"知识库文档目录读取失败: {result}",
                )
            documents = result.get("documents", [])
            if not isinstance(documents, list):
                raise HTTPException(status_code=500, detail="知识库文档目录格式错误")
            if any(not isinstance(item, dict)
                   or not isinstance(item.get('filename'), str)
                   or not item['filename'].strip()
                   or (item.get('file_id') is not None and not isinstance(item['file_id'], str))
                   for item in documents):
                raise HTTPException(status_code=500, detail="知识库文档目录包含无效记录")
            return [dict(item, filename=item['filename'].strip()) for item in documents]
        except requests.exceptions.RequestException as e:
            raise HTTPException(
                status_code=500,
                detail=f"调用Milvus文档目录API失败: {str(e)}",
            )

    async def list_collection_filenames(
        self, collection_name: str, milvus_api_url: str,
    ) -> List[str]:
        """Compatibility helper for offline tools; request scope also needs IDs."""
        documents = await self.list_collection_documents(collection_name, milvus_api_url)
        return sorted({str(item['filename']).strip() for item in documents})

    async def plan_retrieval(
        self,
        query: str,
        llm_config: LLMConfig,
        multi_query_config: MultiQueryConfig,
    ) -> RetrievalPlan:
        """Generate a validated comparison plan with deterministic settings."""

        planner_llm_config = LLMConfig(
            api_url=llm_config.api_url,
            api_key=llm_config.api_key,
            model_name=llm_config.model_name,
            temperature=0.0,
            max_tokens=min(llm_config.max_tokens, 600),
        )

        async def generate(messages: List[Dict[str, str]]) -> str:
            return await self.call_llm_non_stream(messages, planner_llm_config)

        return await create_query_plan(
            query,
            generate,
            timeout_seconds=multi_query_config.planner_timeout_seconds,
            max_subqueries=multi_query_config.max_subqueries,
        )

    async def retrieve_for_request(
        self,
        request: ChatRequest,
    ) -> RetrievalExecution:
        """Keep the user's catalog-grounded scope outside planner control."""

        try:
            catalog = await self.list_collection_documents(
                request.collection_name, request.milvus_api_url,
            )
        except Exception as exc:
            # A catalog outage must not silently remove a document restriction.
            raise HTTPException(status_code=503, detail="无法读取论文目录，已停止检索；请检查知识库服务后重试。") from exc
        scope = resolve_document_scope(request.query, catalog)
        scope_trace = dict(scope.to_dict(), dropped_candidates=0, skipped_queries=[])
        if scope.status in {"ambiguous", "unresolved"}:
            return RetrievalExecution(documents=[], trace={
                "mode": "scope_blocked", "fallback_reason": scope.reason,
                "queries": [], "final_count": 0, "document_scope": scope_trace,
                "target_resolution_status": "not_applicable", "target_resolutions": {},
            })

        planner_started = time.perf_counter()
        if scope.status == "resolved" and len(scope.documents) == 1:
            plan = single_query_plan(planner_source="document_scope")
        elif request.use_multi_query:
            plan = await self.plan_retrieval(
                request.query,
                request.llm_config,
                request.multi_query_config,
            )
        else:
            plan = single_query_plan(planner_source="disabled")
        planner_latency = time.perf_counter() - planner_started

        candidate_k = (
            max(request.top_k, request.multi_query_config.candidate_k_per_query)
            if plan.is_multi_query
            else request.top_k
        )

        query_scopes: Dict[str, DocumentScope] = {}
        blocked_queries: set[str] = set()
        target_resolutions: Dict[str, Dict[str, Any]] = {}
        target_resolution_status = "not_applicable"
        if plan.is_multi_query:
            permitted = scope.documents if scope.status == "resolved" else tuple(catalog)
            filenames = [item['filename'] for item in permitted]
            for subquery in plan.subqueries:
                resolution = resolve_target_filename(subquery.target, filenames)
                target_resolutions[subquery.query_id] = resolution.to_dict()
                if resolution.filename:
                    matched = tuple(d for d in permitted if d['filename'] == resolution.filename)
                    query_scopes[subquery.query] = DocumentScope('resolved', matched, 'planner_target_within_scope')
                elif scope.status == 'resolved':
                    blocked_queries.add(subquery.query)
                    scope_trace['skipped_queries'].append(subquery.query_id)
            resolved_count = sum(item['status'] == 'resolved' for item in target_resolutions.values())
            target_resolution_status = ('complete' if resolved_count == len(plan.subqueries)
                                        else 'partial' if resolved_count else 'unresolved')

        async def retrieve(query: str) -> List[Dict[str, Any]]:
            if query in blocked_queries:
                return []  # existing executor falls back to the scoped original
            active_scope = query_scopes.get(query, scope)
            documents = await self.retrieve_documents(
                query=query,
                collection_name=request.collection_name,
                milvus_api_url=request.milvus_api_url,
                top_k=candidate_k,
                score_threshold=request.score_threshold,
                filter_expr=active_scope.filter_expr,
            )
            filtered = [d for d in documents if active_scope.allows(d) and scope.allows(d)]
            scope_trace['dropped_candidates'] += len(documents) - len(filtered)
            return filtered

        execution = await execute_retrieval_plan(
            original_query=request.query,
            plan=plan,
            retrieve=retrieve,
            top_k=request.top_k,
            rrf_k=request.multi_query_config.rrf_k,
            original_reserve=request.multi_query_config.original_reserve,
            per_target_reserve=request.multi_query_config.per_target_reserve,
        )
        execution.trace["planner_latency_seconds"] = round(planner_latency, 4)
        execution.trace["target_resolution_status"] = target_resolution_status
        execution.trace["target_resolutions"] = target_resolutions
        execution.trace["document_scope"] = scope_trace
        return execution

    async def rerank_for_request(
        self,
        request: ChatRequest,
        documents: List[Dict[str, Any]],
        retrieval_trace: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Rerank without truncating a coverage-selected multi-query context."""

        if not request.use_reranker or not request.reranker_config:
            return documents
        reranker_config = request.reranker_config
        if (
            retrieval_trace.get("mode") == "multi_query"
            and reranker_config.top_n < len(documents)
        ):
            reranker_config = RerankerConfig(
                api_url=reranker_config.api_url,
                api_key=reranker_config.api_key,
                model_name=reranker_config.model_name,
                top_n=len(documents),
            )
        return await self.rerank_documents(
            query=request.query,
            documents=documents,
            reranker_config=reranker_config,
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

        for i, doc in enumerate(documents, 1):
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
                f"[S{i}] 来源: {filename}{page_info} | 相关度: {score:.3f}\n{text}"
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

    async def call_llm_claims(self, messages, llm_config):
        """One bounded structured generation call; no hidden retry/fallback."""
        try:
            async with AsyncOpenAI(api_key=llm_config.api_key, base_url=llm_config.api_url,
                                   max_retries=0, timeout=60) as client:
                response = await client.chat.completions.create(
                    model=llm_config.model_name, messages=messages,
                    temperature=llm_config.temperature, max_tokens=llm_config.max_tokens,
                    response_format={"type": "json_object"}, stream=False)
        except Exception:
            # Do not let provider errors expose keys or raw request data via SSE.
            raise HTTPException(status_code=502, detail="结构化回答服务调用失败，请稍后重试。") from None
        if not response.choices:
            raise ValueError('incomplete_claim_generation')
        choice = response.choices[0]
        if (choice.finish_reason != 'stop' or getattr(choice.message, 'refusal', None)
                or not isinstance(choice.message.content, str) or not choice.message.content.strip()):
            raise ValueError('incomplete_claim_generation')
        return choice.message.content

    async def generate_claim_bound_answer(self, request, documents):
        sentence_mode = request.claim_evidence_mode == 'sentence_v2'
        catalog_builder = evidence_units.build_catalog if sentence_mode else build_catalog
        message_builder = evidence_units.build_messages if sentence_mode else build_messages
        renderer = evidence_units.render_claim_answer if sentence_mode else render_claim_answer

        def failed(status):
            binding = empty_binding(status)
            if sentence_mode:
                binding['evidence_catalog_version'] = evidence_units.VERSION
            return binding

        try:
            catalog = catalog_builder(documents)
        except ValueError:
            return CLAIM_EVIDENCE_ERROR, failed('invalid_claim_evidence')
        messages = message_builder(request.query, catalog,
            [msg.model_dump() for msg in request.history], request.prompt_template)
        try:
            raw = await self.call_llm_claims(messages, request.llm_config)
        except ValueError:
            return CLAIM_GENERATION_ERROR, failed('incomplete_claim_generation')
        return renderer(raw, catalog)

    async def generate_answer(self, request, documents, *, streaming):
        """Shared dispatch; retain the legacy prompt and guard by default."""
        if request.answer_mode == 'claim_bound':
            answer, binding = await self.generate_claim_bound_answer(request, documents)
            return answer, binding['status'], binding
        template = request.prompt_template or self.default_prompt_template
        user_message = template.format(context=self.format_context(documents), query=request.query)
        messages = [dict(role=msg.role, content=msg.content) for msg in request.history if msg.role != 'system']
        messages.insert(0, {'role': 'system', 'content': GROUNDING_POLICY})
        messages.append({'role': 'user', 'content': user_message})
        if streaming:
            pending = [token async for token in self.call_llm_stream(messages, request.llm_config)]
            raw = ''.join(pending)
        else:
            raw = await self.call_llm_non_stream(messages, request.llm_config)
        answer, status = guard_answer(raw, len(documents))
        return answer, status, None

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
            retrieval_execution = await self.retrieve_for_request(request)
            documents = retrieval_execution.documents
            retrieval_trace = retrieval_execution.trace
            retrieve_time = time.time() - retrieve_start

            if not documents:
                # Knowledge-base mode must not fall back to model memory.
                print("⚠️ 未找到相关文档，返回证据不足提示")
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
                for token in (INSUFFICIENT_EVIDENCE,):
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
                        "documents_count": 0,
                        "answer_guard": "no_evidence",
                        "retrieval_trace": retrieval_trace,
                    }
                }, ensure_ascii=False) + "\n"
                return

            # 2. 重排序（可选）
            if request.use_reranker and request.reranker_config:
                rerank_start = time.time()
                documents = await self.rerank_for_request(
                    request,
                    documents,
                    retrieval_trace,
                )
                rerank_time = time.time() - rerank_start
                print(f"✓ 重排序耗时: {rerank_time:.2f}秒")
            else:
                rerank_time = 0

            # 3-6. Generate and validate the selected format before emitting text.
            llm_start = time.time()
            answer, guard_status, citation_binding = await self.generate_answer(request, documents, streaming=True)
            # Validate before emitting any text; token fragments can split citations.
            for token in (answer,):
                yield json.dumps({
                    "type": "content",
                    "data": token
                }, ensure_ascii=False) + "\n"
            llm_time = time.time() - llm_start

            # 7. 发送来源文档
            if request.return_source and documents:
                sources = []
                for index, doc in enumerate(documents, 1):
                    sources.append({
                        "source_id": f"S{index}",
                        "file_id": doc.get("file_id") or doc.get("metadata", {}).get("file_id"),
                        "chunk_text": doc["chunk_text"],
                        "filename": doc["filename"],
                        "score": doc["score"],
                        "retrieval_score": doc.get("retrieval_score"),
                        "rerank_score": doc.get("rerank_score"),
                        "query_rrf_score": doc.get("query_rrf_score"),
                        "matched_query_ids": doc.get("matched_query_ids"),
                        "query_ranks": doc.get("query_ranks"),
                        "section_intent": doc.get("section_intent"),
                        "section_boost": doc.get("section_boost"),
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
                    "answer_guard": guard_status,
                    **({'citation_binding': citation_binding} if citation_binding is not None else {}),
                    "total_time": total_time,
                    "documents_count": len(documents),
                    "retrieval_trace": retrieval_trace,
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
            retrieval_execution = await self.retrieve_for_request(request)
            documents = retrieval_execution.documents
            retrieval_trace = retrieval_execution.trace
            retrieve_time = time.time() - retrieve_start

            if not documents:
                # Knowledge-base mode must not fall back to model memory.
                print("⚠️ 未找到相关文档，返回证据不足提示")
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

                answer = INSUFFICIENT_EVIDENCE

                return ChatResponse(
                    success=True,
                    message="对话完成（未找到相关文档）",
                    answer=answer,
                    sources=None,
                    metadata={
                        "retrieve_time": retrieve_time,
                        "total_time": time.time() - start_time,
                        "documents_count": 0,
                        "answer_guard": "no_evidence",
                        "retrieval_trace": retrieval_trace,
                    }
                )

            # 2. 重排序（可选）
            if request.use_reranker and request.reranker_config:
                rerank_start = time.time()
                documents = await self.rerank_for_request(
                    request,
                    documents,
                    retrieval_trace,
                )
                rerank_time = time.time() - rerank_start
            else:
                rerank_time = 0

            # 3-6. Same contract and guard as the streaming endpoint.
            llm_start = time.time()
            answer, guard_status, citation_binding = await self.generate_answer(request, documents, streaming=False)
            llm_time = time.time() - llm_start

            # 7. 构建来源文档
            sources = None
            if request.return_source:
                sources = []
                for index, doc in enumerate(documents, 1):
                    source_doc = SourceDocument(
                        source_id=f"S{index}",
                        file_id=doc.get("file_id") or doc.get("metadata", {}).get("file_id"),
                        chunk_text=doc["chunk_text"],
                        filename=doc["filename"],
                        score=doc["score"],  # 主分数
                        retrieval_score=doc.get("retrieval_score"),  # 原始召回分数
                        rerank_score=doc.get("rerank_score"),  # 重排序分数
                        query_rrf_score=doc.get("query_rrf_score"),
                        matched_query_ids=doc.get("matched_query_ids"),
                        query_ranks=doc.get("query_ranks"),
                        section_intent=doc.get("section_intent"),
                        section_boost=doc.get("section_boost"),
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
                    "answer_guard": guard_status,
                    **({'citation_binding': citation_binding} if citation_binding is not None else {}),
                    "total_time": total_time,
                    "documents_count": len(documents),
                    "retrieval_trace": retrieval_trace,
                }
            )

        except HTTPException:
            raise
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
        "features": [
            "vector_retrieval",
            "multi_query_retrieval",
            "reranking",
            "streaming",
            "non_streaming",
        ]
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

    except HTTPException:
        raise
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
                "score_threshold": 0.1,
                "use_multi_query": False,
                "multi_query": {
                    "candidate_k_per_query": 10,
                    "rrf_k": 60,
                    "original_reserve": 4,
                    "per_target_reserve": 2,
                },
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
