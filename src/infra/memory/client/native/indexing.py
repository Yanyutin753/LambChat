"""Indexing helpers for the native memory backend."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from src.infra.memory.client.types import MemoryType
from src.infra.utils.datetime import ensure_utc, utc_now
from src.kernel.config import settings


def choose_index_memories(
    docs: list[dict[str, Any]],
    per_type_limit: int,
    now: datetime,
    staleness_days: int,
) -> list[dict[str, Any]]:
    def score(doc: dict[str, Any]) -> tuple[float, float, str]:
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
        age_days = (now - ensure_utc(doc.get("updated_at", now))).days
        freshness_score = max(0.0, 2.0 - (age_days / max(staleness_days, 1)))
        # Access statistics are mutable on every recall and must not affect the
        # system-prompt prefix. Updated time is the stable memory revision.
        return (source_score + freshness_score, -age_days, str(doc.get("memory_id", "")))

    ranked = sorted(docs, key=score, reverse=True)
    return ranked[:per_type_limit]


def evict_index_cache(index_cache: dict[str, tuple[float, str]], max_size: int) -> None:
    now = time.monotonic()
    cache_ttl = getattr(settings, "NATIVE_MEMORY_INDEX_CACHE_TTL", 3600)
    expired = [uid for uid, (t, _) in index_cache.items() if (now - t) >= cache_ttl]
    for uid in expired:
        del index_cache[uid]
    if len(index_cache) > max_size:
        sorted_entries = sorted(index_cache.items(), key=lambda x: x[1][0])
        to_remove = len(index_cache) - max_size
        for uid, _ in sorted_entries[:to_remove]:
            del index_cache[uid]


async def build_memory_index(backend, user_id: str) -> str:
    cache_ttl = getattr(settings, "NATIVE_MEMORY_INDEX_CACHE_TTL", 3600)
    cached = backend._index_cache.get(user_id)
    if cached:
        built_at, cached_str = cached
        if (time.monotonic() - built_at) < cache_ttl:
            return cached_str

    staleness_days = getattr(settings, "NATIVE_MEMORY_STALENESS_DAYS", 30)
    projection = {
        "title": 1,
        "index_label": 1,
        "summary": 1,
        "updated_at": 1,
        "memory_type": 1,
        "source": 1,
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

    now = utc_now()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for doc in docs:
        grouped.setdefault(str(doc.get("memory_type", "")), []).append(doc)

    type_order = {
        MemoryType.USER.value: 0,
        MemoryType.FEEDBACK.value: 1,
        MemoryType.PROJECT.value: 2,
        MemoryType.REFERENCE.value: 3,
    }

    type_labels = {
        MemoryType.USER.value: "User",
        MemoryType.FEEDBACK.value: "Feedback",
        MemoryType.PROJECT.value: "Project",
        MemoryType.REFERENCE.value: "Reference",
    }

    lines = ["<memory_index>", "# Cross-Session Memory Index"]
    for mtype in sorted(grouped.keys(), key=lambda key: type_order.get(key, 99)):
        chosen = choose_index_memories(
            grouped[mtype], per_type_limit=5, now=now, staleness_days=staleness_days
        )
        if not chosen:
            continue
        lines.append(f"\n## {type_labels.get(mtype, mtype.title())}")
        for item in chosen:
            display_title = item.get("index_label") or item.get("title") or ""
            if not display_title:
                display_title = (item.get("summary") or "")[:30]
            updated_at = ensure_utc(item.get("updated_at", now)).date().isoformat()
            summary = str(item.get("summary") or display_title).strip()
            lines.extend(
                (
                    f"\n- **{display_title}**",
                    f"  - Updated: {updated_at}",
                    f"  - Summary: {summary}",
                )
            )

    lines.append("\n</memory_index>")
    result = "\n".join(lines)
    backend._index_cache[user_id] = (time.monotonic(), result)
    evict_index_cache(backend._index_cache, backend._INDEX_CACHE_MAX_SIZE)
    return result
