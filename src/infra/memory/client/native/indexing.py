"""Indexing helpers for the native memory backend."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from src.infra.memory.client.native.models import ensure_aware
from src.infra.memory.client.types import MemoryType
from src.kernel.config import settings


def choose_index_memories(
    docs: list[dict[str, Any]],
    per_type_limit: int,
    now: datetime,
    staleness_days: int,
) -> list[dict[str, Any]]:
    def score(doc: dict[str, Any]) -> tuple[float, float]:
        source = str(doc.get("source", "manual"))
        source_score = (
            2.0
            if source == "manual"
            else 1.0
            if source == "auto_retained"
            else 0.8
            if source == "consolidated"
            else 0.5
        )
        access_score = min(float(doc.get("access_count", 0) or 0), 5.0) * 0.3
        age_days = (now - ensure_aware(doc["updated_at"])).days
        freshness_score = max(0.0, 2.0 - (age_days / max(staleness_days, 1)))
        return (source_score + access_score + freshness_score, -age_days)

    ranked = sorted(docs, key=score, reverse=True)
    return ranked[:per_type_limit]


def evict_index_cache(index_cache: dict[str, tuple[float, str]], max_size: int) -> None:
    now = asyncio.get_event_loop().time()
    cache_ttl = getattr(settings, "NATIVE_MEMORY_INDEX_CACHE_TTL", 300)
    expired = [uid for uid, (t, _) in index_cache.items() if (now - t) >= cache_ttl]
    for uid in expired:
        del index_cache[uid]
    if len(index_cache) > max_size:
        sorted_entries = sorted(index_cache.items(), key=lambda x: x[1][0])
        to_remove = len(index_cache) - max_size
        for uid, _ in sorted_entries[:to_remove]:
            del index_cache[uid]


async def build_memory_index(backend, user_id: str) -> str:
    cache_ttl = getattr(settings, "NATIVE_MEMORY_INDEX_CACHE_TTL", 300)
    cached = backend._index_cache.get(user_id)
    if cached:
        built_at, cached_str = cached
        if (asyncio.get_event_loop().time() - built_at) < cache_ttl:
            return cached_str

    staleness_days = getattr(settings, "NATIVE_MEMORY_STALENESS_DAYS", 30)
    projection = {
        "title": 1,
        "index_label": 1,
        "summary": 1,
        "memory_id": 1,
        "updated_at": 1,
        "memory_type": 1,
        "source": 1,
        "access_count": 1,
    }
    docs = (
        await backend._collection.find(
            {"user_id": user_id, "source": {"$ne": "session_summary"}},
            projection,
        )
        .sort("updated_at", -1)
        .limit(80)
        .to_list(length=80)
    )

    if not docs:
        return ""

    now = datetime.now(timezone.utc)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for doc in docs:
        grouped.setdefault(str(doc.get("memory_type", "")), []).append(doc)

    type_order = {
        MemoryType.USER.value: 0,
        MemoryType.FEEDBACK.value: 1,
        MemoryType.PROJECT.value: 2,
        MemoryType.REFERENCE.value: 3,
    }

    lines = ["<memory_index>"]
    for mtype in sorted(grouped.keys(), key=lambda key: type_order.get(key, 99)):
        chosen = choose_index_memories(
            grouped[mtype], per_type_limit=5, now=now, staleness_days=staleness_days
        )
        if not chosen:
            continue
        lines.append(f"\n## [{mtype}]")
        for item in chosen:
            age_days = (now - ensure_aware(item["updated_at"])).days
            if age_days == 0:
                age_str = ""
            elif age_days == 1:
                age_str = "yesterday"
            elif age_days <= 7:
                age_str = f"{age_days}d ago"
            elif age_days > staleness_days:
                age_str = f"stale:{age_days}d"
            else:
                age_str = f"{age_days}d ago"
            display_title = item.get("index_label") or item.get("title") or ""
            if not display_title:
                display_title = (item.get("summary") or "")[:30]
            short_id = (item.get("memory_id") or "")[:6]
            if short_id:
                lines.append(
                    f"- {display_title} ({short_id}, {age_str})"
                    if age_str
                    else f"- {display_title} ({short_id})"
                )
            else:
                lines.append(f"- {display_title} ({age_str})" if age_str else f"- {display_title}")

    lines.append("\n</memory_index>")
    result = "\n".join(lines)
    backend._index_cache[user_id] = (asyncio.get_event_loop().time(), result)
    evict_index_cache(backend._index_cache, backend._INDEX_CACHE_MAX_SIZE)
    return result
