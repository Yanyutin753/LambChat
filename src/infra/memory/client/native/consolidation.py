"""Consolidation helpers for the native memory backend."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from src.infra.logging import get_logger
from src.infra.memory.client.native.content import build_content_fields, delete_memory_content
from src.infra.memory.client.native.models import ensure_aware
from src.infra.memory.client.native.summaries import (
    build_index_label,
    llm_enrich_memory,
)
from src.infra.memory.client.types import MemoryType
from src.kernel.config import settings

logger = get_logger(__name__)


async def consolidate_memories(
    backend,
    user_id: str,
    acquire_lock: Callable[[str, str], Awaitable[str]],
    release_lock: Callable[[str, str], Awaitable[None]],
) -> dict[str, Any]:
    instance_id = uuid.uuid4().hex[:8]
    lock_state = await acquire_lock(user_id, instance_id)
    if lock_state != "acquired":
        return {
            "merged": 0,
            "pruned": 0,
            "total_before": 0,
            "skipped": True,
            "reason": "lock_unavailable" if lock_state == "unavailable" else "lock_not_acquired",
        }

    try:
        return await do_consolidate(backend, user_id)
    finally:
        await release_lock(user_id, instance_id)


async def do_consolidate(backend, user_id: str) -> dict[str, Any]:
    all_memories = await backend._collection.find(
        {"user_id": user_id},
        {"embedding": 0},
        sort=[("created_at", 1)],
    ).to_list(length=500)

    if len(all_memories) < 5:
        return {"merged": 0, "pruned": 0, "total_before": len(all_memories)}

    total_before = len(all_memories)
    now = datetime.now(timezone.utc)
    prune_threshold = int(getattr(settings, "NATIVE_MEMORY_PRUNE_THRESHOLD", 90))
    pruned_ids: set[str] = set()

    for m in all_memories:
        source = m.get("source", "")
        updated = ensure_aware(m.get("updated_at", now))
        age_days = (now - updated).days
        access_count = m.get("access_count", 0)

        if source == "manual":
            continue
        if source == "session_summary" and age_days > 7:
            pruned_ids.add(m["memory_id"])
            continue
        if source == "auto_retained":
            if age_days > 180:
                pruned_ids.add(m["memory_id"])
            elif age_days > prune_threshold and access_count <= 1:
                pruned_ids.add(m["memory_id"])
            elif age_days > 30 and access_count == 0:
                pruned_ids.add(m["memory_id"])

    if pruned_ids:
        await backend._collection.delete_many(
            {"user_id": user_id, "memory_id": {"$in": list(pruned_ids)}}
        )

    remaining = [m for m in all_memories if m["memory_id"] not in pruned_ids]
    auto_memories = [m for m in remaining if m.get("source") != "manual"]

    reduced = 0
    for mtype in MemoryType:
        type_memories = [m for m in auto_memories if m.get("memory_type") == mtype.value]
        if len(type_memories) < 3:
            continue
        for batch in _split_batches(type_memories, max_size=30):
            consolidated = await _llm_batch_consolidate(backend, batch, mtype.value)
            if consolidated is None:
                continue
            old_store_keys = [
                m.get("content_store_key")
                for m in batch
                if m.get("content_storage_mode") == "store" and m.get("content_store_key")
            ]
            old_ids = [m["memory_id"] for m in batch]
            # Delete store content first to avoid orphaned files on crash
            if old_store_keys:
                await asyncio.gather(
                    *(delete_memory_content(backend, user_id, key) for key in old_store_keys)
                )
            await backend._collection.delete_many(
                {"user_id": user_id, "memory_id": {"$in": old_ids}}
            )
            if consolidated:
                await backend._collection.insert_many(consolidated)
            reduced += len(batch) - len(consolidated)

    await backend._invalidate_cache(user_id)

    max_per_user = 200
    current_count = await backend._collection.count_documents({"user_id": user_id})
    cap_pruned = 0
    if current_count > max_per_user:
        excess = current_count - max_per_user
        oldest_auto = (
            backend._collection.find(
                {"user_id": user_id, "source": {"$ne": "manual"}},
                {"memory_id": 1, "content_storage_mode": 1, "content_store_key": 1},
            )
            .sort("created_at", 1)
            .limit(excess)
        )
        oldest_docs = await oldest_auto.to_list(length=excess)
        if oldest_docs:
            # Clean up content store entries before deleting MongoDB docs
            store_keys = [
                d["content_store_key"]
                for d in oldest_docs
                if d.get("content_storage_mode") == "store" and d.get("content_store_key")
            ]
            if store_keys:
                await asyncio.gather(
                    *(delete_memory_content(backend, user_id, key) for key in store_keys)
                )
            cap_ids = [d["memory_id"] for d in oldest_docs]
            result = await backend._collection.delete_many(
                {"user_id": user_id, "memory_id": {"$in": cap_ids}}
            )
            cap_pruned = result.deleted_count
            await backend._invalidate_cache(user_id)

    final_count = await backend._collection.count_documents({"user_id": user_id})

    return {
        "merged": reduced,
        "pruned": len(pruned_ids) + cap_pruned,
        "total_before": total_before,
        "total_after": final_count,
    }


def _split_batches(items: list[dict], max_size: int = 30) -> list[list[dict]]:
    return [items[i : i + max_size] for i in range(0, len(items), max_size)]


async def _enrich_item(
    backend, content: str, provided_summary: str, provided_title: str, provided_tags: list
) -> dict[str, Any] | None:
    """Enrich a single consolidated item. Returns None if content is too short."""
    if not content or len(content) < 10:
        return None

    if provided_summary and provided_title and provided_tags:
        summary = provided_summary
        title = provided_title
        tags = [str(t) for t in provided_tags if isinstance(t, str) and len(t) >= 2][:5]
    else:
        enriched = await llm_enrich_memory(backend, content)
        summary = enriched.get("summary") or provided_summary
        title = enriched.get("title") or provided_title
        tags = enriched.get("tags") or []

    return {"summary": summary, "title": title, "tags": tags}


async def _llm_batch_consolidate(backend, memories: list[dict], expected_type: str):
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        model = await backend._get_memory_model()
        items_text = "\n".join(
            f"[{i + 1}] ({m.get('created_at', '').strftime('%Y-%m-%d') if isinstance(m.get('created_at'), datetime) else 'unknown'}) {m['content']}"
            for i, m in enumerate(memories)
        )
        prompt = (
            "You are a memory consolidation assistant. Given a list of memories, "
            "produce a clean, deduplicated, consolidated set.\n\n"
            "Rules:\n"
            "1. MERGE memories about the same topic — combine all unique facts, "
            "prefer newer info when conflicting\n"
            "2. KEEP memories that are unique, specific, and still relevant\n"
            "3. DELETE (omit from output) memories that are:\n"
            "   - Duplicates or near-duplicates of another memory\n"
            "   - Too vague or generic to be useful\n"
            "   - Outdated (old project status that has since changed)\n"
            "   - Contradicted by a newer memory\n"
            "   - Shorter than 15 characters\n"
            "4. Each output memory should be ONE focused fact or observation\n"
            "5. When merging, preserve all unique details from all source memories\n"
            '6. Keep memory type as: "{type}"\n\n'
            'Return ONLY a JSON array: [{{"content": "...", "summary": "...", "title": "...", "tags": ["...", "..."]}}]\n'
            "title should be max 25 chars, a short label for this memory.\n"
            "tags should be 3-5 meaningful keywords.\n"
            "Memories to delete should simply be OMITTED from the array.\n\n"
            f"Input memories (oldest first):\n{items_text}"
        ).format(type=expected_type)

        response = await model.ainvoke(
            [
                SystemMessage(
                    content="You consolidate memories. Output only JSON. Be conservative — when in doubt, keep it."
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
                return None
        text = str(text).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        parsed = json.loads(text.strip())
        if not isinstance(parsed, list) or (not parsed and len(memories) >= 3):
            return None

        now = datetime.now(timezone.utc)
        # Enrich items concurrently
        enrich_coros = [
            _enrich_item(
                backend,
                item.get("content", "").strip(),
                item.get("summary", "").strip(),
                item.get("title", "").strip(),
                item.get("tags") or [],
            )
            for item in parsed
        ]
        enrich_results = await asyncio.gather(*enrich_coros)

        docs = []
        for item, meta in zip(parsed, enrich_results):
            if meta is None:
                continue
            content = item.get("content", "").strip()
            # Build content fields and embed concurrently across items
            memory_id = uuid.uuid4().hex
            content_fields, embedding = await asyncio.gather(
                build_content_fields(backend, memories[0]["user_id"], memory_id, content),
                backend._maybe_embed(content),
            )
            docs.append(
                {
                    "memory_id": memory_id,
                    "user_id": memories[0]["user_id"],
                    "summary": meta["summary"][:100],
                    "title": meta["title"][:25],
                    "index_label": build_index_label(meta["title"], meta["summary"], content),
                    "memory_type": expected_type,
                    "context": "consolidated",
                    "tags": meta["tags"],
                    "source": "consolidated",
                    "embedding": embedding,
                    "created_at": now,
                    "updated_at": now,
                    "accessed_at": now,
                    "access_count": 0,
                    **content_fields,
                }
            )
        return docs if docs else None
    except Exception as e:
        logger.warning(
            "[NativeMemory] Batch consolidation failed (batch of %d): %s", len(memories), e
        )
        return None
