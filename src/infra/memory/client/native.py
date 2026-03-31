"""
Native Memory Backend — MongoDB-backed, zero external dependencies.

Self-hosted memory system using MongoDB for storage with hybrid search
(text + optional vector). Inspired by Claude Code's memory architecture.
"""

import asyncio
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from src.infra.logging import get_logger
from src.infra.memory.client.base import MemoryBackend
from src.infra.memory.client.types import (
    EXCLUDED_CONTENT_PATTERNS,
    HIGH_SIGNAL_PATTERNS,
    MemoryType,
)
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)

COLLECTION_NAME = "native_memories"

# ---------------------------------------------------------------------------
# Stop words for tag extraction
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    "the a an is are was were be been being have has had do does did will would "
    "could should may might can shall to of in for on with at by from as into "
    "through and but or not this that it its i my me you your we our they their "
    "he she his her also just very so if then when where what how which who "
    "there here about up out all some any no each every both few more most "
    "other some such only own same than too most".split()
)


def _ensure_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC) if it is naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ============================================================================
# NativeMemoryBackend
# ============================================================================


class NativeMemoryBackend(MemoryBackend):
    """MongoDB-native memory backend. No external API dependencies."""

    # Maximum entries in the per-instance index cache
    _INDEX_CACHE_MAX_SIZE: int = 1000

    def __init__(self):
        self._collection: Any = None
        self._embedding_fn: Optional[Callable] = None
        self._httpx_client: Any = None  # keep ref for proper cleanup
        # In-memory cache for memory index: {user_id: (built_at, index_str)}
        self._index_cache: dict[str, tuple[float, str]] = {}

    @property
    def name(self) -> str:
        return "native"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _invalidate_cache(self, user_id: str) -> None:
        """Invalidate local index cache and publish invalidation to other instances."""
        self._index_cache.pop(user_id, None)
        try:
            from src.infra.memory.distributed import publish_memory_invalidation

            await publish_memory_invalidation(user_id)
        except Exception:
            pass  # non-critical: other instances will eventually refresh via TTL

    async def initialize(self) -> None:
        """Ensure indexes exist; set up optional embedding function."""
        self._ensure_collection()
        await self._create_indexes()
        self._setup_embedding_fn()

    async def close(self) -> None:
        if self._httpx_client is not None:
            try:
                await self._httpx_client.aclose()
            except Exception:
                pass
            self._httpx_client = None
        self._collection = None
        self._embedding_fn = None
        self._index_cache.clear()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def retain(
        self,
        user_id: str,
        content: str,
        context: Optional[str] = None,
    ) -> dict[str, Any]:
        memory_type = self._classify_type(content, context)
        tags = self._extract_tags(content)
        summary = self._build_summary(content)
        memory_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)

        doc = {
            "memory_id": memory_id,
            "user_id": user_id,
            "content": content[:5000],
            "summary": summary,
            "memory_type": memory_type,
            "context": context,
            "tags": tags,
            "source": "manual",
            "embedding": await self._maybe_embed(content),
            "created_at": now,
            "updated_at": now,
            "accessed_at": now,
            "access_count": 0,
        }

        await self._collection.insert_one(doc)
        # Invalidate index cache (local + distributed)
        await self._invalidate_cache(user_id)

        return {
            "success": True,
            "memory_id": memory_id,
            "memory_type": memory_type,
            "message": "Memory stored successfully",
        }

    async def recall(
        self,
        user_id: str,
        query: str,
        max_results: int = 5,
        memory_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        text_results = await self._text_search(user_id, query, max_results * 2, memory_types)

        vector_results: list[dict] = []
        if self._embedding_fn:
            vector_results = await self._vector_search(
                user_id, query, max_results * 2, memory_types
            )

        memories = self._rrf_merge(text_results, vector_results, max_results * 2)

        # LLM re-ranking: filter for contextual relevance
        if memories and len(memories) > max_results:
            memories = await self._llm_rerank(user_id, query, memories, max_results)

        if memories:
            memories = memories[:max_results]
            await self._update_access_stats([m["memory_id"] for m in memories])

        return {
            "success": True,
            "query": query,
            "memories": memories,
            "search_mode": "hybrid" if self._embedding_fn else "text",
        }

    async def delete(
        self,
        user_id: str,
        memory_id: str,
    ) -> dict[str, Any]:
        result = await self._collection.delete_one({"user_id": user_id, "memory_id": memory_id})
        if result.deleted_count > 0:
            await self._invalidate_cache(user_id)
            return {"success": True, "message": f"Memory {memory_id} deleted"}
        return {"success": False, "error": "Memory not found"}

    # ------------------------------------------------------------------
    # Session summary (for context survival)
    # ------------------------------------------------------------------

    async def store_session_summary(
        self, user_id: str, session_id: str, summary: str
    ) -> None:
        """Store or update a session-level summary as a project-type memory.

        This captures the key state of a conversation so it can be recovered
        after context compaction or in future sessions.
        """
        if not summary or len(summary.strip()) < 20:
            return

        summary = summary.strip()

        # Upsert: replace existing summary for this session
        existing = await self._collection.find_one(
            {"user_id": user_id, "context": f"session:{session_id}"},
            {"memory_id": 1},
        )
        now = datetime.now(timezone.utc)
        summary_text = f"[Session {session_id[:8]}] {summary}"

        if existing:
            await self._collection.update_one(
                {"memory_id": existing["memory_id"]},
                {
                    "$set": {
                        "content": summary_text[:5000],
                        "summary": summary[:100],
                        "updated_at": now,
                    }
                },
            )
        else:
            await self._collection.insert_one(
                {
                    "memory_id": uuid.uuid4().hex,
                    "user_id": user_id,
                    "content": summary_text[:5000],
                    "summary": summary[:100],
                    "memory_type": "project",
                    "context": f"session:{session_id}",
                    "tags": self._extract_tags(summary),
                    "source": "session_summary",
                    "embedding": await self._maybe_embed(summary_text),
                    "created_at": now,
                    "updated_at": now,
                    "accessed_at": now,
                    "access_count": 0,
                }
            )
        await self._invalidate_cache(user_id)
        logger.debug("[NativeMemory] Stored session summary for %s", session_id[:8])

    # ------------------------------------------------------------------
    # Auto-retain (smart filtering)
    # ------------------------------------------------------------------

    async def auto_retain(
        self,
        user_id: str,
        conversation_summary: str,
        context: Optional[str] = None,
    ) -> None:
        # Try LLM-based extraction first, fall back to rule-based
        memories = await self._llm_extract_memories(user_id, conversation_summary)
        if not memories:
            memories = self._smart_filter_and_classify(conversation_summary)
        if not memories:
            return

        # Deduplicate against existing memories
        memories = await self._deduplicate_against_existing(user_id, memories)
        if not memories:
            return

        # Daily rate limit
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_count = await self._collection.count_documents(
            {
                "user_id": user_id,
                "source": "auto_retained",
                "created_at": {"$gte": today},
            }
        )
        max_daily = getattr(settings, "NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY", 20)
        remaining = max_daily - daily_count
        if remaining <= 0:
            return

        now = datetime.now(timezone.utc)
        docs = []
        for mem in memories[: min(len(memories), remaining, 3)]:
            doc = {
                "memory_id": uuid.uuid4().hex,
                "user_id": user_id,
                "content": mem["content"][:5000],
                "summary": mem["summary"],
                "memory_type": mem["memory_type"],
                "context": context or "auto_retained",
                "tags": mem.get("tags", []),
                "source": "auto_retained",
                "embedding": await self._maybe_embed(mem["content"]),
                "created_at": now,
                "updated_at": now,
                "accessed_at": now,
                "access_count": 0,
            }
            docs.append(doc)

        if docs:
            await self._collection.insert_many(docs)
            await self._invalidate_cache(user_id)
            logger.debug(f"[NativeMemory] Auto-retained {len(docs)} memories for {user_id}")

    # ------------------------------------------------------------------
    # Memory consolidation
    # ------------------------------------------------------------------

    async def consolidate_memories(self, user_id: str) -> dict[str, Any]:
        """Consolidate memories: merge near-duplicates, prune stale/never-accessed.

        Uses LLM for semantic merging of overlapping memories, then removes
        memories that were never accessed and are older than 90 days.
        Protected by a distributed lock to prevent concurrent consolidation
        across instances.

        Returns stats about what was done.
        """
        # Acquire distributed lock
        import uuid as _uuid

        instance_id = _uuid.uuid4().hex[:8]
        try:
            from src.infra.memory.distributed import (
                acquire_consolidation_lock,
                release_consolidation_lock,
            )

            locked = await acquire_consolidation_lock(user_id, instance_id)
            if not locked:
                logger.info("[NativeMemory] Consolidation already in progress for %s, skipping", user_id)
                return {"merged": 0, "pruned": 0, "total_before": 0, "skipped": True}
        except Exception:
            locked = False  # fallback: proceed without distributed lock

        try:
            return await self._do_consolidate(user_id, instance_id, staleness_days, prune_threshold)
        finally:
            if locked:
                try:
                    from src.infra.memory.distributed import release_consolidation_lock

                    await release_consolidation_lock(user_id, instance_id)
                except Exception:
                    pass

    async def _do_consolidate(
        self,
        user_id: str,
        instance_id: str,
        staleness_days: int,
        prune_threshold: int,
    ) -> dict[str, Any]:
        """Internal consolidation implementation (called after lock acquired)."""

        # Fetch all memories for this user
        cursor = self._collection.find(
            {"user_id": user_id},
            sort=[("memory_type", 1), ("updated_at", -1)],
        )
        all_memories = await cursor.to_list(length=200)

        if len(all_memories) < 5:
            return {"merged": 0, "pruned": 0, "total_before": len(all_memories)}

        # Phase 1: Prune stale, never-accessed memories
        now = datetime.utcnow()
        pruned_ids = []
        for m in all_memories:
            updated = _ensure_aware(m.get("updated_at", now))
            age_days = (now - updated).days
            if age_days > prune_threshold and m.get("access_count", 0) == 0:
                pruned_ids.append(m["memory_id"])

        if pruned_ids:
            await self._collection.delete_many(
                {"user_id": user_id, "memory_id": {"$in": pruned_ids}}
            )

        # Phase 2: LLM-based merge of similar memories per type
        merged_count = 0
        for mtype in MemoryType:
            type_memories = [
                m for m in all_memories
                if m.get("memory_type") == mtype.value and m["memory_id"] not in pruned_ids
            ]
            if len(type_memories) < 2:
                continue

            # Group by tag overlap for candidate merging
            groups: dict[str, list] = {}
            for m in type_memories:
                key_tags = frozenset(m.get("tags", [])[:3])
                if not key_tags:
                    continue
                found = False
                for existing_key in groups:
                    if len(key_tags & existing_key) >= 2:
                        groups[existing_key].append(m)
                        found = True
                        break
                if not found:
                    groups[key_tags] = [m]

            for group_key, group in groups.items():
                if len(group) < 2:
                    continue

                try:
                    merged = await self._llm_merge_memories(group)
                    if merged:
                        # Delete old memories, insert merged one
                        old_ids = [m["memory_id"] for m in group]
                        await self._collection.delete_many(
                            {"user_id": user_id, "memory_id": {"$in": old_ids}}
                        )
                        await self._collection.insert_one(merged)
                        merged_count += 1
                except Exception as e:
                    logger.debug("[NativeMemory] Merge failed for group: %s", e)

        await self._invalidate_cache(user_id)

        total_after = len(all_memories) - len(pruned_ids) - merged_count
        result = {
            "merged": merged_count,
            "pruned": len(pruned_ids),
            "total_before": len(all_memories),
            "total_after": total_after,
        }
        logger.info(
            "[NativeMemory] Consolidation for %s: merged=%d, pruned=%d, %d -> %d",
            user_id, merged_count, len(pruned_ids),
            result["total_before"], result["total_after"],
        )
        return result

    async def _llm_rerank(
        self, user_id: str, query: str, candidates: list[dict], max_results: int
    ) -> list[dict]:
        """Use LLM to re-rank candidate memories by contextual relevance."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from src.infra.llm.client import LLMClient

            model = LLMClient.get_model(
                model=getattr(settings, "SESSION_TITLE_MODEL", None) or getattr(settings, "LLM_MODEL", None),
                api_base=getattr(settings, "SESSION_TITLE_API_BASE", "") or "",
                api_key=getattr(settings, "SESSION_TITLE_API_KEY", "") or "",
                temperature=0.1,
                max_tokens=200,
            )

            items_text = "\n".join(
                f"[{i}] {m['summary']}" for i, m in enumerate(candidates)
            )

            prompt = (
                f"Query: {query}\n\n"
                f"Ranked by relevance:\n{items_text}\n\n"
                f"Return a JSON array of up to {max_results} index numbers (most relevant first). "
                "Be strict — only include memories that are genuinely useful for this query."
            )

            response = await model.ainvoke(
                [SystemMessage(content="You rank memory relevance. Output only a JSON array of numbers, e.g. [0, 3, 1]."), HumanMessage(content=prompt)],
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
            logger.debug("[NativeMemory] LLM rerank failed, using RRF order: %s", e)
            return candidates[:max_results]

    async def _llm_merge_memories(self, memories: list[dict]) -> Optional[dict]:
        """Use LLM to merge overlapping memories into one consolidated memory."""
        if len(memories) > 5:
            memories = memories[:5]

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from src.infra.llm.client import LLMClient

            model = LLMClient.get_model(
                model=getattr(settings, "SESSION_TITLE_MODEL", None) or getattr(settings, "LLM_MODEL", None),
                api_base=getattr(settings, "SESSION_TITLE_API_BASE", "") or "",
                api_key=getattr(settings, "SESSION_TITLE_API_KEY", "") or "",
                temperature=0.1,
                max_tokens=500,
            )

            items_text = "\n".join(
                f"[{i+1}] {m['content']}" for i, m in enumerate(memories)
            )

            prompt = (
                "These memories are overlapping or related. Merge them into a single "
                "consolidated memory that captures all unique information.\n\n"
                f"Memories to merge:\n{items_text}\n\n"
                "Return JSON: {\"content\": \"merged content\", \"type\": \"memory_type\", "
                "\"summary\": \"concise summary\"}\n"
                "Keep the most recent/relevant details. If memories contradict, "
                "prefer the newer one."
            )

            response = await model.ainvoke(
                [SystemMessage(content="You are a memory consolidation assistant. Output only JSON."), HumanMessage(content=prompt)],
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
            text = text.strip()

            parsed = json.loads(text)
            content = parsed.get("content", "").strip()
            if not content:
                return None

            mem_type = parsed.get("type", memories[0].get("memory_type", "user"))
            summary = parsed.get("summary", self._build_summary(content))

            now = datetime.now(timezone.utc)
            return {
                "memory_id": uuid.uuid4().hex,
                "user_id": memories[0]["user_id"],
                "content": content[:5000],
                "summary": summary[:100],
                "memory_type": mem_type,
                "context": "consolidated",
                "tags": self._extract_tags(content),
                "source": "auto_retained",
                "embedding": await self._maybe_embed(content),
                "created_at": now,
                "updated_at": now,
                "accessed_at": now,
                "access_count": 0,
            }
        except Exception as e:
            logger.debug("[NativeMemory] LLM merge failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Memory index (for system prompt injection)
    # ------------------------------------------------------------------

    async def build_memory_index(self, user_id: str) -> str:
        """
        Build lightweight memory index string for system prompt.
        Grouped by type, capped at 10 per type, with staleness warnings.
        """
        # Check cache (5 min TTL)
        cache_ttl = getattr(settings, "NATIVE_MEMORY_INDEX_CACHE_TTL", 300)
        cached = self._index_cache.get(user_id)
        if cached:
            built_at, cached_str = cached
            if (asyncio.get_event_loop().time() - built_at) < cache_ttl:
                return cached_str

        staleness_days = getattr(settings, "NATIVE_MEMORY_STALENESS_DAYS", 30)

        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$sort": {"updated_at": -1}},
            {
                "$group": {
                    "_id": "$memory_type",
                    "items": {
                        "$push": {
                            "summary": "$summary",
                            "updated_at": "$updated_at",
                        }
                    },
                }
            },
            {
                "$project": {
                    "items": {"$slice": ["$items", 10]},
                }
            },
        ]

        try:
            cursor = self._collection.aggregate(pipeline)
            groups = await cursor.to_list(length=4)
        except Exception as e:
            logger.warning(f"[NativeMemory] Failed to build index: {e}")
            return ""

        if not groups:
            return ""

        now = datetime.now(timezone.utc)
        type_order = {
            MemoryType.USER: 0,
            MemoryType.FEEDBACK: 1,
            MemoryType.PROJECT: 2,
            MemoryType.REFERENCE: 3,
        }
        groups.sort(key=lambda g: type_order.get(g["_id"], 99))

        lines = ["<memory_index>"]
        for group in groups:
            mtype = group["_id"]
            lines.append(f"\n## [{mtype}]")
            for item in group["items"]:
                age_days = (now - _ensure_aware(item["updated_at"])).days
                staleness = f" (stale: {age_days}d old)" if age_days > staleness_days else ""
                lines.append(f"- {item['summary']}{staleness}")

        lines.append("\n</memory_index>")
        result = "\n".join(lines)

        # Cache it
        self._index_cache[user_id] = (asyncio.get_event_loop().time(), result)
        # Evict oldest entries if cache exceeds max size
        if len(self._index_cache) > self._INDEX_CACHE_MAX_SIZE:
            self._evict_index_cache()
        return result

    def _evict_index_cache(self) -> None:
        """Remove expired and oldest entries to keep cache bounded."""
        now = asyncio.get_event_loop().time()
        cache_ttl = getattr(settings, "NATIVE_MEMORY_INDEX_CACHE_TTL", 300)
        # Remove expired entries first
        expired = [uid for uid, (t, _) in self._index_cache.items() if (now - t) >= cache_ttl]
        for uid in expired:
            del self._index_cache[uid]
        # If still over limit, remove oldest entries
        if len(self._index_cache) > self._INDEX_CACHE_MAX_SIZE:
            sorted_entries = sorted(self._index_cache.items(), key=lambda x: x[1][0])
            to_remove = len(self._index_cache) - self._INDEX_CACHE_MAX_SIZE
            for uid, _ in sorted_entries[:to_remove]:
                del self._index_cache[uid]

    # ------------------------------------------------------------------
    # Search implementations
    # ------------------------------------------------------------------

    async def _text_search(
        self,
        user_id: str,
        query: str,
        limit: int,
        memory_types: Optional[list[str]],
    ) -> list[dict]:
        base: dict[str, Any] = {"user_id": user_id}
        if memory_types:
            base["memory_type"] = {"$in": memory_types}
        base["$text"] = {"$search": query}

        try:
            cursor = (
                self._collection.find(
                    base,
                    {"score": {"$meta": "textScore"}},
                )
                .sort([("score", {"$meta": "textScore"})])
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
        except Exception:
            # Fallback: text index might not exist yet, do keyword match
            logger.debug("[NativeMemory] Text search failed, falling back to keyword match")
            docs = await self._keyword_fallback(user_id, query, limit, memory_types)

        return [self._format_memory(doc, doc.get("score", 0)) for doc in docs]

    async def _keyword_fallback(
        self,
        user_id: str,
        query: str,
        limit: int,
        memory_types: Optional[list[str]],
    ) -> list[dict]:
        """Simple keyword matching fallback when text index is unavailable."""
        words = [w for w in query.lower().split() if len(w) >= 2 and w not in _STOPWORDS][:5]
        if not words:
            return []

        base: dict[str, Any] = {"user_id": user_id}
        if memory_types:
            base["memory_type"] = {"$in": memory_types}
        base["$or"] = [{"content": {"$regex": re.escape(w), "$options": "i"}} for w in words]

        cursor = self._collection.find(base).sort("updated_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def _vector_search(
        self,
        user_id: str,
        query: str,
        limit: int,
        memory_types: Optional[list[str]],
    ) -> list[dict]:
        query_vec = await self._maybe_embed(query)
        if not query_vec:
            return []

        base: dict[str, Any] = {
            "user_id": user_id,
            "embedding": {"$exists": True, "$ne": None},
        }
        if memory_types:
            base["memory_type"] = {"$in": memory_types}

        # Try Atlas Vector Search
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
            cursor = self._collection.aggregate(pipeline)
            docs = await cursor.to_list(length=limit)
            return [self._format_memory(doc, doc.get("score", 1.0)) for doc in docs]
        except Exception:
            pass

        # Fallback: Python cosine similarity (only project needed fields)
        logger.debug("[NativeMemory] Atlas $vectorSearch unavailable, using Python cosine fallback")
        projection = {"memory_id": 1, "content": 1, "summary": 1, "memory_type": 1,
                      "source": 1, "created_at": 1, "updated_at": 1, "embedding": 1}
        cursor = self._collection.find(base, projection).limit(200)
        docs = await cursor.to_list(length=200)
        scored = []
        for d in docs:
            emb = d.get("embedding")
            if emb:
                sim = _cosine_similarity(query_vec, emb)
                scored.append((sim, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._format_memory(d, sim) for sim, d in scored[:limit]]

    # ------------------------------------------------------------------
    # Type classification
    # ------------------------------------------------------------------

    def _classify_type(self, content: str, context: Optional[str] = None) -> str:
        """Rule-based memory type classification."""
        content_lower = content.lower()

        # If context explicitly specifies a type, use it
        if context:
            ctx_lower = context.lower()
            for mt in MemoryType:
                if mt.value in ctx_lower:
                    return mt.value

        # Score each type by matching high-signal patterns
        scores: dict[str, float] = {}
        for mtype, patterns in HIGH_SIGNAL_PATTERNS.items():
            score = 0
            for pat in patterns:
                if re.search(pat, content_lower):
                    score += 1
            if score > 0:
                scores[mtype] = score

        if scores:
            # Tie-break: prefer first match in priority order
            max_score = max(scores.values())
            for mt in [
                MemoryType.FEEDBACK,
                MemoryType.REFERENCE,
                MemoryType.PROJECT,
                MemoryType.USER,
            ]:
                if mt.value in scores and scores[mt.value] == max_score:
                    return mt.value

        return MemoryType.USER

    # ------------------------------------------------------------------
    # Smart auto-retain filtering
    # ------------------------------------------------------------------

    def _smart_filter_and_classify(self, summary: str) -> list[dict]:
        """Multi-layer filter: noise, dedup, classify."""
        stripped = summary.strip()

        # Layer 1: length filter
        if len(stripped) < 20:
            return []

        # Layer 2: generic pattern filter
        first_line = stripped.split("\n")[0].lower()
        generic_starts = (
            "hello",
            "hi ",
            "hey",
            "thanks",
            "thank you",
            "ok",
            "okay",
            "sure",
            "yes",
            "no",
            "bye",
            "great",
        )
        if any(first_line.startswith(p) for p in generic_starts) and len(stripped) < 100:
            return []

        # Layer 3: noise filter (code patterns, file paths, etc.)
        for pat in EXCLUDED_CONTENT_PATTERNS:
            if re.search(pat, stripped, re.IGNORECASE):
                return []

        # Layer 4: signal matching — only retain if high-signal pattern matched
        has_signal = False
        for patterns in HIGH_SIGNAL_PATTERNS.values():
            for pat in patterns:
                if re.search(pat, stripped, re.IGNORECASE):
                    has_signal = True
                    break
            if has_signal:
                break

        if not has_signal:
            return []

        # Split into chunks (paragraphs)
        chunks = [p.strip() for p in stripped.split("\n\n") if len(p.strip()) > 30]
        if not chunks:
            chunks = [stripped]

        memories = []
        for chunk in chunks:
            mtype = self._classify_type(chunk)
            memories.append(
                {
                    "content": chunk,
                    "summary": self._build_summary(chunk),
                    "memory_type": mtype,
                    "tags": self._extract_tags(chunk),
                }
            )

        return memories[:3]

    async def _llm_extract_memories(
        self, user_id: str, conversation: str
    ) -> list[dict]:
        """Use a lightweight LLM call to extract structured memories from a conversation turn.

        Falls back gracefully on any error (returns empty list).
        """
        if len(conversation.strip()) < 30:
            return []

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from src.infra.llm.client import LLMClient

            model = LLMClient.get_model(
                model=getattr(settings, "SESSION_TITLE_MODEL", None) or getattr(settings, "LLM_MODEL", None),
                api_base=getattr(settings, "SESSION_TITLE_API_BASE", "") or "",
                api_key=getattr(settings, "SESSION_TITLE_API_KEY", "") or "",
                temperature=0.1,
                max_tokens=500,
            )

            # Pre-inject existing memory index for dedup guidance
            existing_index = ""
            try:
                cached = self._index_cache.get(user_id)
                if cached and (asyncio.get_event_loop().time() - cached[0]) < 300:
                    existing_index = cached[1]
            except Exception:
                pass

            existing_hint = ""
            if existing_index:
                existing_hint = f"\n\nExisting memories (do NOT duplicate):\n{existing_index}"

            prompt = (
                "Analyze this conversation turn and extract memories worth remembering "
                "across sessions. Return a JSON array of objects with 'content', 'type' "
                "(one of: user, feedback, project, reference), and 'summary' (max 80 chars).\n\n"
                "Rules:\n"
                "- Only extract non-obvious, durable information (preferences, decisions, context)\n"
                "- Do NOT extract code, file paths, git commands, error traces\n"
                "- Do NOT extract greetings, thanks, or trivial chitchat\n"
                "- Include *why* for feedback type memories\n"
                "- Convert relative dates to absolute dates for project type\n"
                "- Return empty array [] if nothing is worth remembering\n"
                "- Maximum 3 memories per turn"
                f"{existing_hint}\n\n"
                "Conversation:\n"
                f"{conversation[:2000]}\n\n"
                'Return ONLY valid JSON: [{"content": "...", "type": "user", "summary": "..."}]'
            )

            response = await model.ainvoke(
                [SystemMessage(content="You are a memory extraction assistant. Output only JSON."), HumanMessage(content=prompt)],
            )

            # Extract text from response
            text = response.content
            if isinstance(text, list):
                for item in text:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        break
                else:
                    return []
            text = str(text).strip()

            # Strip markdown code fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            parsed = json.loads(text)
            if not isinstance(parsed, list):
                return []

            memories = []
            for item in parsed[:3]:
                content = item.get("content", "").strip()
                mem_type = item.get("type", "user")
                summary = item.get("summary", "")
                if not content or len(content) < 15:
                    continue
                if mem_type not in ("user", "feedback", "project", "reference"):
                    mem_type = "user"
                if not summary:
                    summary = self._build_summary(content)
                memories.append(
                    {
                        "content": content[:5000],
                        "summary": summary[:100],
                        "memory_type": mem_type,
                        "tags": self._extract_tags(content),
                    }
                )
            if memories:
                logger.debug("[NativeMemory] LLM extracted %d memories", len(memories))
            return memories

        except Exception as e:
            logger.debug("[NativeMemory] LLM extraction failed, falling back to rules: %s", e)
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _deduplicate_against_existing(
        self, user_id: str, candidates: list[dict]
    ) -> list[dict]:
        """Filter out candidates that are too similar to existing memories."""
        if not candidates:
            return candidates

        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        try:
            # Fetch recent summaries for this user
            recent = await self._collection.find(
                {
                    "user_id": user_id,
                    "updated_at": {"$gte": seven_days_ago},
                },
                {"summary": 1},
            ).to_list(length=50)
        except Exception:
            return candidates  # on DB error, keep all candidates

        recent_summaries = [doc["summary"] for doc in recent if doc.get("summary")]

        if not recent_summaries:
            return candidates

        filtered = []
        for mem in candidates:
            summary = mem.get("summary", "")
            if not summary:
                filtered.append(mem)
                continue
            if any(self._word_similarity(summary, rs) > 0.7 for rs in recent_summaries):
                continue  # too similar, skip
            filtered.append(mem)

        return filtered

    @staticmethod
    def _word_similarity(a: str, b: str) -> float:
        """Jaccard similarity on word sets."""
        set_a = set(a.lower().split())
        set_b = set(b.lower().split())
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    def _extract_tags(self, content: str) -> list[str]:
        words = content.lower().split()
        tags: list[str] = []
        seen: set[str] = set()
        for w in words:
            clean = w.strip(".,!?;:()[]{}\"'").lower()
            if len(clean) >= 3 and clean not in _STOPWORDS and clean not in seen:
                tags.append(clean)
                seen.add(clean)
        return tags[:5]

    def _build_summary(self, content: str, max_len: int = 100) -> str:
        # Take first sentence or truncate
        flat = content.replace("\n", " ").strip()
        sentences = flat.split(". ")
        if sentences and len(sentences[0]) <= max_len:
            return sentences[0].strip()
        if len(flat) > max_len:
            return flat[:max_len].strip() + "..."
        return flat

    @staticmethod
    def _format_memory(doc: dict, score: float) -> dict:
        now = datetime.now(timezone.utc)
        staleness_days = (now - _ensure_aware(doc["updated_at"])).days
        staleness_days_cfg = getattr(settings, "NATIVE_MEMORY_STALENESS_DAYS", 30)

        result: dict[str, Any] = {
            "memory_id": doc["memory_id"],
            "text": doc["content"],
            "summary": doc["summary"],
            "type": doc["memory_type"],
            "source": doc.get("source", "manual"),
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

    async def _update_access_stats(self, memory_ids: list[str]) -> None:
        await self._collection.update_many(
            {"memory_id": {"$in": memory_ids}},
            {
                "$set": {"accessed_at": datetime.now(timezone.utc)},
                "$inc": {"access_count": 1},
            },
        )

    async def _maybe_embed(self, text: str) -> Optional[list[float]]:
        if not self._embedding_fn:
            return None
        try:
            result = self._embedding_fn(text)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            logger.warning(f"[NativeMemory] Embedding failed: {e}")
            return None

    @staticmethod
    def _rrf_merge(
        text_results: list[dict],
        vector_results: list[dict],
        max_results: int,
        k: int = 60,
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

    # ------------------------------------------------------------------
    # MongoDB setup
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        client = get_mongo_client()
        db = client[settings.MONGODB_DB]
        self._collection = db[COLLECTION_NAME]

    async def _create_indexes(self) -> None:
        sync_col = get_mongo_client().delegate[settings.MONGODB_DB][COLLECTION_NAME]
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._create_indexes_sync, sync_col)

    @staticmethod
    def _create_indexes_sync(col: Any) -> None:
        col.create_index(
            [("user_id", 1), ("memory_type", 1), ("created_at", -1)],
            name="native_mem_user_type_idx",
        )
        col.create_index(
            [("memory_id", 1)],
            name="native_mem_id_idx",
            unique=True,
        )
        col.create_index(
            [("user_id", 1), ("updated_at", -1), ("access_count", -1)],
            name="native_mem_recency_idx",
        )
        try:
            col.create_index(
                [("user_id", 1), ("content", "text"), ("summary", "text"), ("tags", "text")],
                name="native_mem_text_idx",
                weights={"content": 10, "summary": 5, "tags": 2},
            )
        except Exception as e:
            # Text index creation can fail on existing collections with conflicts
            logger.warning(f"[NativeMemory] Text index creation skipped: {e}")

    def _setup_embedding_fn(self) -> None:
        """Set up optional embedding function from config."""
        api_base = getattr(settings, "NATIVE_MEMORY_EMBEDDING_API_BASE", "")
        api_key = getattr(settings, "NATIVE_MEMORY_EMBEDDING_API_KEY", "")
        model = getattr(settings, "NATIVE_MEMORY_EMBEDDING_MODEL", "text-embedding-3-small")

        if not api_base or not api_key:
            logger.debug("[NativeMemory] No embedding API configured, text-only mode")
            return

        try:
            import httpx

            client = httpx.AsyncClient(
                base_url=api_base.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0),
            )

            async def embed_fn(text: str) -> list[float]:
                resp = await client.post(
                    "/v1/embeddings",
                    json={"input": text, "model": model},
                )
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]

            self._embedding_fn = embed_fn
            self._httpx_client = client
            logger.info(f"[NativeMemory] Embedding enabled: {api_base} ({model})")
        except ImportError:
            logger.warning("[NativeMemory] httpx not available, embedding disabled")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
