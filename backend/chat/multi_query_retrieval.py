"""Validated query planning and coverage-aware multi-query retrieval.

The module is intentionally independent from FastAPI and any concrete LLM or
vector-store client.  Callers provide one async text generator for planning and
one async retrieval function, which keeps the orchestration deterministic and
unit-testable.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any, Awaitable, Callable, Sequence


PlannerGenerator = Callable[[list[dict[str, str]]], Awaitable[str]]
Retriever = Callable[[str], Awaitable[list[dict[str, Any]]]]


PLANNER_SYSTEM_PROMPT = """You plan retrieval for a scientific-paper RAG system.
Classify the user question as either single-paper/general retrieval or an
explicit comparison that needs independent evidence about two or three targets.

Return JSON only with this schema:
{
  "intent": "single" | "comparison",
  "subqueries": [
    {"id": "short-stable-id", "target": "paper or method", "query": "standalone evidence question"}
  ]
}

Rules:
- For single intent, return an empty subqueries array.
- For comparison intent, return exactly one standalone question per target.
- Make every subquery an atomic retrieval question of at most 30 words.
- Preserve the exact mechanism, metric, experiment, or claim requested for that
  target, including the user's important technical terms.
- The target value must be only the target's short canonical name and must be
  unique. Never split one target into multiple subqueries; keep all explicitly
  requested facets for that target in its single concise query.
- Ask only for that target's half of the comparison. Do not ask how it differs
  from the other target.
- Do not broaden the question with extra facets such as benchmarks, complexity,
  architecture, objectives, decoding strategies, or implementation details
  unless the user explicitly requested those facets.
- Do not answer the question and do not invent paper titles.
- Use two or three distinct subqueries; never repeat the original comparison verbatim.
"""


@dataclass(frozen=True)
class RetrievalSubquery:
    query_id: str
    target: str
    query: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.query_id, "target": self.target, "query": self.query}


@dataclass(frozen=True)
class RetrievalPlan:
    mode: str
    subqueries: tuple[RetrievalSubquery, ...] = field(default_factory=tuple)
    fallback_reason: str | None = None
    planner_source: str = "llm"

    @property
    def is_multi_query(self) -> bool:
        return self.mode == "comparison" and len(self.subqueries) >= 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "subqueries": [item.to_dict() for item in self.subqueries],
            "fallback_reason": self.fallback_reason,
            "planner_source": self.planner_source,
        }


@dataclass(frozen=True)
class RetrievalExecution:
    documents: list[dict[str, Any]]
    trace: dict[str, Any]


@dataclass(frozen=True)
class TargetFilenameResolution:
    """Auditable result of mapping one planner target to a corpus file."""

    target: str
    status: str
    filename: str | None = None
    score: float = 0.0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "status": self.status,
            "filename": self.filename,
            "score": round(self.score, 4),
            "reason": self.reason,
        }


_TARGET_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "hosted",
    "is",
    "method",
    "model",
    "models",
    "of",
    "on",
    "paper",
    "report",
    "service",
    "system",
    "technical",
    "the",
}


def _identity_tokens(value: str) -> list[str]:
    """Return identity-bearing tokens from a target name or PDF filename."""

    stem = PurePath(str(value or "")).stem.casefold()
    tokens = re.findall(r"[a-z]+\d*|\d+", stem)
    return [
        token
        for token in tokens
        if token not in _TARGET_STOPWORDS
        and not re.fullmatch(r"pmc\d+", token)
        and not (token.isdigit() and len(token) >= 4)
    ]


def _acronym_windows(tokens: Sequence[str]) -> set[str]:
    windows: set[str] = set()
    for start in range(len(tokens)):
        for length in range(2, min(5, len(tokens) - start) + 1):
            window = tokens[start : start + length]
            if all(token and token[0].isalpha() for token in window):
                windows.add("".join(token[0] for token in window))
    return windows


def _target_filename_score(target: str, filename: str) -> float:
    target_tokens = _identity_tokens(target)
    filename_tokens = _identity_tokens(filename)
    if not target_tokens or not filename_tokens:
        return 0.0

    target_identity = "".join(target_tokens)
    filename_identity = "".join(filename_tokens)
    if target_identity == filename_identity:
        return 1.0
    if len(target_identity) >= 4 and target_identity in filename_identity:
        return 0.98
    if len(filename_identity) >= 4 and filename_identity in target_identity:
        return 0.95

    filename_token_set = set(filename_tokens)
    acronyms = _acronym_windows(filename_tokens)
    matched_targets = sum(
        token in filename_token_set or token in acronyms for token in target_tokens
    )
    target_coverage = matched_targets / len(target_tokens)
    exact_overlap = len(set(target_tokens) & filename_token_set) / len(target_tokens)
    return 0.8 * target_coverage + 0.2 * exact_overlap


def resolve_target_filename(
    target: str,
    filenames: Sequence[str],
    *,
    minimum_score: float = 0.72,
    ambiguity_margin: float = 0.12,
) -> TargetFilenameResolution:
    """Resolve a free-form planner target only when one filename is unambiguous.

    Returning ``unresolved`` is intentional: an unsafe filename guess would
    silently remove valid evidence. Callers must retain the existing unfiltered
    retrieval path in that case.
    """

    unique_filenames = sorted({str(item).strip() for item in filenames if str(item).strip()})
    ranked = sorted(
        (
            (_target_filename_score(target, filename), filename)
            for filename in unique_filenames
        ),
        key=lambda item: (-item[0], item[1]),
    )
    if not ranked or ranked[0][0] < minimum_score:
        return TargetFilenameResolution(
            target=target,
            status="unresolved",
            score=ranked[0][0] if ranked else 0.0,
            reason="low_confidence",
        )

    best_score, best_filename = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if second_score > 0 and best_score - second_score < ambiguity_margin:
        return TargetFilenameResolution(
            target=target,
            status="unresolved",
            score=best_score,
            reason="ambiguous",
        )
    return TargetFilenameResolution(
        target=target,
        status="resolved",
        filename=best_filename,
        score=best_score,
        reason="unique_lexical_match",
    )


def single_query_plan(
    reason: str | None = None, *, planner_source: str = "llm"
) -> RetrievalPlan:
    return RetrievalPlan(
        mode="single",
        fallback_reason=reason,
        planner_source=planner_source,
    )


def _decode_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("planner output does not contain a JSON object")
    value, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value, dict):
        raise ValueError("planner output must be a JSON object")
    return value


def _normalize_query_id(value: str, index: int) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-_")
    return normalized[:32] or f"target-{index}"


def _normalize_target_identity(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold(), flags=re.UNICODE)


def parse_query_plan(
    raw: str,
    original_query: str,
    *,
    max_subqueries: int = 3,
) -> RetrievalPlan:
    """Parse and strictly validate one planner response."""

    if max_subqueries < 2:
        raise ValueError("max_subqueries must be at least two")
    payload = _decode_json_object(raw)
    intent = str(payload.get("intent", "")).strip().lower()
    if intent == "single":
        return single_query_plan(planner_source="llm")
    if intent != "comparison":
        raise ValueError("planner intent must be single or comparison")

    raw_subqueries = payload.get("subqueries")
    if not isinstance(raw_subqueries, list):
        raise ValueError("comparison plan requires a subqueries array")
    if not 2 <= len(raw_subqueries) <= max_subqueries:
        raise ValueError(
            f"comparison plan requires between 2 and {max_subqueries} subqueries"
        )

    normalized_original = original_query.strip().casefold()
    query_ids: set[str] = set()
    target_identities: set[str] = set()
    normalized_queries: set[str] = set()
    subqueries: list[RetrievalSubquery] = []
    for index, item in enumerate(raw_subqueries, 1):
        if not isinstance(item, dict):
            raise ValueError("each subquery must be an object")
        target = str(item.get("target", "")).strip()
        query = str(item.get("query", "")).strip()
        if not target or not query:
            raise ValueError("each subquery requires nonempty target and query")
        target_identity = _normalize_target_identity(target)
        if not target_identity or target_identity in target_identities:
            raise ValueError("subquery targets must be unique")
        if len(query) > 500:
            raise ValueError("subquery exceeds 500 characters")
        normalized_query = query.casefold()
        if normalized_query == normalized_original or normalized_query in normalized_queries:
            raise ValueError("subqueries must be distinct from each other and the original")
        query_id = _normalize_query_id(str(item.get("id", target)), index)
        if query_id == "original" or query_id in query_ids:
            raise ValueError("subquery ids must be unique and cannot be original")
        query_ids.add(query_id)
        target_identities.add(target_identity)
        normalized_queries.add(normalized_query)
        subqueries.append(
            RetrievalSubquery(query_id=query_id, target=target, query=query)
        )

    return RetrievalPlan(mode="comparison", subqueries=tuple(subqueries))


async def create_query_plan(
    original_query: str,
    generate: PlannerGenerator,
    *,
    timeout_seconds: float = 12.0,
    max_subqueries: int = 3,
) -> RetrievalPlan:
    """Generate a plan, always falling back safely on planner failures."""

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": original_query},
    ]
    deadline = time.perf_counter() + timeout_seconds
    try:
        raw = await asyncio.wait_for(generate(messages), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return single_query_plan("planner_timeout")
    except Exception:
        return single_query_plan("planner_error")

    try:
        return parse_query_plan(
            raw,
            original_query,
            max_subqueries=max_subqueries,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return single_query_plan("invalid_planner_output")
        repair_messages = [
            *messages,
            {"role": "assistant", "content": str(raw)[:2000]},
            {
                "role": "user",
                "content": (
                    f"The JSON plan was invalid: {exc}. Return one corrected "
                    "JSON object only. Keep one unique target and one query per "
                    "comparison target."
                ),
            },
        ]
        try:
            repaired_raw = await asyncio.wait_for(
                generate(repair_messages), timeout=remaining
            )
            return parse_query_plan(
                repaired_raw,
                original_query,
                max_subqueries=max_subqueries,
            )
        except asyncio.TimeoutError:
            return single_query_plan("planner_timeout")
        except Exception:
            return single_query_plan("invalid_planner_output")


def _chunk_id(hit: dict[str, Any]) -> str:
    return str((hit.get("metadata") or {}).get("chunk_id", ""))


def _query_rrf(
    ranked_hits_by_query: dict[str, list[dict[str, Any]]],
    *,
    rrf_k: int = 60,
) -> list[dict[str, Any]]:
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")
    if not ranked_hits_by_query:
        return []

    fused_by_id: dict[str, dict[str, Any]] = {}
    for query_id, hits in ranked_hits_by_query.items():
        seen_in_query: set[str] = set()
        for rank, hit in enumerate(hits, 1):
            chunk_id = _chunk_id(hit)
            if not chunk_id:
                raise ValueError(f"{query_id} candidate at rank {rank} has no chunk id")
            if chunk_id in seen_in_query:
                raise ValueError(f"{query_id} contains duplicate chunk id: {chunk_id}")
            seen_in_query.add(chunk_id)
            dense_score = float(hit.get("retrieval_score", hit.get("score", 0.0)))

            if chunk_id not in fused_by_id:
                item = dict(hit)
                item["retrieval_score"] = dense_score
                item["matched_query_ids"] = []
                item["query_ranks"] = {}
                item["query_rrf_score"] = 0.0
                fused_by_id[chunk_id] = item
            item = fused_by_id[chunk_id]
            item["retrieval_score"] = max(
                float(item["retrieval_score"]), dense_score
            )
            item["matched_query_ids"].append(query_id)
            item["query_ranks"][query_id] = rank
            item["query_rrf_score"] += 1.0 / (rrf_k + rank)

    fused = list(fused_by_id.values())
    for item in fused:
        item["score"] = float(item["query_rrf_score"])
    return sorted(
        fused,
        key=lambda item: (
            -float(item["query_rrf_score"]),
            min(int(rank) for rank in item["query_ranks"].values()),
            _chunk_id(item),
        ),
    )


def _coverage_select(
    fused_hits: list[dict[str, Any]],
    required_query_ids: list[str],
    *,
    top_k: int,
    original_reserve: int = 0,
    per_target_reserve: int = 1,
) -> list[dict[str, Any]]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if len(required_query_ids) != len(set(required_query_ids)):
        raise ValueError("required query ids must be unique")
    if original_reserve < 0:
        raise ValueError("original_reserve cannot be negative")
    if per_target_reserve <= 0:
        raise ValueError("per_target_reserve must be positive")
    if original_reserve + per_target_reserve * len(required_query_ids) > top_k:
        raise ValueError("top_k cannot be smaller than the configured reserve budget")

    selected_ids: set[str] = set()
    selected: list[dict[str, Any]] = []

    original_candidates = sorted(
        (
            item
            for item in fused_hits
            if "original" in (item.get("query_ranks") or {})
        ),
        key=lambda item: (int(item["query_ranks"]["original"]), _chunk_id(item)),
    )
    for candidate in original_candidates[:original_reserve]:
        selected.append(candidate)
        selected_ids.add(_chunk_id(candidate))

    for query_id in required_query_ids:
        target_candidates = sorted(
            (
                item
                for item in fused_hits
                if query_id in (item.get("query_ranks") or {})
            ),
            key=lambda item: (int(item["query_ranks"][query_id]), _chunk_id(item)),
        )
        for candidate in target_candidates[:per_target_reserve]:
            chunk_id = _chunk_id(candidate)
            if chunk_id in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(chunk_id)

    for item in fused_hits:
        if len(selected) >= top_k:
            break
        chunk_id = _chunk_id(item)
        if chunk_id in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(chunk_id)

    fused_order = {_chunk_id(item): rank for rank, item in enumerate(fused_hits)}
    return sorted(selected[:top_k], key=lambda item: fused_order[_chunk_id(item)])


async def execute_retrieval_plan(
    *,
    original_query: str,
    plan: RetrievalPlan,
    retrieve: Retriever,
    top_k: int,
    rrf_k: int = 60,
    original_reserve: int = 4,
    per_target_reserve: int = 2,
) -> RetrievalExecution:
    """Run original and target retrieval concurrently with safe degradation."""

    async def retrieve_one(
        query_id: str, target: str | None, query: str
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            hits = await retrieve(query)
            return {
                "id": query_id,
                "target": target,
                "query": query,
                "status": "success",
                "latency_seconds": round(time.perf_counter() - started, 4),
                "hits": hits,
            }
        except Exception as exc:
            return {
                "id": query_id,
                "target": target,
                "query": query,
                "status": "error",
                "latency_seconds": round(time.perf_counter() - started, 4),
                "error_type": type(exc).__name__,
                "exception": exc,
            }

    async def original_only(reason: str | None) -> RetrievalExecution:
        result = await retrieve_one("original", None, original_query)
        if result["status"] == "error":
            raise result["exception"]
        documents = result["hits"][:top_k]
        result.pop("hits", None)
        return RetrievalExecution(
            documents=documents,
            trace={
                "mode": "single_query_fallback" if reason else "single_query",
                "fallback_reason": reason,
                "plan": plan.to_dict(),
                "queries": [{**result, "result_count": len(documents)}],
                "final_count": len(documents),
            },
        )

    if not plan.is_multi_query:
        return await original_only(plan.fallback_reason)
    reserve_budget = original_reserve + per_target_reserve * len(plan.subqueries)
    if reserve_budget > top_k:
        return await original_only("insufficient_top_k_for_coverage")

    specs = [("original", None, original_query)] + [
        (item.query_id, item.target, item.query) for item in plan.subqueries
    ]
    results = await asyncio.gather(
        *(retrieve_one(query_id, target, query) for query_id, target, query in specs)
    )
    original_result = results[0]
    if original_result["status"] == "error":
        raise original_result["exception"]
    failed_targets = [item for item in results[1:] if item["status"] != "success"]
    empty_targets = [item for item in results[1:] if not item.get("hits")]
    if failed_targets or empty_targets:
        documents = original_result["hits"][:top_k]
        trace_queries = []
        for item in results:
            trace_item = {key: value for key, value in item.items() if key not in {"hits", "exception"}}
            trace_item["result_count"] = len(item.get("hits", []))
            trace_queries.append(trace_item)
        return RetrievalExecution(
            documents=documents,
            trace={
                "mode": "single_query_fallback",
                "fallback_reason": "target_retrieval_failed",
                "plan": plan.to_dict(),
                "queries": trace_queries,
                "final_count": len(documents),
            },
        )

    ranked_by_query = {
        str(item["id"]): item["hits"]
        for item in results
    }
    fused = _query_rrf(ranked_by_query, rrf_k=rrf_k)
    documents = _coverage_select(
        fused,
        [item.query_id for item in plan.subqueries],
        top_k=top_k,
        original_reserve=original_reserve,
        per_target_reserve=per_target_reserve,
    )
    trace_queries = []
    for item in results:
        trace_item = {key: value for key, value in item.items() if key != "hits"}
        trace_item["result_count"] = len(item["hits"])
        trace_queries.append(trace_item)
    return RetrievalExecution(
        documents=documents,
        trace={
            "mode": "multi_query",
            "fallback_reason": None,
            "plan": plan.to_dict(),
            "queries": trace_queries,
            "unique_candidate_count": len(fused),
            "final_count": len(documents),
        },
    )
