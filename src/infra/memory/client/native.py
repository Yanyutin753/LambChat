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

# Chinese stopwords for tag extraction
_CJK_STOPWORDS = frozenset(
    "的 了 是 在 和 与 也 都 就 要 会 能 有 这 那 一 不 个 吧 啊 呢 吗 呀 "
    "把 被 让 给 对 从 到 向 比 用 以 为 所 之 其 着 过 地 得 很 已 还 "
    "再 又 却 并 因为 所以 如果 但是 而且 或者 虽然 不过".split()
)


def _ensure_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC) if it is naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _has_cjk(text: str) -> bool:
    """Check if text contains CJK characters."""
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    """Extract character n-grams from text, useful for Chinese similarity."""
    cleaned = re.sub(r"\s+", "", text)
    if len(cleaned) < n:
        return set()
    return {cleaned[i : i + n] for i in range(len(cleaned) - n + 1)}


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
        # Per-user consolidation dedup: prevents spawning multiple tasks
        self._consolidation_pending: set[str] = set()

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

    @staticmethod
    def _get_memory_model():
        """Get LLM model for memory operations.

        Uses dedicated NATIVE_MEMORY_MODEL/API config if set,
        otherwise falls back to the main LLM_MODEL.
        """
        model = getattr(settings, "NATIVE_MEMORY_MODEL", None) or getattr(
            settings, "LLM_MODEL", None
        )
        api_base = (
            getattr(settings, "NATIVE_MEMORY_API_BASE", None)
            or getattr(settings, "LLM_API_BASE", "")
            or ""
        )
        api_key = (
            getattr(settings, "NATIVE_MEMORY_API_KEY", None)
            or getattr(settings, "LLM_API_KEY", "")
            or ""
        )
        max_tokens = int(getattr(settings, "NATIVE_MEMORY_MAX_TOKENS", 2000))
        from src.infra.llm.client import LLMClient

        return LLMClient.get_model(
            model=model,
            api_base=api_base,
            api_key=api_key,
            temperature=0.1,
            max_tokens=max_tokens,
        )

    async def retain(
        self,
        user_id: str,
        content: str,
        context: Optional[str] = None,
    ) -> dict[str, Any]:
        # --- Validation (relaxed for manual retention — trust user intent) ---
        if len(content.strip()) < 5:
            return {
                "success": False,
                "error": "Content too short (minimum 10 characters)",
            }

        # Noise filter: reject code patterns, file paths, error traces
        for pat in EXCLUDED_CONTENT_PATTERNS:
            if re.search(pat, content, re.IGNORECASE):
                return {
                    "success": False,
                    "error": "Content rejected: appears to be code, commands, or technical noise",
                }

        # Deduplication: reject if too similar to existing recent memory
        summary = self._build_summary(content)
        dup_candidates = [{"content": content, "summary": summary}]
        deduped = await self._deduplicate_against_existing(user_id, dup_candidates)
        if not deduped:
            return {
                "success": False,
                "error": "Content rejected: too similar to an existing recent memory",
            }

        memory_type = self._classify_type(content, context)
        tags = self._extract_tags(content)
        title = await self._llm_build_title(content)
        summary = await self._llm_build_summary(content)
        memory_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)

        doc = {
            "memory_id": memory_id,
            "user_id": user_id,
            "content": content[:5000],
            "title": title,
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

    async def store_session_summary(self, user_id: str, session_id: str, summary: str) -> None:
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
                        "title": f"Session {session_id[:8]}",
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
                    "title": f"Session {session_id[:8]}",
                    "memory_type": "reference",
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
        # Only use LLM-based extraction — rule-based fallback is too permissive
        memories = await self._llm_extract_memories(user_id, conversation_summary)
        if not memories:
            return

        # Deduplicate against existing memories
        memories = await self._deduplicate_against_existing(user_id, memories)
        if not memories:
            return

        now = datetime.now(timezone.utc)
        docs = []
        for mem in memories[:2]:
            doc = {
                "memory_id": uuid.uuid4().hex,
                "user_id": user_id,
                "content": mem["content"][:5000],
                "summary": mem["summary"],
                "title": mem.get("title", ""),
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
            logger.info(f"[NativeMemory] Auto-retained {len(docs)} memories for {user_id}")

            # On-demand consolidation: after storing new memories, check if
            # this user's memory set has grown enough to warrant cleanup.
            if user_id not in self._consolidation_pending:
                self._consolidation_pending.add(user_id)
                asyncio.create_task(self._maybe_consolidate(user_id))

    # ------------------------------------------------------------------
    # Memory consolidation (on-demand)
    # ------------------------------------------------------------------

    async def _maybe_consolidate(self, user_id: str) -> None:
        """Check if a user's memories need consolidation, and do it if so.

        Triggered automatically after auto-retain stores new memories.
        Only counts auto-retained memories (manual memories are protected).
        Only consolidates if:
          1. The user has > 10 auto-retained memories
          2. The gap between newest and oldest exceeds 1 day
        """
        try:
            pipeline = [
                {"$match": {"user_id": user_id, "source": {"$ne": "manual"}}},
                {
                    "$group": {
                        "_id": None,
                        "count": {"$sum": 1},
                        "oldest": {"$min": "$created_at"},
                        "newest": {"$max": "$created_at"},
                    }
                },
            ]
            result = await self._collection.aggregate(pipeline).to_list(length=1)
            if not result:
                return

            stats = result[0]
            count = stats["count"]
            if count <= 10:
                return

            oldest = _ensure_aware(stats["oldest"])
            newest = _ensure_aware(stats["newest"])
            span_hours = (newest - oldest).total_seconds() / 3600

            if span_hours <= 24:
                return

            logger.info(
                "[NativeMemory] %s has %d auto memories spanning %.1fh, triggering consolidation",
                user_id[:8],
                count,
                span_hours,
            )
            await self.consolidate_memories(user_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("[NativeMemory] _maybe_consolidate failed for %s: %s", user_id[:8], e)
        finally:
            self._consolidation_pending.discard(user_id)

    async def consolidate_memories(self, user_id: str) -> dict[str, Any]:
        """Consolidate memories: merge duplicates, update stale info, prune ephemeral.

        Inspired by Claude Code's memory architecture:
        - Session summaries are ephemeral (auto-prune after 7 days)
        - Auto-retained memories use soft decay: older + less accessed = more likely to prune
        - Manual memories (source="manual") are NEVER touched
        - LLM sees full context per type to make better merge/update decisions
        - One LLM call per memory type (max 4 total) instead of per-group

        Protected by a distributed lock to prevent concurrent consolidation.
        """
        instance_id = uuid.uuid4().hex[:8]
        try:
            from src.infra.memory.distributed import (
                acquire_consolidation_lock,
                release_consolidation_lock,
            )

            locked = await acquire_consolidation_lock(user_id, instance_id)
            if not locked:
                logger.info(
                    "[NativeMemory] Consolidation already in progress for %s, skipping", user_id
                )
                return {"merged": 0, "pruned": 0, "total_before": 0, "skipped": True}
        except Exception:
            locked = False

        try:
            return await self._do_consolidate(user_id)
        finally:
            if locked:
                try:
                    from src.infra.memory.distributed import release_consolidation_lock

                    await release_consolidation_lock(user_id, instance_id)
                except Exception:
                    pass

    async def _do_consolidate(self, user_id: str) -> dict[str, Any]:
        """Internal consolidation implementation (called after lock acquired).

        Three phases:
        1. Rule-based pruning: session summaries (7d), stale + never accessed (soft decay)
        2. LLM batch consolidation: one call per type, LLM decides merge/keep/delete
        3. Count result
        """
        # Fetch all memories (oldest first — better LLM context)
        all_memories = await self._collection.find(
            {"user_id": user_id},
            sort=[("created_at", 1)],
        ).to_list(length=500)

        if len(all_memories) < 5:
            return {"merged": 0, "pruned": 0, "total_before": len(all_memories)}

        total_before = len(all_memories)
        now = datetime.now(timezone.utc)
        prune_threshold = int(getattr(settings, "NATIVE_MEMORY_PRUNE_THRESHOLD", 90))

        # ------------------------------------------------------------------
        # Phase 1: Rule-based pruning (no LLM, just delete)
        # ------------------------------------------------------------------
        # Inspired by Claude Code:
        # - Session summaries are ephemeral context bridges, prune after 7 days
        # - Auto-retained memories use soft decay by age × access
        # - Manual memories are NEVER pruned
        pruned_ids: set[str] = set()

        for m in all_memories:
            source = m.get("source", "")
            updated = _ensure_aware(m.get("updated_at", now))
            age_days = (now - updated).days
            access_count = m.get("access_count", 0)

            # Manual memories: always protected
            if source == "manual":
                continue

            # Session summaries: ephemeral, prune after 7 days
            if source == "session_summary" and age_days > 7:
                pruned_ids.add(m["memory_id"])
                continue

            # Auto-retained: soft decay
            #   180+ days → always prune (even if accessed occasionally)
            #   90+ days  → prune if accessed ≤ 1 time
            #   30+ days  → prune if never accessed
            if source == "auto_retained":
                if age_days > 180:
                    pruned_ids.add(m["memory_id"])
                elif age_days > prune_threshold and access_count <= 1:
                    pruned_ids.add(m["memory_id"])
                elif age_days > 30 and access_count == 0:
                    pruned_ids.add(m["memory_id"])

        if pruned_ids:
            await self._collection.delete_many(
                {"user_id": user_id, "memory_id": {"$in": list(pruned_ids)}}
            )

        # Separate manual memories (protected from LLM consolidation)
        remaining = [m for m in all_memories if m["memory_id"] not in pruned_ids]
        auto_memories = [m for m in remaining if m.get("source") != "manual"]

        # ------------------------------------------------------------------
        # Phase 2: LLM batch consolidation per type
        # ------------------------------------------------------------------
        # One LLM call per type. The LLM sees ALL memories of that type and
        # decides: merge overlapping, keep unique, delete stale/duplicate.
        # This replaces the old tag-based grouping + per-group LLM approach.
        reduced = 0

        for mtype in MemoryType:
            type_memories = [m for m in auto_memories if m.get("memory_type") == mtype.value]
            if len(type_memories) < 3:
                continue

            # Split into batches if too many (> 30 per LLM call)
            for batch in self._split_batches(type_memories, max_size=30):
                consolidated = await self._llm_batch_consolidate(batch, mtype.value)
                if consolidated is None:
                    continue  # LLM failed, keep originals

                old_ids = [m["memory_id"] for m in batch]
                await self._collection.delete_many(
                    {"user_id": user_id, "memory_id": {"$in": old_ids}}
                )
                if consolidated:
                    await self._collection.insert_many(consolidated)
                reduced += len(batch) - len(consolidated)

        await self._invalidate_cache(user_id)

        # ------------------------------------------------------------------
        # Phase 3: Hard cap safety net (like Claude Code's 200 file limit)
        # ------------------------------------------------------------------
        # If the user still has > 200 memories after Phase 1+2, prune the
        # oldest auto-retained ones until we're back under the cap.
        # Manual memories are never pruned.
        max_per_user = 200
        current_count = await self._collection.count_documents({"user_id": user_id})
        cap_pruned = 0

        if current_count > max_per_user:
            # Find oldest auto-retained memories to remove
            excess = current_count - max_per_user
            oldest_auto = (
                self._collection.find(
                    {"user_id": user_id, "source": {"$ne": "manual"}},
                    {"memory_id": 1},
                )
                .sort("created_at", 1)
                .limit(excess)
            )
            oldest_docs = await oldest_auto.to_list(length=excess)
            if oldest_docs:
                cap_ids = [d["memory_id"] for d in oldest_docs]
                result = await self._collection.delete_many(
                    {"user_id": user_id, "memory_id": {"$in": cap_ids}}
                )
                cap_pruned = result.deleted_count
                await self._invalidate_cache(user_id)

        # Phase 4: count final state
        final_count = await self._collection.count_documents({"user_id": user_id})
        result = {
            "merged": reduced,
            "pruned": len(pruned_ids) + cap_pruned,
            "total_before": total_before,
            "total_after": final_count,
        }
        logger.info(
            "[NativeMemory] Consolidation for %s: merged=%d, pruned=%d, %d -> %d",
            user_id,
            reduced,
            len(pruned_ids),
            total_before,
            final_count,
        )
        return result

    @staticmethod
    def _split_batches(items: list[dict], max_size: int = 30) -> list[list[dict]]:
        """Split a list into chunks of at most max_size."""
        return [items[i : i + max_size] for i in range(0, len(items), max_size)]

    async def _llm_batch_consolidate(
        self, memories: list[dict], expected_type: str
    ) -> Optional[list[dict]]:
        """Send a batch of memories to LLM and get a consolidated set back.

        The LLM decides for each memory: merge with another, keep as-is, or delete.
        Returns the consolidated list (may be shorter than input), or None on failure.
        """

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = self._get_memory_model()

            # Format memories with date for LLM context (oldest first)
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
                'Return ONLY a JSON array: [{"content": "...", "summary": "...", "title": "..."}]\n'
                "title should be max 25 chars, a short label for this memory.\n"
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
            text = text.strip()

            parsed = json.loads(text)
            if not isinstance(parsed, list):
                return None

            # Safety: if LLM returned nothing but we had many inputs, skip
            if not parsed and len(memories) >= 3:
                logger.warning(
                    "[NativeMemory] LLM returned empty array for %d memories, skipping",
                    len(memories),
                )
                return None

            now = datetime.now(timezone.utc)
            docs = []
            for item in parsed:
                content = item.get("content", "").strip()
                if not content or len(content) < 10:
                    continue
                summary = item.get("summary", "")
                if not summary:
                    summary = await self._llm_build_summary(content)
                title = item.get("title", "").strip()
                if not title:
                    title = await self._llm_build_title(content)
                docs.append(
                    {
                        "memory_id": uuid.uuid4().hex,
                        "user_id": memories[0]["user_id"],
                        "content": content[:5000],
                        "summary": summary[:100],
                        "title": title[:25],
                        "memory_type": expected_type,
                        "context": "consolidated",
                        "tags": self._extract_tags(content),
                        "source": "auto_retained",
                        "embedding": await self._maybe_embed(content),
                        "created_at": now,
                        "updated_at": now,
                        "accessed_at": now,
                        "access_count": 0,
                    }
                )
            return docs if docs else None

        except Exception as e:
            logger.debug("[NativeMemory] Batch consolidation failed: %s", e)
            return None

    async def _llm_rerank(
        self, user_id: str, query: str, candidates: list[dict], max_results: int
    ) -> list[dict]:
        """Use LLM to re-rank candidate memories by contextual relevance."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = self._get_memory_model()

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
            logger.debug("[NativeMemory] LLM rerank failed, using RRF order: %s", e)
            return candidates[:max_results]

    # ------------------------------------------------------------------
    # Memory index (for system prompt injection)
    # ------------------------------------------------------------------

    async def build_memory_index(self, user_id: str) -> str:
        """
        Build lightweight memory index string for system prompt.
        Grouped by type, capped at 5 per type, with human-readable staleness.
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
                            "title": "$title",
                            "summary": "$summary",
                            "memory_id": "$memory_id",
                            "updated_at": "$updated_at",
                        }
                    },
                }
            },
            {
                "$project": {
                    "items": {"$slice": ["$items", 5]},
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
                # Human-readable staleness
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
                # Display: title + short_id (fallback to summary[:30] for old memories)
                display_title = item.get("title") or ""
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
                    lines.append(
                        f"- {display_title} ({age_str})" if age_str else f"- {display_title}"
                    )

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
        projection = {
            "memory_id": 1,
            "content": 1,
            "summary": 1,
            "memory_type": 1,
            "source": 1,
            "created_at": 1,
            "updated_at": 1,
            "embedding": 1,
        }
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

    async def _llm_extract_memories(self, user_id: str, conversation: str) -> list[dict]:
        """Use a lightweight LLM call to extract structured memories from a conversation turn.

        Falls back gracefully on any error (returns empty list).
        """
        if len(conversation.strip()) < 10:
            return []

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = self._get_memory_model()

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
                "You are an EXTREMELY STRICT memory extraction filter. Your job is to decide if "
                "anything in this conversation is worth remembering PERMANENTLY across sessions.\n\n"
                "You must be CONSERVATIVE: when in any doubt, return []. Most conversations "
                "contain NOTHING worth remembering. Only extract genuine, durable, non-obvious facts.\n\n"
                "Return a JSON array of objects with 'content', 'type' "
                "(one of: user, feedback, project, reference), 'summary' (max 80 chars), "
                "and 'title' (max 25 chars, a short label for this memory). "
                "Return at most 2 items.\n\n"
                "EXTRACT only if ALL of these are true:\n"
                "- The content is a FACTUAL STATEMENT (never a question or request)\n"
                "- The content reveals something SPECIFIC and NON-OBVIOUS about the user: "
                "a concrete preference with reason, a named tool/framework they use, a role with "
                "context, a hard constraint, a named project with goal, or explicit positive/negative "
                "feedback on a specific approach\n"
                "- The content would still be useful MONTHS from now (not just today)\n"
                "- The content contains at least one SPECIFIC entity: a name, a tool name, "
                "a date, a number, a framework, a project name, or a concrete decision\n\n"
                "ALWAYS REJECT (return []):\n"
                "- Questions of any kind (who/what/why/where/when/how/多少/什么/为什么/怎么/哪个)\n"
                "- Greetings, farewells, thanks, acknowledgments, small talk\n"
                "- Requests for the AI to do something ('help me', 'show me', 'check', 'please')\n"
                "- Vague self-introductions without specifics ('I am a developer', 'I like coding')\n"
                "- Meta-commentary about the conversation itself\n"
                "- Code snippets, file paths, git commands, error traces, terminal output\n"
                "- Anything obvious, generic, or universally true\n"
                "- Assistant boilerplate, greetings, or identity statements\n"
                "- Content shorter than 30 characters\n"
                "- Temporary/ephemeral state ('currently looking at X', 'right now I'm doing Y')\n"
                "  unless it includes a specific deadline, constraint, or named deliverable\n"
                "- Mild preferences without rationale ('I prefer X') — only keep if a reason is given\n"
                "- Activity logs, summaries, or recaps — extract only the surprising/non-obvious kernel\n\n"
                "TYPE rules:\n"
                "- user: concrete identity (name+role), expertise level with years, specific preferences "
                "WITH reasoning, named tools/frameworks they use daily\n"
                "- feedback: BOTH corrections AND positive confirmations. Must include the SPECIFIC "
                "approach that was validated/rejected and the WHY. 'yes exactly' alone is not enough — "
                "capture WHAT was confirmed and WHY it matters.\n"
                "- project: specific work items with concrete deadlines, constraints, or stakeholders\n"
                "- reference: external system URLs with their purpose, named identifiers\n\n"
                "EXAMPLES of GOOD memories:\n"
                "- 'User is a backend engineer with 8 years Go experience, new to React — explain "
                "frontend concepts using backend analogies'\n"
                "- 'User prefers raw SQL over ORMs because a past ORM migration silently corrupted "
                "production data'\n"
                "- 'User confirmed the single-bundle PR approach for this area — avoids churn from "
                "splitting interdependent changes'\n\n"
                "EXAMPLES of BAD memories (do NOT extract):\n"
                "- 'User is a developer'\n"
                "- 'User asked about authentication'\n"
                "- 'User prefers TypeScript'\n"
                "- 'Working on the login feature'\n\n"
                f"{existing_hint}\n\n"
                "Conversation:\n"
                f"{conversation[:2000]}\n\n"
                'Return ONLY valid JSON: [{"content": "...", "type": "user", "summary": "...", "title": "..."}] '
                "or [] if nothing is worth remembering."
            )

            response = await model.ainvoke(
                [
                    SystemMessage(
                        content="You are a STRICT memory extraction filter. Be extremely conservative. When in doubt, return []. Output only JSON."
                    ),
                    HumanMessage(content=prompt),
                ],
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
            for item in parsed[:2]:
                content = item.get("content", "").strip()
                mem_type = item.get("type", "user")
                summary = item.get("summary", "")
                if not content:
                    continue
                # Post-extraction validation: reject low-quality candidates
                if not self._is_valid_memory_content(content):
                    continue
                # Noise post-check: reject code patterns / file paths
                if any(re.search(pat, content, re.IGNORECASE) for pat in EXCLUDED_CONTENT_PATTERNS):
                    continue
                if mem_type not in ("user", "feedback", "project", "reference"):
                    mem_type = "user"
                if not summary:
                    summary = await self._llm_build_summary(content)
                title = item.get("title", "").strip()
                if not title:
                    title = await self._llm_build_title(content)
                memories.append(
                    {
                        "content": content[:5000],
                        "summary": summary[:100],
                        "title": title[:25],
                        "memory_type": mem_type,
                        "tags": self._extract_tags(content),
                    }
                )
            if memories:
                logger.info("[NativeMemory] LLM extracted %d memories", len(memories))
            return memories

        except Exception as e:
            logger.warning("[NativeMemory] LLM extraction failed, falling back to rules: %s", e)
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

        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
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
            if any(
                self._word_similarity(summary, rs) > (0.55 if _has_cjk(summary + rs) else 0.7)
                for rs in recent_summaries
            ):
                continue  # too similar, skip
            filtered.append(mem)

        return filtered

    @staticmethod
    def _word_similarity(a: str, b: str) -> float:
        """Jaccard similarity — uses character n-grams for CJK, word sets for English."""
        if _has_cjk(a) or _has_cjk(b):
            set_a = _char_ngrams(a, 2)
            set_b = _char_ngrams(b, 2)
        else:
            set_a = set(a.lower().split())
            set_b = set(b.lower().split())
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    # Patterns that indicate the content is a question or request, not a memory
    _QUESTION_PATTERNS = re.compile(
        r"^(为什么|怎么|如何|啥|什么|多少|哪[个里]|谁|谁|where|what|why|how|"
        r"who|when|which|can you|could you|would you|please |帮我|请帮我|"
        r"你好|嗨|hi |hello|hey)",
        re.IGNORECASE,
    )

    # Patterns that indicate assistant internal monologue (should never be stored as memory)
    _ASSISTANT_MONOLOGUE_STARTS = (
        "让我",
        "我来",
        "我来帮",
        "让我来",
        "让我检查",
        "让我看看",
        "让我搜",
        "搜索一下",
        "查找一下",
        "我来分析",
        "我来搜索",
        "正在搜索",
        "正在查找",
        "正在检查",
        "正在分析",
        "正在读取",
        "正在执行",
        "我来读",
        "让我读",
        "我来查看",
        "好的，我来",
        "好的，让我",
    )

    @classmethod
    def _is_valid_memory_content(cls, content: str) -> bool:
        """Post-extraction validation: reject questions, noise, and low-signal content."""
        stripped = content.strip()
        if len(stripped) < 30:
            return False
        # Reject questions (ending with ? or ？)
        if stripped.endswith("?") or stripped.endswith("？"):
            return False
        # Reject content starting with question words
        if cls._QUESTION_PATTERNS.match(stripped):
            return False
        # Reject assistant internal monologue
        if any(stripped.startswith(p) for p in cls._ASSISTANT_MONOLOGUE_STARTS):
            return False
        # Reject pure question patterns anywhere in short content
        question_markers = ("我叫啥", "你叫啥", "我是谁", "你是谁", "什么意思", "怎么回事")
        if stripped in question_markers:
            return False
        # Reject content that is mostly punctuation or whitespace
        alpha_ratio = sum(1 for c in stripped if c.isalnum() or "\u4e00" <= c <= "\u9fff") / max(
            len(stripped), 1
        )
        if alpha_ratio < 0.5:
            return False
        return True

    def _extract_tags(self, content: str) -> list[str]:
        """Extract keyword tags. Supports both English (whitespace split) and Chinese (segment-based)."""
        tags: list[str] = []
        seen: set[str] = set()

        if _has_cjk(content):
            # Chinese: split on punctuation/whitespace, then extract 2-4 char segments
            # Filter out segments containing stopwords
            chunks = []
            current: list[str] = []
            for c in content:
                if c in "，。！？、；：''【】（）《》\t\n\r ":
                    if current:
                        chunks.append("".join(current))
                        current = []
                else:
                    current.append(c)
            if current:
                chunks.append("".join(current))

            for chunk in chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue
                # Skip chunks that are just a single stopword
                if chunk in _CJK_STOPWORDS:
                    continue
                # For chunks of 2-4 chars, use directly as tag
                if 2 <= len(chunk) <= 4:
                    if chunk not in seen:
                        tags.append(chunk)
                        seen.add(chunk)
                # For longer chunks, slide a 3-char window
                elif len(chunk) > 4:
                    for i in range(len(chunk) - 2):
                        seg = chunk[i : i + 3]
                        # Skip segments dominated by stopwords
                        if any(sw in seg for sw in ("的", "了", "是", "在")):
                            continue
                        if seg not in seen:
                            tags.append(seg)
                            seen.add(seg)
        else:
            # English: original whitespace-split logic
            for w in content.lower().split():
                clean = w.strip(".,!?;:()[]{}\"'").lower()
                if len(clean) >= 3 and clean not in _STOPWORDS and clean not in seen:
                    tags.append(clean)
                    seen.add(clean)

        return tags[:5]

    def _build_summary(self, content: str, max_len: int = 100) -> str:
        """Take the first sentence from content, supporting both CJK and English."""
        flat = content.replace("\n", " ").strip()

        # Split on common sentence-ending markers (both CJK and English)
        # without regex: find the earliest sentence boundary
        best_pos = len(flat)
        for marker in ("。", "！", "？", ". ", "! ", "? ", "；", "; "):
            pos = flat.find(marker)
            if pos != -1 and pos < best_pos:
                best_pos = pos + len(marker)

        first_sentence = flat[:best_pos].strip()
        if first_sentence and len(first_sentence) <= max_len:
            return first_sentence

        # No good sentence boundary found — truncate at max_len
        if len(flat) <= max_len:
            return flat
        # For CJK: truncate at exact char boundary
        if _has_cjk(flat):
            return flat[:max_len].strip() + "..."
        # For English: try to break at last space within max_len
        truncated = flat[:max_len]
        last_space = truncated.rfind(" ")
        if last_space > max_len // 2:
            return truncated[:last_space].strip() + "..."
        return truncated.strip() + "..."

    async def _llm_build_summary(self, content: str) -> str:
        """Use LLM to generate a concise summary (max 80 chars). Falls back to _build_summary."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = self._get_memory_model()
            response = await model.ainvoke(
                [
                    SystemMessage(
                        content="Summarize in at most 80 characters. Output ONLY the summary, nothing else."
                    ),
                    HumanMessage(
                        content=f"Summarize this memory in at most 80 characters (Chinese or English):\n\n{content[:500]}"
                    ),
                ],
            )
            text = response.content
            if isinstance(text, list):
                for item in text:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        break
                else:
                    return self._build_summary(content)
            summary = str(text).strip().strip("\"'")
            if summary and len(summary) <= 120:
                return summary[:100]
        except Exception as e:
            logger.debug("[NativeMemory] LLM summary failed, using rule-based: %s", e)
        return self._build_summary(content)

    async def _llm_build_title(self, content: str) -> str:
        """Use LLM to generate a short title (max 25 chars). Falls back to summary truncation."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = self._get_memory_model()
            response = await model.ainvoke(
                [
                    SystemMessage(
                        content="Generate a short title in at most 25 characters. Output ONLY the title."
                    ),
                    HumanMessage(
                        content=f"Give this memory a concise title (max 25 chars, Chinese or English):\n\n{content[:300]}"
                    ),
                ],
            )
            text = response.content
            if isinstance(text, list):
                for item in text:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        break
                else:
                    return self._build_summary(content, 25)
            title = str(text).strip().strip("\"'")
            if title and len(title) <= 40:
                return title[:25]
        except Exception as e:
            logger.debug("[NativeMemory] LLM title failed, using fallback: %s", e)
        return self._build_summary(content, 25)

    @staticmethod
    def _format_memory(doc: dict, score: float) -> dict:
        now = datetime.now(timezone.utc)
        staleness_days = (now - _ensure_aware(doc["updated_at"])).days
        staleness_days_cfg = getattr(settings, "NATIVE_MEMORY_STALENESS_DAYS", 30)

        result: dict[str, Any] = {
            "memory_id": doc["memory_id"],
            "text": doc["content"],
            "summary": doc["summary"],
            "title": doc.get("title", ""),
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
        try:
            col.create_index(
                [("user_id", 1), ("context", 1)],
                name="native_mem_session_ctx_idx",
                partialFilterExpression={"context": {"$regex": "^session:"}},
            )
        except Exception as e:
            logger.warning(f"[NativeMemory] Session context index creation skipped: {e}")

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
