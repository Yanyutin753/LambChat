"""Native Memory Backend — MongoDB-backed, zero external dependencies."""

import asyncio
import inspect
import uuid
from datetime import timedelta
from typing import Any, Awaitable, Callable, Optional, Sequence

from src.infra.async_utils import (
    run_blocking_io,  # noqa: F401  # 测试 seam 可拦截
    run_long_blocking_io,
)
from src.infra.llm.quota import bind_quota_user, is_quota_error, unpriced_usage
from src.infra.logging import get_logger
from src.infra.memory.cleanup import VECTOR_PENDING_INDEXES, vector_pending_fields
from src.infra.memory.client.base import MemoryBackend
from src.infra.memory.client.native.classification import (
    find_existing_memory_match,
    is_manual_memory_worthy,
)
from src.infra.memory.client.native.content import (
    build_content_fields,
    delete_memory_content,
    hydrate_memory_text_status,
)
from src.infra.memory.client.native.indexing import build_memory_index
from src.infra.memory.client.native.models import COLLECTION_NAME
from src.infra.memory.client.native.search import build_scope_clause, recall_memories
from src.infra.memory.client.native.summaries import (
    build_index_label,
    llm_enrich_memory,
)
from src.infra.memory.client.types import MemoryType
from src.infra.memory.staging import CONTENT_INDEXES, content_commit_query, insert_content_memory
from src.infra.session.conversation_history import ConversationHistoryService
from src.infra.session.conversation_history_index import (
    MEMORY_SOURCE_REFS_MAX,
    memory_lineage_update_fields,
    merge_source_refs,
)
from src.infra.storage.mongodb import get_mongo_client, get_mongo_sync_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.conversation_history import ConversationSourceRef

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
        # In-memory cache for memory index: {(user_id, project_id): (built_at, index_str)}
        self._index_cache: dict[tuple[str, str], tuple[float, str]] = {}

    @property
    def name(self) -> str:
        return "native"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _invalidate_cache(self, user_id: str) -> None:
        """Invalidate local index cache and publish invalidation to other instances."""
        for key in [k for k in self._index_cache if k[0] == user_id]:
            self._index_cache.pop(key, None)
        try:
            # The prompt middleware has a separate navigation-index snapshot
            # cache. Keep it coherent for writes from tools, extraction,
            # compaction, and self-evolution alike. This is best-effort so a
            # cache notification can never fail a durable mutation.
            from src.infra.agent.middleware.prompt_injection import (
                invalidate_memory_index_snapshot,
            )

            invalidate_memory_index_snapshot(user_id)
        except Exception:
            pass
        try:
            from src.infra.memory.distributed import publish_memory_invalidation

            await publish_memory_invalidation(user_id)
        except Exception:
            pass  # non-critical: other instances will eventually refresh via TTL

    async def initialize(self) -> None:
        """Ensure indexes exist; set up optional embedding function."""
        await run_long_blocking_io(self._ensure_collection)
        await self._create_indexes()
        self._setup_embedding_fn()
        await self._maybe_create_vector_index()
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
        """Remove a bounded batch of old summaries through durable resource cleanup."""
        if self._collection is None:
            return
        try:
            await self._collection.create_index(
                [("_id", 1), ("user_id", 1)],
                name="legacy_summary_cleanup",
                partialFilterExpression={"source": "session_summary"},
            )
            rows = (
                await self._collection.find(
                    {
                        "source": "session_summary",
                        "user_id": {"$type": "string", "$ne": ""},
                        "memory_id": {"$type": "string", "$ne": ""},
                    },
                    {"user_id": 1, "memory_id": 1, "revision_id": 1},
                )
                .sort("_id", 1)
                .limit(100)
                .to_list(length=100)
            )
            deleted_count = 0
            for row in rows:
                try:
                    result = await self._delete_matching_memory(
                        row["user_id"],
                        row["memory_id"],
                        {
                            "_id": row["_id"],
                            "user_id": row["user_id"],
                            "memory_id": row["memory_id"],
                            "source": "session_summary",
                            "revision_id": row.get("revision_id"),
                        },
                        forget_sources=False,
                    )
                    deleted_count += int(result.get("success") is True)
                except Exception as exc:
                    logger.debug(
                        "[NativeMemory] Legacy resource cleanup deferred: %s", type(exc).__name__
                    )
            if deleted_count:
                logger.info(
                    "[NativeMemory] Pruned %d legacy session summary memories",
                    deleted_count,
                )
        except Exception as exc:
            logger.debug(
                "[NativeMemory] Failed to prune legacy session summaries: %s", type(exc).__name__
            )

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_memory_model():
        """Get LLM model for memory operations.

        Uses the configured model ID if set, otherwise falls back to the
        default model. Provider credentials and base URL come from the model
        provider configuration.
        """
        max_tokens = int(getattr(settings, "NATIVE_MEMORY_MAX_TOKENS", 0) or 0)
        from src.infra.llm.client import LLMClient
        from src.infra.llm.models_service import resolve_model_reference

        model_id, model_value = await resolve_model_reference(
            getattr(settings, "NATIVE_MEMORY_MODEL", "")
        )
        model_kwargs: dict[str, Any] = {
            "model_id": model_id,
            "temperature": 0.1,
        }
        # 0 = 不限制（默认）：思考型模型 thinking 块先吃预算，固定小上限
        # 会把结构化输出截断；不传时用模型默认上限
        if max_tokens > 0:
            model_kwargs["max_tokens"] = max_tokens
        if model_value:
            model_kwargs["model"] = model_value
        return await LLMClient.get_model(
            **model_kwargs,
        )

    @bind_quota_user
    async def retain(
        self,
        user_id: str,
        content: str,
        context: Optional[str] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[list[str]] = None,
        existing_memory_id: Optional[str] = None,
        source_refs: Optional[Sequence[ConversationSourceRef | dict[str, str]]] = None,
        scope: Optional[str] = None,
        project_id: Optional[str] = None,
        expected_revision: Optional[dict[str, Any]] = None,
        source: Optional[str] = None,
        write_guard: Optional[Callable[[], Awaitable[bool]]] = None,
        origin_session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if source is not None and source not in {"manual", "auto_retained", "self_evolved"}:
            return {"success": False, "error": "Invalid memory source", "retryable": False}
        # --- Validation (relaxed for manual retention — trust user intent) ---
        if len(content.strip()) < 5:
            return {
                "success": False,
                "error": "Content too short (minimum 5 characters)",
                "retryable": False,
            }

        from src.infra.memory.scope import ScopeResolutionError, resolve_retain_scope

        requested_scope = scope
        try:
            scope, project_id = resolve_retain_scope(scope=scope, project_id=project_id)
        except ScopeResolutionError as exc:
            return {"success": False, "error": str(exc), "retryable": False}

        if not is_manual_memory_worthy(content, context):
            return {
                "success": False,
                "error": "Content rejected: appears transient, noisy, or not durable enough",
                "retryable": False,
            }

        memory_type = _infer_memory_type(context)
        revision_filter: dict[str, Any] = {
            key: expected_revision[key]
            for key in (
                "updated_at",
                "source",
                "scope",
                "project_id",
                "content_store_key",
                "revision_id",
            )
            if expected_revision is not None and key in expected_revision
        }

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

        from src.infra.memory.scope import build_dedup_scope_clause

        dedup_scope_clause = build_dedup_scope_clause(scope, project_id)

        async def fetch_recent_memories(target_user_id: str) -> list[dict[str, Any]]:
            seven_days_ago = utc_now() - timedelta(days=7)
            return await self._collection.find(
                {
                    "user_id": target_user_id,
                    "updated_at": {"$gte": seven_days_ago},
                    **dedup_scope_clause,
                },
                {"summary": 1, "memory_id": 1, "memory_type": 1},
            ).to_list(length=50)

        async def fetch_semantic_candidates(target_user_id: str) -> list[dict[str, Any]]:
            return await self._collection.find(
                {
                    "user_id": target_user_id,
                    "embedding": {"$exists": True, "$ne": None},
                    "source": {"$ne": "session_summary"},
                    **dedup_scope_clause,
                },
                {"memory_id": 1, "memory_type": 1, "summary": 1, "embedding": 1},
            ).to_list(length=200)

        embedding = None
        embedding_computed = False

        existing_match = None
        previous_content: tuple[str, bool] | None = None
        _match_projection = {
            "revision_id": 1,
            "origin_session_ids": 1,
            "memory_id": 1,
            "memory_type": 1,
            "user_id": 1,
            "content": 1,
            "title": 1,
            "summary": 1,
            "tags": 1,
            "context": 1,
            "source": 1,
            "embedding": 1,
            "scope": 1,
            "project_id": 1,
            "updated_at": 1,
            "content_storage_mode": 1,
            "content_store_key": 1,
            "source_refs": 1,
        }
        if existing_memory_id:
            forced_match = await self._collection.find_one(
                {
                    "user_id": user_id,
                    "memory_id": existing_memory_id,
                    **build_scope_clause(project_id),
                    **revision_filter,
                },
                _match_projection,
            )
            if forced_match:
                existing_match = forced_match
                # A project session can still update a visible user/reference
                # memory by ID. Preserve its existing ownership unless the
                # caller explicitly selected a new scope.
                if requested_scope is None:
                    existing_scope = existing_match.get("scope") or "user"
                    scope = existing_scope
                    project_id = (
                        existing_match.get("project_id") if existing_scope == "project" else None
                    )
        if expected_revision is not None and existing_match is None:
            return {"success": False, "error": "memory_changed_since_inventory", "retryable": False}
        if existing_memory_id and existing_match is None:
            return {"success": False, "error": "Memory not found", "retryable": False}
        if existing_match is None:
            existing_match = await find_existing_memory_match(
                fetch_recent=fetch_recent_memories,
                user_id=user_id,
                summary=summary,
                memory_type=memory_type,
            )
            if existing_match is None:
                from src.infra.memory.dedup_arbiter import resolve_semantic_match

                embedding = await self._maybe_embed(content)
                embedding_computed = True
                existing_match = await resolve_semantic_match(
                    fetch_candidates=fetch_semantic_candidates,
                    user_id=user_id,
                    query_embedding=embedding or [],
                    query_summary=summary,
                    memory_type=memory_type,
                )
            if existing_match:
                full_doc = await self._collection.find_one(
                    {"user_id": user_id, "memory_id": existing_match["memory_id"]},
                    _match_projection,
                )
                if full_doc:
                    existing_match.update(full_doc)
                previous_content = await hydrate_memory_text_status(self, existing_match)
                previous_text, complete = previous_content
                # Similarity locates candidates; only full equality authorizes an implicit update.
                if not complete or previous_text != content:
                    existing_match = None
                    previous_content = None

        now = utc_now()
        is_update = existing_match is not None
        _existing: dict[str, Any] = existing_match if is_update else {}  # type: ignore[assignment]
        memory_id = _existing["memory_id"] if is_update else uuid.uuid4().hex
        existing_source_refs = _existing.get("source_refs") or []
        incoming_source_refs = merge_source_refs([], source_refs)
        # Display limits must not erase an owned source needed by future forgetting.
        merged_source_refs = merge_source_refs(
            existing_source_refs,
            incoming_source_refs,
            limit=len(existing_source_refs) + len(incoming_source_refs),
        )
        if source_refs is not None:
            try:
                merged_source_refs = await ConversationHistoryService().validate_source_refs(
                    user_id, merged_source_refs, limit=len(merged_source_refs)
                )
            except Exception as exc:
                self._logger.warning(
                    "[NativeMemory] Source reference validation failed: %s",
                    type(exc).__name__,
                )
                raise
        source_ref_docs = [ref.model_dump() for ref in merged_source_refs[-MEMORY_SOURCE_REFS_MAX:]]
        origin_sessions = list(
            dict.fromkeys(
                [
                    *(_existing.get("origin_session_ids") or []),
                    *([origin_session_id] if origin_session_id else []),
                    *(ref.session_id for ref in merged_source_refs),
                ]
            )
        )
        if is_update:
            previous_text, complete = previous_content or await hydrate_memory_text_status(
                self, _existing
            )
            same_content = complete and previous_text == content
            unchanged_fields = {
                "title": title[:25],
                "summary": summary[:100],
                "tags": tags,
                "context": context,
                "scope": scope,
                "project_id": project_id,
                "source_refs": source_ref_docs,
                "origin_session_ids": origin_sessions,
            }
            if (
                expected_revision is None
                and write_guard is None
                and same_content
                and all(
                    _existing.get(
                        key,
                        "user" if key == "scope" else [] if key == "origin_session_ids" else None,
                    )
                    == value
                    for key, value in unchanged_fields.items()
                )
            ):
                return {
                    "success": True,
                    "memory_id": memory_id,
                    "memory_type": memory_type,
                    "scope": scope,
                    "project_id": project_id,
                    "updated_existing": True,
                    "unchanged": True,
                    "source": _existing.get("source", "manual"),
                    "message": "Memory already up to date",
                }
            if same_content and "embedding" in _existing:
                embedding = _existing["embedding"]
                embedding_computed = True
        if not embedding_computed:
            embedding = await self._maybe_embed(content)
        if not is_update and expected_revision is None:
            content_fields = await build_content_fields(self, user_id, memory_id, content)
        else:
            # Never reuse a body key that another writer may still be cleaning up.
            content_fields = await build_content_fields(
                self,
                user_id,
                memory_id,
                content,
                store_key=f"memory:{memory_id}:{uuid.uuid4().hex}",
            )

        if write_guard is not None:
            try:
                allowed = await write_guard()
            except (Exception, asyncio.CancelledError):
                await delete_memory_content(self, user_id, content_fields.get("content_store_key"))
                raise
            if not allowed:
                await delete_memory_content(self, user_id, content_fields.get("content_store_key"))
                return {"success": False, "error": "write_guard_rejected", "retryable": False}

        if is_update:
            from src.infra.memory.cleanup import content_update

            next_revision = uuid.uuid4().hex
            update = content_update(
                user_id,
                {
                    "title": title[:25],
                    "summary": summary[:100],
                    "index_label": build_index_label(title, summary, content),
                    "context": context,
                    "tags": tags,
                    "scope": scope,
                    "project_id": project_id,
                    "embedding": embedding,
                    "updated_at": now,
                    "revision_id": next_revision,
                    **vector_pending_fields(next_revision),
                    **content_fields,
                },
            )
            update[0]["$set"].update(
                memory_lineage_update_fields(
                    existing_source_refs, incoming_source_refs, merged_source_refs, origin_sessions
                )
            )
            try:
                write_result = await self._collection.update_one(
                    {
                        **content_commit_query(user_id, _existing["memory_id"], content_fields),
                        "user_id": user_id,
                        **revision_filter,
                    },
                    update,
                )
            except (Exception, asyncio.CancelledError):
                await self._invalidate_cache(user_id)
                raise
            if not int(
                getattr(write_result, "matched_count", 0 if expected_revision is not None else 1)
                or 0
            ):
                await delete_memory_content(self, user_id, content_fields.get("content_store_key"))
                return {
                    "success": False,
                    "error": "memory_changed_since_inventory"
                    if expected_revision is not None
                    else "Memory not found",
                    "retryable": False,
                }
            try:
                if (
                    _existing.get("content_storage_mode") == "store"
                    and _existing.get("content_store_key")
                    and _existing.get("content_store_key")
                    != content_fields.get("content_store_key")
                ):
                    await delete_memory_content(self, user_id, _existing.get("content_store_key"))
            finally:
                try:
                    await self._invalidate_cache(user_id)
                finally:
                    from src.infra.memory.cleanup import write_memory_vector

                    await write_memory_vector(
                        self,
                        user_id=user_id,
                        memory_id=_existing["memory_id"],
                        embedding=embedding,
                        memory_type=memory_type,
                        context=context,
                        updated_at_ts=int(now.timestamp()),
                        scope=scope,
                        project_id=project_id,
                    )
            return {
                "success": True,
                "memory_id": _existing["memory_id"],
                "memory_type": memory_type,
                "scope": scope,
                "project_id": project_id,
                "updated_existing": True,
                "message": "Memory updated successfully",
                **({"revision_id": next_revision} if expected_revision is not None else {}),
            }

        doc: dict[str, Any] = {
            "memory_id": memory_id,
            "user_id": user_id,
            "title": title[:25],
            "summary": summary[:100],
            "index_label": build_index_label(title, summary, content),
            "memory_type": memory_type,
            "context": context,
            "tags": tags,
            "scope": scope,
            "project_id": project_id,
            "source": source or "manual",
            "embedding": embedding,
            "created_at": now,
            "updated_at": now,
            "revision_id": uuid.uuid4().hex,
            "accessed_at": now,
            "access_count": 0,
            "source_refs": source_ref_docs,
            "origin_session_ids": origin_sessions,
        }
        doc.update(content_fields)
        doc.update(vector_pending_fields(doc["revision_id"]))

        try:
            await insert_content_memory(self, doc)
        except (Exception, asyncio.CancelledError):
            await self._invalidate_cache(user_id)
            raise
        if write_guard is not None:
            try:
                if not await write_guard():
                    raise RuntimeError("write_guard_rejected")
            except (Exception, asyncio.CancelledError):
                await self._delete_matching_memory(
                    user_id,
                    memory_id,
                    {"user_id": user_id, "memory_id": memory_id, "revision_id": doc["revision_id"]},
                    forget_sources=False,
                )
                raise
        # Invalidate index cache (local + distributed)
        await self._invalidate_cache(user_id)
        from src.infra.memory.cleanup import write_memory_vector

        await write_memory_vector(
            self,
            user_id=user_id,
            memory_id=memory_id,
            embedding=embedding,
            memory_type=memory_type,
            context=context,
            updated_at_ts=int(now.timestamp()),
            scope=scope,
            project_id=project_id,
        )

        return {
            "success": True,
            "memory_id": memory_id,
            "memory_type": memory_type,
            "scope": scope,
            "project_id": project_id,
            "message": "Memory stored successfully",
        }

    @bind_quota_user
    async def recall(
        self,
        user_id: str,
        query: str,
        max_results: int = 5,
        memory_types: Optional[list[str]] = None,
        context_filter: Optional[str] = None,
        project_id: Optional[str] = None,
        *,
        touch_access: bool = True,
        enable_rerank: bool = True,
    ) -> dict[str, Any]:
        return await recall_memories(
            self,
            user_id,
            query,
            max_results,
            memory_types,
            touch_access=touch_access,
            enable_rerank=enable_rerank,
            context_filter=context_filter,
            project_id=project_id,
        )

    async def delete(
        self,
        user_id: str,
        memory_id: str,
        *,
        expected_revision: Optional[dict[str, Any]] = None,
        write_guard: Optional[Callable[[], Awaitable[bool]]] = None,
    ) -> dict[str, Any]:
        return await self._delete_matching_memory(
            user_id,
            memory_id,
            {
                "user_id": user_id,
                "memory_id": memory_id,
                **{
                    key: expected_revision[key]
                    for key in (
                        "updated_at",
                        "source",
                        "scope",
                        "project_id",
                        "content_store_key",
                        "revision_id",
                    )
                    if expected_revision is not None and key in expected_revision
                },
            },
            write_guard=write_guard,
            forget_sources=expected_revision is None,
        )

    async def delete_scoped(
        self,
        user_id: str,
        memory_id: str,
        *,
        project_id: Optional[str],
    ) -> dict[str, Any]:
        """Delete only memories visible in the current project scope."""
        return await self._delete_matching_memory(
            user_id,
            memory_id,
            {
                "user_id": user_id,
                "memory_id": memory_id,
                **build_scope_clause(project_id),
            },
        )

    async def _delete_matching_memory(
        self,
        user_id: str,
        memory_id: str,
        query: dict[str, Any],
        *,
        write_guard: Optional[Callable[[], Awaitable[bool]]] = None,
        forget_sources: bool = True,
    ) -> dict[str, Any]:
        if write_guard is not None and not await write_guard():
            return {"success": False, "error": "write_guard_rejected", "retryable": False}
        from src.infra.memory.cleanup import delete_memory_vector, prepare_deleted_resources

        before = await self._collection.find_one(
            query,
            {
                "memory_id": 1,
                "source_refs": 1,
                "origin_session_ids": 1,
                "revision_id": 1,
                "content_storage_mode": 1,
                "content_store_key": 1,
                "_content_cleanup": 1,
                "_content_stages": 1,
            },
        )
        if before is None:
            return {"success": False, "error": "Memory not found"}
        if forget_sources:
            from src.infra.memory.forgetting import suppress_deleted_sources

            await suppress_deleted_sources(self, user_id, before)
        await prepare_deleted_resources(self, user_id, memory_id, before)
        if write_guard is not None and not await write_guard():
            return {"success": False, "error": "write_guard_rejected", "retryable": False}
        query = {**query, "revision_id": before.get("revision_id")}
        if getattr(self._collection, "database", None) is not None:
            query["_content_stages"] = before.get("_content_stages", {"$exists": False})
        try:
            existing_doc = await self._collection.find_one_and_delete(
                query,
                projection={"content_storage_mode": 1, "content_store_key": 1},
            )
        except (Exception, asyncio.CancelledError):
            await self._invalidate_cache(user_id)
            raise
        if existing_doc is not None:
            try:
                if existing_doc.get("content_storage_mode") == "store":
                    await delete_memory_content(
                        self, user_id, existing_doc.get("content_store_key")
                    )
            finally:
                try:
                    await self._invalidate_cache(user_id)
                finally:
                    await delete_memory_vector(self, user_id, memory_id)
            return {"success": True, "message": f"Memory {memory_id} deleted"}
        return {"success": False, "error": "Memory not found"}

    async def build_memory_index(self, user_id: str, project_id: Optional[str] = None) -> str:
        return await build_memory_index(self, user_id, project_id=project_id)

    async def _update_access_stats(self, memory_ids: list[str], user_id: str = "") -> None:
        query: dict[str, Any] = {"memory_id": {"$in": memory_ids}}
        if user_id:
            query["user_id"] = user_id
        await self._collection.update_many(
            query,
            {
                "$set": {"accessed_at": utc_now()},
                "$inc": {"access_count": 1},
            },
        )

    async def _maybe_embed(self, text: str) -> Optional[list[float]]:
        if not self._embedding_fn:
            return None
        try:
            # embedding fn 是 httpx.AsyncClient 协程：直接 await，零线程；
            # 同步 fn 兜底才走慢道
            if inspect.iscoroutinefunction(self._embedding_fn):
                return await self._embedding_fn(text)
            result = await run_long_blocking_io(self._embedding_fn, text)
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as e:
            if is_quota_error(e):
                raise
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
        sync_col = get_mongo_sync_client()[settings.MONGODB_DB][COLLECTION_NAME]
        await run_long_blocking_io(self._create_indexes_sync, sync_col)

    @staticmethod
    def _create_indexes_sync(col: Any) -> None:
        for name, (keys, partial) in CONTENT_INDEXES.items():
            col.create_index(keys, name=name, partialFilterExpression=partial)
        for name, keys in VECTOR_PENDING_INDEXES.items():
            col.create_index(
                keys,
                name=name,
                partialFilterExpression={"_vector_pending": {"$exists": True}},
            )
        col.create_index(
            [("user_id", 1), ("memory_type", 1), ("created_at", -1)],
            name="native_mem_user_type_idx",
        )
        col.create_index(
            [("user_id", 1), ("memory_type", 1), ("updated_at", -1)],
            name="native_mem_user_type_recency_idx",
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
                [
                    ("user_id", 1),
                    ("content", "text"),
                    ("summary", "text"),
                    ("tags", "text"),
                ],
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
        try:
            col.create_index(
                [("user_id", 1), ("scope", 1), ("project_id", 1)],
                name="native_mem_scope_idx",
            )
        except Exception as e:
            logger.warning(f"[NativeMemory] Scope index creation skipped: {e}")

    async def _maybe_create_vector_index(self) -> None:
        """Best-effort 创建 vectorSearch 索引（MongoDB 8.2+ 社区版内置）。

        未配置 embedding 或服务器无 mongot 时静默跳过——检索侧已有
        Python 余弦兜底（search.vector_search fallback）。
        """
        if self._embedding_fn is None:
            return
        try:
            sync_col = get_mongo_sync_client()[settings.MONGODB_DB][COLLECTION_NAME]
            await run_long_blocking_io(self._create_vector_index_sync, sync_col)
        except Exception as e:
            logger.warning(f"[NativeMemory] Vector index setup skipped: {e}")

    @staticmethod
    def _create_vector_index_sync(col: Any) -> None:
        existing = [ix.get("name") for ix in col.list_search_indexes()]
        if "native_mem_vector_idx" in existing:
            return
        dimensions = int(getattr(settings, "NATIVE_MEMORY_EMBEDDING_DIMENSIONS", 1536))
        col.create_search_index(
            {
                "name": "native_mem_vector_idx",
                "type": "vectorSearch",
                "definition": {
                    "fields": [
                        {
                            "type": "vector",
                            "path": "embedding",
                            "numDimensions": dimensions,
                            "similarity": "cosine",
                        }
                    ]
                },
            }
        )
        logger.info(
            "[NativeMemory] Vector index creation requested (native_mem_vector_idx, %d dims)",
            dimensions,
        )

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
                # httpx 连接池默认 5s 闲置断连：每条隔闲消息重付 ~1.5s TLS 握手，
                # 恰好击穿 1.5s 的查询上下文注入预算（staging 实测冷 1.99s→热 0.44s）
                limits=httpx.Limits(keepalive_expiry=60.0),
            )

            async def embed_fn(text: str) -> list[float]:
                async with unpriced_usage():
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
