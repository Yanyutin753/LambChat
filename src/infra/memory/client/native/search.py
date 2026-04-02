"""Search helpers for the native memory backend."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.infra.memory.client.native.content import hydrate_formatted_memory
from src.infra.memory.client.native.models import (
    STOPWORDS,
    char_ngrams,
    cosine_similarity,
    ensure_aware,
    has_cjk,
)
from src.kernel.config import settings


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
    current_time = now or datetime.now(timezone.utc)
    staleness_days = (current_time - ensure_aware(doc["updated_at"])).days
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
    collection, user_id: str, limit: int, memory_types: Optional[list[str]]
) -> list[dict]:
    base: dict[str, Any] = {"user_id": user_id, "source": {"$ne": "session_summary"}}
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
    cursor = collection.find(base).sort("updated_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [format_memory(doc, 0.0) for doc in docs]


async def text_search(
    collection, logger, user_id: str, query: str, limit: int, memory_types: Optional[list[str]]
) -> list[dict]:
    base: dict[str, Any] = {"user_id": user_id, "source": {"$ne": "session_summary"}}
    if memory_types:
        base["memory_type"] = {"$in": memory_types}
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
        docs = await keyword_fallback(collection, user_id, query, limit, memory_types)
    else:
        if not docs:
            docs = await keyword_fallback(collection, user_id, query, limit, memory_types)

    return [format_memory(doc, doc.get("score", 0)) for doc in docs]


async def keyword_fallback(
    collection, user_id: str, query: str, limit: int, memory_types: Optional[list[str]]
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

    cursor = collection.find(base).sort("updated_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def vector_search(
    backend, user_id: str, query: str, limit: int, memory_types: Optional[list[str]]
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
        "content_storage_mode": 1,
        "content_store_key": 1,
        "summary": 1,
        "memory_type": 1,
        "source": 1,
        "created_at": 1,
        "updated_at": 1,
        "embedding": 1,
    }
    cursor = backend._collection.find(base, projection).limit(200)
    docs = await cursor.to_list(length=200)
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


async def recall_memories(
    backend,
    user_id: str,
    query: str,
    max_results: int = 5,
    memory_types: Optional[list[str]] = None,
    touch_access: bool = True,
    enable_rerank: bool = True,
) -> dict[str, Any]:
    text_results = await text_search(
        backend._collection, backend._logger, user_id, query, max_results * 2, memory_types
    )

    vector_results: list[dict] = []
    if backend._embedding_fn:
        vector_results = await vector_search(backend, user_id, query, max_results * 2, memory_types)

    memories = rrf_merge(text_results, vector_results, max_results * 2)
    memories = prioritize_sources(memories)

    if not memories and is_context_overview_query(query):
        memories = await recent_context_fallback(
            backend._collection, user_id, max_results * 2, memory_types
        )

    if enable_rerank and memories and len(memories) > max_results:
        memories = await rerank_candidates(query, memories, max_results)
        memories = prioritize_sources(memories)

    if memories:
        memories = memories[:max_results]
        memories = [await hydrate_formatted_memory(backend, memory) for memory in memories]
        if touch_access:
            await backend._update_access_stats([m["memory_id"] for m in memories])

    return {
        "success": True,
        "query": query,
        "memories": memories,
        "search_mode": "hybrid" if backend._embedding_fn else "text",
    }
