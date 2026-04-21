"""Native Memory Backend — MongoDB-backed, zero external dependencies."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.infra.logging import get_logger
from src.infra.memory.client.base import MemoryBackend
from src.infra.memory.client.native.classification import (
    find_existing_memory_match,
    is_manual_memory_worthy,
)
from src.infra.memory.client.native.consolidation import consolidate_memories as run_consolidation
from src.infra.memory.client.native.content import (
    build_content_fields,
    delete_memory_content,
)
from src.infra.memory.client.native.indexing import build_memory_index
from src.infra.memory.client.native.models import COLLECTION_NAME
from src.infra.memory.client.native.search import recall_memories
from src.infra.memory.client.native.summaries import (
    _fallback_enrich,
    build_index_label,
    llm_enrich_memory,
)
from src.infra.memory.client.types import MemoryType
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)

_CONTEXT_TYPE_HINTS = {
    "feedback": MemoryType.FEEDBACK,
    "project": MemoryType.PROJECT,
    "reference": MemoryType.REFERENCE,
}


def _infer_memory_type(context: Optional[str] = None) -> str:
    if context:
        ctx_lower = context.lower()
        for hint, mt in _CONTEXT_TYPE_HINTS.items():
            if hint in ctx_lower:
                return mt.value
    return MemoryType.USER


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
    async def _get_memory_model():
        """Get LLM model for memory operations.

        Uses dedicated NATIVE_MEMORY_MODEL/API config if set,
        otherwise falls back to the main LLM_MODEL.
        """
        model = getattr(settings, "NATIVE_MEMORY_MODEL", None)
        api_base = getattr(settings, "NATIVE_MEMORY_API_BASE", None) or None
        api_key = getattr(settings, "NATIVE_MEMORY_API_KEY", None) or None
        max_tokens = int(getattr(settings, "NATIVE_MEMORY_MAX_TOKENS", 2000))
        from src.infra.llm.client import LLMClient

        return await LLMClient.get_model(
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
        tags: Optional[list[str]] = None,
        existing_memory_id: Optional[str] = None,
    ) -> dict[str, Any]:
        # --- Validation (relaxed for manual retention — trust user intent) ---
        if len(content.strip()) < 5:
            return {
                "success": False,
                "error": "Content too short (minimum 5 characters)",
            }

        if not is_manual_memory_worthy(content, context):
            return {
                "success": False,
                "error": "Content rejected: appears transient, noisy, or not durable enough",
            }

        memory_type = _infer_memory_type(context)

        # If caller provides all three, skip LLM enrichment entirely
        if title and summary and tags:
            tags = [str(t)[:20] for t in tags[:5] if t]
        elif not title or not summary:
            enriched = await llm_enrich_memory(self, content)
            if not tags:
                tags = enriched["tags"]
            if not summary:
                summary = enriched["summary"]
            if not title:
                title = enriched["title"]
        elif not tags:
            enriched = await llm_enrich_memory(self, content)
            tags = enriched["tags"]

        async def fetch_recent_memories(target_user_id: str) -> list[dict[str, Any]]:
            seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
            return await self._collection.find(
                {"user_id": target_user_id, "updated_at": {"$gte": seven_days_ago}},
                {"summary": 1, "memory_id": 1, "memory_type": 1},
            ).to_list(length=50)

        existing_match = None
        _match_projection = {
            "memory_id": 1,
            "memory_type": 1,
            "summary": 1,
            "updated_at": 1,
            "content_storage_mode": 1,
            "content_store_key": 1,
        }
        if existing_memory_id:
            forced_match = await self._collection.find_one(
                {"user_id": user_id, "memory_id": existing_memory_id},
                _match_projection,
            )
            if forced_match:
                existing_match = forced_match
        if existing_match is None:
            existing_match = await find_existing_memory_match(
                fetch_recent=fetch_recent_memories,
                user_id=user_id,
                summary=summary,
                memory_type=memory_type,
            )
            # fetch content fields for store cleanup if matched via similarity
            if existing_match and "content_storage_mode" not in existing_match:
                full_doc = await self._collection.find_one(
                    {"user_id": user_id, "memory_id": existing_match["memory_id"]},
                    {"content_storage_mode": 1, "content_store_key": 1},
                )
                if full_doc:
                    existing_match.update(full_doc)

        now = datetime.now(timezone.utc)
        is_update = existing_match is not None
        _existing: dict[str, Any] = existing_match if is_update else {}  # type: ignore[assignment]
        memory_id = _existing["memory_id"] if is_update else uuid.uuid4().hex
        content_fields, embedding = await asyncio.gather(
            build_content_fields(self, user_id, memory_id, content),
            self._maybe_embed(content),
        )

        if is_update:
            await self._collection.update_one(
                {"user_id": user_id, "memory_id": _existing["memory_id"]},
                {
                    "$set": {
                        "title": title[:25],
                        "summary": summary[:100],
                        "index_label": build_index_label(title, summary, content),
                        "context": context,
                        "tags": tags,
                        "embedding": embedding,
                        "updated_at": now,
                        **content_fields,
                    }
                },
            )
            if (
                _existing.get("content_storage_mode") == "store"
                and _existing.get("content_store_key")
                and _existing.get("content_store_key") != content_fields.get("content_store_key")
            ):
                await delete_memory_content(self, user_id, _existing.get("content_store_key"))
            await self._invalidate_cache(user_id)
            return {
                "success": True,
                "memory_id": _existing["memory_id"],
                "memory_type": memory_type,
                "updated_existing": True,
                "message": "Memory updated successfully",
            }

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
            "embedding": embedding,
            "created_at": now,
            "updated_at": now,
            "accessed_at": now,
            "access_count": 0,
        }
        doc.update(content_fields)

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
        existing_doc = await self._collection.find_one(
            {"user_id": user_id, "memory_id": memory_id},
            {"content_storage_mode": 1, "content_store_key": 1},
        )
        result = await self._collection.delete_one({"user_id": user_id, "memory_id": memory_id})
        if result.deleted_count > 0:
            if existing_doc and existing_doc.get("content_storage_mode") == "store":
                await delete_memory_content(self, user_id, existing_doc.get("content_store_key"))
            await self._invalidate_cache(user_id)
            return {"success": True, "message": f"Memory {memory_id} deleted"}
        return {"success": False, "error": "Memory not found"}

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

    async def auto_retain_from_text(self, user_id: str, text: str) -> dict[str, Any]:
        if not text.strip():
            return {"success": True, "stored": 0, "candidates": 0}

        try:
            from src.infra.memory.tools import memory_retain

            candidates = await self._get_auto_retain_candidates(user_id, text)
            candidates_text = "\n".join(
                (
                    f"- id={item.get('memory_id')} "
                    f"type={item.get('type')} "
                    f"title={item.get('title', '')!r} "
                    f"summary={item.get('summary', '')!r} "
                    f"updated_at={item.get('created_at') or item.get('updated_at', '')}"
                )
                for item in candidates
            )
            model = (await self._get_memory_model()).bind_tools([memory_retain])
            response = await model.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "You are a background memory-retention evaluator.\n"
                            "You receive one user message after the main assistant response has already finished.\n"
                            "You may see similar existing memories.\n"
                            "If the message contains durable cross-session memory, call memory_retain.\n"
                            "If it does not, do not call any tool.\n"
                            "Only retain user identity, preferences with reasons, durable project context, "
                            "explicit feedback, or lasting references. Never retain code, file paths, "
                            "temporary worklogs, greetings, or transient status updates.\n"
                            "When calling memory_retain, ALWAYS provide title, summary, and tags "
                            "— this avoids a second LLM call. Keep title under 25 chars, summary under 80 chars, "
                            "and provide 3-5 keyword tags.\n"
                            "If one existing memory already covers the same topic, call memory_retain with "
                            "`existing_memory_id` set to that memory id so the system updates it instead of "
                            "creating a duplicate.\n"
                            "If none match closely enough, omit `existing_memory_id`."
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"User message:\n{text}\n\n"
                            f"Similar existing memories:\n{candidates_text or '(none)'}"
                        )
                    ),
                ]
            )
        except Exception as e:
            self._logger.debug("[NativeMemory] Background auto-retain decision failed: %s", e)
            return {"success": False, "stored": 0, "candidates": 0, "error": str(e)}

        tool_calls = getattr(response, "tool_calls", None) or []
        stored = 0
        for tool_call in tool_calls:
            if tool_call.get("name") != "memory_retain":
                continue
            args = tool_call.get("args") or {}
            content = str(args.get("content") or "").strip()
            if not content:
                continue
            # Ensure all three enrichment fields are present so retain() skips the LLM call.
            # Rule-based fallbacks fill gaps when the decision LLM omits optional params.
            title = args.get("title")
            summary = args.get("summary")
            tags = args.get("tags")
            if not title or not summary or not tags:
                enriched = _fallback_enrich(content)
                title = title or enriched["title"]
                summary = summary or enriched["summary"]
                tags = tags or enriched["tags"]
            result = await self.retain(
                user_id,
                content,
                context=args.get("context"),
                title=title,
                summary=summary,
                tags=tags,
                existing_memory_id=args.get("existing_memory_id"),
            )
            if result.get("success"):
                stored += 1
        return {"success": True, "stored": stored, "candidates": len(tool_calls)}

    async def _get_auto_retain_candidates(self, user_id: str, text: str) -> list[dict[str, Any]]:
        result = await recall_memories(
            self,
            user_id,
            text,
            max_results=5,
            touch_access=False,
            enable_rerank=False,
        )
        if not result.get("success"):
            return []
        return list(result.get("memories") or [])

    # ------------------------------------------------------------------
    # Memory index (for system prompt injection)
    # ------------------------------------------------------------------

    async def build_memory_index(self, user_id: str) -> str:
        return await build_memory_index(self, user_id)

    async def _update_access_stats(self, memory_ids: list[str], user_id: str = "") -> None:
        query: dict[str, Any] = {"memory_id": {"$in": memory_ids}}
        if user_id:
            query["user_id"] = user_id
        await self._collection.update_many(
            query,
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
