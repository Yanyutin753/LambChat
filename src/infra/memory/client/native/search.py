"""Search helpers for the native memory backend."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, Optional

import httpx

from src.infra.logging import get_logger
from src.infra.memory.client.native.content import hydrate_formatted_memory
from src.infra.memory.client.native.models import (
    STOPWORDS,
    char_ngrams,
    cosine_similarity,
    has_cjk,
)
from src.infra.session.conversation_history import ConversationHistoryService
from src.infra.utils.datetime import ensure_utc, utc_now
from src.kernel.config import settings
from src.kernel.schemas.conversation_history import ConversationSourceRef

NATIVE_MEMORY_RECALL_MAX_RESULTS = 20
NATIVE_MEMORY_RECALL_QUERY_MAX_CHARS = 2_000
logger = get_logger(__name__)


def _clip_recall_query(query: str) -> str:
    normalized = str(query or "").strip()
    if len(normalized) <= NATIVE_MEMORY_RECALL_QUERY_MAX_CHARS:
        return normalized
    return normalized[:NATIVE_MEMORY_RECALL_QUERY_MAX_CHARS].rstrip()


async def _hydrate_memories_limited(
    backend, memories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not memories:
        return []

    results: list[dict[str, Any] | None] = [None] * len(memories)
    next_index = 0
    lock = asyncio.Lock()
    worker_count = min(
        max(1, int(getattr(settings, "NATIVE_MEMORY_HYDRATE_CONCURRENCY", 4) or 1)),
        len(memories),
    )

    async def _worker() -> None:
        nonlocal next_index
        while True:
            async with lock:
                if next_index >= len(memories):
                    return
                index = next_index
                next_index += 1
            results[index] = await hydrate_formatted_memory(backend, memories[index])

    await asyncio.gather(*(_worker() for _ in range(worker_count)))
    return [memory for memory in results if memory is not None]


def build_keyword_clauses(query: str) -> list[dict[str, Any]]:
    normalized = query.strip()
    terms: list[str] = []

    if has_cjk(normalized):
        compact = re.sub(r"\s+", "", normalized)
        seen: set[str] = set()
        for n in (3, 2):
            for i in range(max(len(compact) - n + 1, 0)):
                term = compact[i : i + n]
                if len(term) < 2 or term in seen:
                    continue
                if all(ch in "的是在了和有" for ch in term):
                    continue
                seen.add(term)
                terms.append(term)
                if len(terms) >= 5:
                    break
            if len(terms) >= 5:
                break
    else:
        terms = [w for w in normalized.lower().split() if len(w) >= 2 and w not in STOPWORDS][:5]

    clauses: list[dict[str, Any]] = []
    for term in terms:
        escaped = re.escape(term)
        clauses.append({"content": {"$regex": escaped, "$options": "i"}})
        clauses.append({"summary": {"$regex": escaped, "$options": "i"}})
        clauses.append({"title": {"$regex": escaped, "$options": "i"}})
    return clauses


def format_memory(doc: dict, score: float, now: datetime | None = None) -> dict:
    current_time = now or utc_now()
    staleness_days = (current_time - ensure_utc(doc["updated_at"])).days
    staleness_days_cfg = getattr(settings, "NATIVE_MEMORY_STALENESS_DAYS", 30)

    result: dict[str, Any] = {
        "memory_id": doc["memory_id"],
        "user_id": doc.get("user_id"),
        "text": doc["content"],
        "preview": doc.get("content", ""),
        "summary": doc["summary"],
        "title": doc.get("title", ""),
        "type": doc["memory_type"],
        "source": doc.get("source", "manual"),
        "storage_mode": doc.get("content_storage_mode", "inline"),
        "content_store_key": doc.get("content_store_key"),
        "source_refs": doc.get("source_refs") or [],
        "created_at": doc["created_at"].isoformat()
        if isinstance(doc["created_at"], datetime)
        else str(doc["created_at"]),
        "score": score,
    }
    if staleness_days > staleness_days_cfg:
        result["staleness_warning"] = (
            f"This memory is {staleness_days} days old and may be outdated"
        )
    return result


def prioritize_sources(memories: list[dict]) -> list[dict]:
    source_order = {
        "manual": 0,
        "auto_retained": 1,
        "consolidated": 2,
        "session_summary": 99,
    }
    return sorted(
        memories,
        key=lambda memory: (
            source_order.get(str(memory.get("source", "")), 50),
            -float(memory.get("score", 0.0) or 0.0),
        ),
    )


def is_context_overview_query(query: str) -> bool:
    lowered = query.strip().lower()
    overview_markers = (
        "user preferences",
        "project context",
        "context overview",
        "what should i know",
        "memory overview",
        "relevant memories",
    )
    return any(marker in lowered for marker in overview_markers)


async def recent_context_fallback(
    collection,
    user_id: str,
    limit: int,
    memory_types: Optional[list[str]],
    context_filter: Optional[str] = None,
) -> list[dict]:
    base: dict[str, Any] = {"user_id": user_id, "source": {"$ne": "session_summary"}}
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
    if context_filter:
        base["context"] = context_filter
    cursor = (
        collection.find(
            base,
            {
                "memory_id": 1,
                "user_id": 1,
                "content": 1,
                "summary": 1,
                "title": 1,
                "memory_type": 1,
                "source": 1,
                "content_storage_mode": 1,
                "content_store_key": 1,
                "created_at": 1,
                "updated_at": 1,
                "source_refs": 1,
            },
        )
        .sort("updated_at", -1)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    return [format_memory(doc, 0.0) for doc in docs]


async def text_search(
    collection,
    logger,
    user_id: str,
    query: str,
    limit: int,
    memory_types: Optional[list[str]],
    context_filter: Optional[str] = None,
) -> list[dict]:
    base: dict[str, Any] = {"user_id": user_id, "source": {"$ne": "session_summary"}}
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
    if context_filter:
        base["context"] = context_filter
    base["$text"] = {"$search": query}

    try:
        cursor = (
            collection.find(base, {"score": {"$meta": "textScore"}})
            .sort([("score", {"$meta": "textScore"})])
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
    except Exception:
        logger.debug("[NativeMemory] Text search failed, falling back to keyword match")
        docs = await keyword_fallback(collection, user_id, query, limit, memory_types, context_filter)
    else:
        if not docs:
            docs = await keyword_fallback(collection, user_id, query, limit, memory_types, context_filter)

    return [format_memory(doc, doc.get("score", 0)) for doc in docs]


async def keyword_fallback(
    collection,
    user_id: str,
    query: str,
    limit: int,
    memory_types: Optional[list[str]],
    context_filter: Optional[str] = None,
) -> list[dict]:
    clauses = build_keyword_clauses(query)
    if not clauses:
        return []

    base: dict[str, Any] = {
        "user_id": user_id,
        "source": {"$ne": "session_summary"},
        "$or": clauses,
    }
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
    if context_filter:
        base["context"] = context_filter

    _projection = {
        "memory_id": 1,
        "user_id": 1,
        "content": 1,
        "summary": 1,
        "title": 1,
        "memory_type": 1,
        "source": 1,
        "content_storage_mode": 1,
        "content_store_key": 1,
        "created_at": 1,
        "updated_at": 1,
        "source_refs": 1,
    }
    try:
        cursor = collection.find(base, _projection)
    except TypeError:
        cursor = collection.find(base)
    cursor = cursor.sort("updated_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def vector_search(
    backend,
    user_id: str,
    query: str,
    limit: int,
    memory_types: Optional[list[str]],
    context_filter: Optional[str] = None,
) -> list[dict]:
    query_vec = await backend._maybe_embed(query)
    if not query_vec:
        return []

    base: dict[str, Any] = {
        "user_id": user_id,
        "source": {"$ne": "session_summary"},
        "embedding": {"$exists": True, "$ne": None},
    }
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
    if context_filter:
        base["context"] = context_filter

    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "native_mem_vector_idx",
                    "path": "embedding",
                    "queryVector": query_vec,
                    "numCandidates": limit * 5,
                    "limit": limit,
                }
            },
            {"$match": base},
        ]
        cursor = backend._collection.aggregate(pipeline)
        docs = await cursor.to_list(length=limit)
        return [format_memory(doc, doc.get("score", 1.0)) for doc in docs]
    except Exception:
        pass

    backend._logger.debug(
        "[NativeMemory] Atlas $vectorSearch unavailable, using Python cosine fallback"
    )
    projection = {
        "user_id": 1,
        "memory_id": 1,
        "content": 1,
        "title": 1,
        "content_storage_mode": 1,
        "content_store_key": 1,
        "summary": 1,
        "memory_type": 1,
        "source": 1,
        "created_at": 1,
        "updated_at": 1,
        "embedding": 1,
        "source_refs": 1,
    }
    scan_limit = min(limit * 3, 100)
    cursor = backend._collection.find(base, projection).sort("updated_at", -1).limit(scan_limit)
    docs = await cursor.to_list(length=scan_limit)
    scored = []
    for d in docs:
        emb = d.get("embedding")
        if emb:
            sim = cosine_similarity(query_vec, emb)
            scored.append((sim, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [format_memory(d, sim) for sim, d in scored[:limit]]


def _query_terms(query: str) -> set[str]:
    normalized = query.strip().lower()
    if not normalized:
        return set()
    if has_cjk(normalized):
        return char_ngrams(normalized, 2) | char_ngrams(normalized, 3)
    return {w for w in re.findall(r"\w+", normalized) if len(w) >= 2 and w not in STOPWORDS}


def _field_overlap_score(query_terms: set[str], text: str) -> float:
    if not query_terms or not text.strip():
        return 0.0
    lowered = text.lower()
    if has_cjk(lowered):
        field_terms = char_ngrams(lowered, 2) | char_ngrams(lowered, 3)
    else:
        field_terms = {w for w in re.findall(r"\w+", lowered) if len(w) >= 2 and w not in STOPWORDS}
    if not field_terms:
        return 0.0
    overlap = len(query_terms & field_terms)
    coverage = overlap / max(len(query_terms), 1)
    density = overlap / max(len(field_terms), 1)
    return coverage * 0.7 + density * 0.3


def local_rerank(query: str, candidates: list[dict], max_results: int) -> list[dict]:
    query_terms = _query_terms(query)

    def score(candidate: dict) -> tuple[float, float, float, float]:
        title_score = _field_overlap_score(query_terms, str(candidate.get("title", "")))
        summary_score = _field_overlap_score(query_terms, str(candidate.get("summary", "")))
        text_score = _field_overlap_score(query_terms, str(candidate.get("text", "")))
        base_score = float(candidate.get("score", 0.0) or 0.0)
        blended = base_score + title_score * 0.8 + summary_score * 0.6 + text_score * 0.3
        return (
            blended,
            title_score,
            summary_score,
            text_score,
        )

    ranked = sorted(candidates, key=score, reverse=True)
    return ranked[:max_results]


async def rerank_candidates(query: str, candidates: list[dict], max_results: int) -> list[dict]:
    rerank_model = getattr(settings, "NATIVE_MEMORY_RERANK_MODEL", "") or ""
    api_base = getattr(settings, "NATIVE_MEMORY_RERANK_API_BASE", "") or ""
    api_key = getattr(settings, "NATIVE_MEMORY_RERANK_API_KEY", "") or ""

    if not rerank_model or not api_base or not api_key or len(candidates) <= 1:
        return local_rerank(query, candidates, max_results)

    documents = [
        "\n".join(
            part
            for part in (
                str(candidate.get("title", "")).strip(),
                str(candidate.get("summary", "")).strip(),
                str(candidate.get("text", "")).strip(),
            )
            if part
        )
        for candidate in candidates
    ]

    try:
        async with httpx.AsyncClient(
            base_url=api_base.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(15.0),
        ) as client:
            response = await client.post(
                "/v1/rerank",
                json={
                    "model": rerank_model,
                    "query": query,
                    "documents": documents,
                    "top_n": max_results,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return local_rerank(query, candidates, max_results)

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return local_rerank(query, candidates, max_results)

    ranked: list[dict] = []
    seen: set[int] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidates) or idx in seen:
            continue
        candidate = dict(candidates[idx])
        if "relevance_score" in item:
            candidate["score"] = float(item["relevance_score"])
        ranked.append(candidate)
        seen.add(idx)

    return ranked[:max_results] if ranked else local_rerank(query, candidates, max_results)


def rrf_merge(
    text_results: list[dict], vector_results: list[dict], max_results: int, k: int = 60
) -> list[dict]:
    scores: dict[str, dict] = {}

    for rank, item in enumerate(text_results):
        mid = item["memory_id"]
        if mid not in scores:
            scores[mid] = {"data": item, "rrf_score": 0.0}
        scores[mid]["rrf_score"] += 1.0 / (k + rank + 1)

    for rank, item in enumerate(vector_results):
        mid = item["memory_id"]
        if mid not in scores:
            scores[mid] = {"data": item, "rrf_score": 0.0}
        scores[mid]["rrf_score"] += 1.0 / (k + rank + 1)

    merged = sorted(scores.values(), key=lambda x: x["rrf_score"], reverse=True)
    return [entry["data"] for entry in merged[:max_results]]


async def validate_memory_source_refs(
    user_id: str, memories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Reauthorize recalled conversation pointers without dropping the memory."""
    normalized_by_memory: list[list[ConversationSourceRef]] = []
    all_refs: list[ConversationSourceRef] = []
    for memory in memories:
        normalized: list[ConversationSourceRef] = []
        for raw_ref in memory.get("source_refs") or []:
            try:
                ref = (
                    raw_ref
                    if isinstance(raw_ref, ConversationSourceRef)
                    else ConversationSourceRef.model_validate(raw_ref)
                )
            except Exception:
                continue
            normalized.append(ref)
            all_refs.append(ref)
        normalized_by_memory.append(normalized)

    if not all_refs:
        return [{**memory, "source_refs": []} for memory in memories]

    try:
        allowed_refs = await ConversationHistoryService().validate_source_refs(user_id, all_refs)
    except Exception as exc:
        logger.warning(
            "[NativeMemory] Recalled source reference validation failed: %s",
            type(exc).__name__,
        )
        allowed_refs = []
    allowed_pairs = {(ref.session_id, ref.run_id) for ref in allowed_refs}

    validated: list[dict[str, Any]] = []
    for memory, refs in zip(memories, normalized_by_memory, strict=True):
        validated.append(
            {
                **memory,
                "source_refs": [
                    ref.model_dump()
                    for ref in refs
                    if (ref.session_id, ref.run_id) in allowed_pairs
                ],
            }
        )
    return validated


async def recall_memories(
    backend,
    user_id: str,
    query: str,
    max_results: int = 5,
    memory_types: Optional[list[str]] = None,
    touch_access: bool = True,
    enable_rerank: bool = True,
    context_filter: Optional[str] = None,
) -> dict[str, Any]:
    max_results = max(1, min(int(max_results or 1), NATIVE_MEMORY_RECALL_MAX_RESULTS))
    query = _clip_recall_query(query)
    text_coro = text_search(
        backend._collection,
        backend._logger,
        user_id,
        query,
        max_results * 2,
        memory_types,
        context_filter,
    )

    if backend._embedding_fn:
        text_results, vector_results = await asyncio.gather(
            text_coro,
            vector_search(backend, user_id, query, max_results * 2, memory_types, context_filter),
        )
    else:
        text_results = await text_coro
        vector_results = []

    memories = rrf_merge(text_results, vector_results, max_results * 2)

    if not memories and is_context_overview_query(query):
        memories = await recent_context_fallback(
            backend._collection, user_id, max_results * 2, memory_types, context_filter
        )

    if enable_rerank and memories and len(memories) > max_results:
        memories = await rerank_candidates(query, memories, max_results)
    memories = prioritize_sources(memories)

    if memories:
        memories = memories[:max_results]
        min_score = getattr(settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0.3)
        if min_score > 0:
            memories = [m for m in memories if m.get("score", 1.0) >= min_score]
        memories = await _hydrate_memories_limited(backend, memories)
        memories = await validate_memory_source_refs(user_id, memories)

        if touch_access:
            await backend._update_access_stats([m["memory_id"] for m in memories], user_id)

    return {
        "success": True,
        "query": query,
        "memories": memories,
        "search_mode": "hybrid" if backend._embedding_fn else "text",
    }
