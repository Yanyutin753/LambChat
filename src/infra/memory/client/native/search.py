"""Search helpers for the native memory backend."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from src.infra.memory.client.native.content import hydrate_formatted_memory
from src.infra.memory.client.native.models import (
    STOPWORDS,
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


async def llm_rerank(
    backend, user_id: str, query: str, candidates: list[dict], max_results: int
) -> list[dict]:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        model = backend._get_memory_model()

        items_text = "\n".join(f"[{i}] {m['summary']}" for i, m in enumerate(candidates))

        prompt = (
            f"Query: {query}\n\n"
            f"Ranked by relevance:\n{items_text}\n\n"
            f"Return a JSON array of up to {max_results} index numbers (most relevant first). "
            "Be strict — only include memories that are genuinely useful for this query."
        )

        response = await model.ainvoke(
            [
                SystemMessage(
                    content="You rank memory relevance. Output only a JSON array of numbers, e.g. [0, 3, 1]."
                ),
                HumanMessage(content=prompt),
            ],
        )

        text = response.content
        if isinstance(text, list):
            for item in text:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    break
            else:
                return candidates[:max_results]
        text = str(text).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        indices = json.loads(text)
        if not isinstance(indices, list):
            return candidates[:max_results]

        ranked = []
        for idx in indices:
            if isinstance(idx, (int, float)) and 0 <= int(idx) < len(candidates):
                ranked.append(candidates[int(idx)])
        return ranked[:max_results] if ranked else candidates[:max_results]

    except Exception as e:
        backend._logger.debug("[NativeMemory] LLM rerank failed, using RRF order: %s", e)
        return candidates[:max_results]


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

    if memories and len(memories) > max_results:
        memories = await llm_rerank(backend, user_id, query, memories, max_results)
        memories = prioritize_sources(memories)

    if memories:
        memories = memories[:max_results]
        memories = [await hydrate_formatted_memory(backend, memory) for memory in memories]
        await backend._update_access_stats([m["memory_id"] for m in memories])

    return {
        "success": True,
        "query": query,
        "memories": memories,
        "search_mode": "hybrid" if backend._embedding_fn else "text",
    }
