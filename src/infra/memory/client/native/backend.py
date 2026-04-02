"""Native Memory Backend — MongoDB-backed, zero external dependencies."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from src.infra.logging import get_logger
from src.infra.memory.client.base import MemoryBackend
from src.infra.memory.client.native.classification import (
    classify_type,
    extract_tags,
    find_existing_memory_match,
    is_manual_memory_worthy,
)
from src.infra.memory.client.native.consolidation import (
    consolidate_memories as run_consolidation,
    do_consolidate,
    llm_batch_consolidate,
    split_batches,
)
from src.infra.memory.client.native.content import (
    build_content_fields,
    get_store,
    hydrate_formatted_memory,
    hydrate_memory_text,
    maybe_await,
    memory_store_namespace,
    store_get,
    store_put,
)
from src.infra.memory.client.native.indexing import build_memory_index, evict_index_cache
from src.infra.memory.client.native.models import COLLECTION_NAME
from src.infra.memory.client.native.search import (
    format_memory,
    recall_memories,
)
from src.infra.memory.client.native.summaries import (
    build_index_label,
    build_summary,
    llm_build_summary,
    llm_build_title,
)
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)


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
        self._store: Any = None
        self._logger = logger
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
        await self._prune_legacy_session_summaries()

    async def close(self) -> None:
        if self._httpx_client is not None:
            try:
                await self._httpx_client.aclose()
            except Exception:
                pass
            self._httpx_client = None
        self._collection = None
        self._embedding_fn = None
        self._store = None
        self._index_cache.clear()

    async def _prune_legacy_session_summaries(self) -> None:
        """One-time cleanup for old transcript-style session summary memories."""
        if self._collection is None:
            return
        try:
            result = await self._collection.delete_many({"source": "session_summary"})
            deleted_count = int(getattr(result, "deleted_count", 0) or 0)
            if deleted_count:
                logger.info(
                    "[NativeMemory] Pruned %d legacy session summary memories", deleted_count
                )
        except Exception as e:
            logger.debug("[NativeMemory] Failed to prune legacy session summaries: %s", e)

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
        title: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> dict[str, Any]:
        # --- Validation (relaxed for manual retention — trust user intent) ---
        if len(content.strip()) < 5:
            return {
                "success": False,
                "error": "Content too short (minimum 10 characters)",
            }

        if not is_manual_memory_worthy(content, context):
            return {
                "success": False,
                "error": "Content rejected: appears transient, noisy, or not durable enough",
            }

        memory_type = classify_type(content, context)
        tags = extract_tags(content)

        # Use caller-provided title/summary, fall back to rule-based
        if not summary:
            summary = build_summary(content)
        if not title:
            title = build_summary(content, 25)

        async def fetch_recent_memories(target_user_id: str) -> list[dict[str, Any]]:
            seven_days_ago = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=7)
            return await self._collection.find(
                {"user_id": target_user_id, "updated_at": {"$gte": seven_days_ago}},
                {"summary": 1, "memory_id": 1, "memory_type": 1},
            ).to_list(length=50)

        existing_match = await find_existing_memory_match(
            fetch_recent=fetch_recent_memories,
            user_id=user_id,
            summary=summary,
            memory_type=memory_type,
        )

        now = datetime.now(timezone.utc)
        content_fields = await build_content_fields(
            self,
            user_id,
            existing_match["memory_id"] if existing_match else uuid.uuid4().hex,
            content,
        )

        if existing_match:
            await self._collection.update_one(
                {"user_id": user_id, "memory_id": existing_match["memory_id"]},
                {
                    "$set": {
                        "title": title[:25],
                        "summary": summary[:100],
                        "index_label": build_index_label(title, summary, content),
                        "context": context,
                        "tags": tags,
                        "updated_at": now,
                        **content_fields,
                    }
                },
            )
            await self._invalidate_cache(user_id)
            return {
                "success": True,
                "memory_id": existing_match["memory_id"],
                "memory_type": memory_type,
                "updated_existing": True,
                "message": "Memory updated successfully",
            }

        memory_id = uuid.uuid4().hex
        doc = {
            "memory_id": memory_id,
            "user_id": user_id,
            "title": title[:25],
            "summary": summary[:100],
            "index_label": build_index_label(title, summary, content),
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
        doc.update(await build_content_fields(self, user_id, memory_id, content))

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
        return await recall_memories(self, user_id, query, max_results, memory_types)

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
        """Legacy compatibility hook.

        Session-level transcript summaries are intentionally no longer stored as
        long-term memories. We only keep extracted durable memories.
        """
        logger.debug("[NativeMemory] Ignoring legacy session summary write for %s", session_id[:8])
        return None

    # ------------------------------------------------------------------
    # Memory consolidation (on-demand, triggered by agent via memory_consolidate tool)
    # ------------------------------------------------------------------

    async def consolidate_memories(self, user_id: str) -> dict[str, Any]:
        from src.infra.memory.distributed import (
            acquire_consolidation_lock,
            release_consolidation_lock,
        )

        return await run_consolidation(
            self,
            user_id,
            acquire_lock=acquire_consolidation_lock,
            release_lock=release_consolidation_lock,
        )

    async def _do_consolidate(self, user_id: str) -> dict[str, Any]:
        return await do_consolidate(self, user_id)

    @staticmethod
    def _split_batches(items: list[dict], max_size: int = 30) -> list[list[dict]]:
        return split_batches(items, max_size)

    async def _llm_batch_consolidate(
        self, memories: list[dict], expected_type: str
    ) -> Optional[list[dict]]:
        return await llm_batch_consolidate(self, memories, expected_type)

    async def _llm_rerank(
        self, user_id: str, query: str, candidates: list[dict], max_results: int
    ) -> list[dict]:
        from src.infra.memory.client.native.search import llm_rerank

        return await llm_rerank(self, user_id, query, candidates, max_results)

    # ------------------------------------------------------------------
    # Memory index (for system prompt injection)
    # ------------------------------------------------------------------

    async def build_memory_index(self, user_id: str) -> str:
        return await build_memory_index(self, user_id)

    def _evict_index_cache(self) -> None:
        evict_index_cache(self._index_cache, self._INDEX_CACHE_MAX_SIZE)

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
