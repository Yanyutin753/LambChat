"""
Checkpoint 存储实现

提供 LangGraph checkpointer 的工厂函数，支持 MongoDB 和 PostgreSQL 持久化。

用户通过 CHECKPOINT_BACKEND 配置选择后端：
- "mongodb": 使用 MongoDBSaver（默认，受 16MB 文档大小限制）
- "postgres": 使用 AsyncPostgresSaver + 连接池（无文档大小限制，需 PostgreSQL 连接参数）

两者都不可用时回退到 MemorySaver（内存存储，重启丢失）。
"""

import asyncio
import copy
import inspect
import random
import time
from collections import OrderedDict
from types import MethodType
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    empty_checkpoint,
)

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

_MEMORY_SAVER_MAX_THREADS = max(int(getattr(settings, "MEMORY_SAVER_MAX_THREADS", 200) or 0), 1)
_MEMORY_SAVER_TTL_SECONDS = max(
    int(getattr(settings, "MEMORY_SAVER_TTL_SECONDS", 3600) or 0),
    1,
)
_MEMORY_SAVER_CLEANUP_INTERVAL = max(
    int(getattr(settings, "MEMORY_SAVER_CLEANUP_INTERVAL", 50) or 0),
    1,
)
_FORK_CHECKPOINT_SCAN_PAGE_SIZE = 25
_DISABLED_CHECKPOINT_BACKENDS = {"", "0", "false", "none", "off", "disabled"}

# MongoDB Checkpointer 单例
_mongo_checkpointer: Optional[BaseCheckpointSaver[Any]] = None

# PostgreSQL Checkpointer 单例
_pg_checkpointer: Optional[BaseCheckpointSaver[Any]] = None
_pg_checkpointer_pool: Any | None = None
_pg_checkpointer_lock: asyncio.Lock | None = None


def _ensure_string_channel_version_support(
    checkpointer: BaseCheckpointSaver[Any],
) -> BaseCheckpointSaver[Any]:
    """Patch savers that still inherit LangGraph's int-only version generator."""
    if type(checkpointer).get_next_version is not BaseCheckpointSaver.get_next_version:
        return checkpointer

    def _get_next_version(self: BaseCheckpointSaver[Any], current: Any, channel: None) -> Any:
        del self, channel
        if isinstance(current, str):
            current_v = int(current.split(".", 1)[0])
            next_v = current_v + 1
            next_h = random.random()
            return f"{next_v:032}.{next_h:016}"
        if current is None:
            return 1
        return current + 1

    checkpointer.get_next_version = MethodType(_get_next_version, checkpointer)  # type: ignore[method-assign]
    return checkpointer


def _get_pg_checkpointer_lock() -> asyncio.Lock:
    global _pg_checkpointer_lock

    if _pg_checkpointer_lock is None:
        _pg_checkpointer_lock = asyncio.Lock()
    return _pg_checkpointer_lock


def _cleanup_memory_saver_cache(now: float | None = None) -> int:
    cache: OrderedDict[str, tuple[object, float]] | None = getattr(
        get_async_checkpointer,
        "_memory_saver_cache",
        None,
    )
    if not cache:
        return 0

    current_time = time.time() if now is None else now
    removed = 0

    stale_threads = [
        thread_id
        for thread_id, (_, last_access) in list(cache.items())
        if current_time - last_access > _MEMORY_SAVER_TTL_SECONDS
    ]
    for thread_id in stale_threads:
        cache.pop(thread_id, None)
        removed += 1

    while len(cache) > _MEMORY_SAVER_MAX_THREADS:
        cache.popitem(last=False)
        removed += 1

    if not cache and hasattr(get_async_checkpointer, "_memory_saver_cache"):
        delattr(get_async_checkpointer, "_memory_saver_cache")

    return removed


def close_async_checkpointer() -> None:
    """Release MemorySaver fallback references so the process can reclaim memory."""
    if hasattr(get_async_checkpointer, "_memory_saver"):
        delattr(get_async_checkpointer, "_memory_saver")
    if hasattr(get_async_checkpointer, "_memory_saver_cache"):
        delattr(get_async_checkpointer, "_memory_saver_cache")
    if hasattr(get_async_checkpointer, "_memory_saver_access_count"):
        delattr(get_async_checkpointer, "_memory_saver_access_count")


def get_checkpointer_diagnostics() -> dict[str, Any]:
    """Return lightweight checkpointer runtime state for memory diagnostics."""
    cache: OrderedDict[str, tuple[object, float]] | None = getattr(
        get_async_checkpointer,
        "_memory_saver_cache",
        None,
    )
    return {
        "configured_backend": str(getattr(settings, "CHECKPOINT_BACKEND", "mongodb")),
        "backend_enabled": is_checkpoint_backend_enabled(),
        "mongo_checkpointer_active": _mongo_checkpointer is not None,
        "postgres_checkpointer_active": _pg_checkpointer is not None,
        "postgres_pool_active": _pg_checkpointer_pool is not None,
        "memory_saver_singleton_active": hasattr(get_async_checkpointer, "_memory_saver"),
        "memory_saver_cache_active": cache is not None,
        "memory_saver_cache_size": len(cache or {}),
        "memory_saver_cache_limit": _MEMORY_SAVER_MAX_THREADS,
        "memory_saver_ttl_seconds": _MEMORY_SAVER_TTL_SECONDS,
    }


async def reset_checkpointer_runtime_state() -> None:
    """Drop process-local checkpointer references after checkpoint settings change."""
    close_async_checkpointer()
    close_mongo_checkpointer()
    await close_pg_checkpointer()


def get_mongo_checkpointer(collection_name: str = "checkpoints") -> BaseCheckpointSaver[Any] | None:
    """
    获取 MongoDB checkpointer 单例

    复用 motor 的底层同步 MongoClient，避免创建独立的同步连接池。

    Args:
        collection_name: MongoDB collection 名称，默认为 "checkpoints"

    Returns:
        MongoDBSaver 实例，如果创建失败则返回 None
    """
    global _mongo_checkpointer
    if _mongo_checkpointer is not None:
        return _mongo_checkpointer

    try:
        from langgraph.checkpoint.mongodb import MongoDBSaver

        from src.infra.storage.mongodb import get_mongo_client

        motor_client = get_mongo_client()
        sync_client = motor_client.delegate

        cp = MongoDBSaver(
            sync_client,
            db_name=settings.MONGODB_DB,
            checkpoint_collection_name=collection_name,
        )

        logger.info(
            f"MongoDB checkpointer created: {settings.MONGODB_DB}.{collection_name} (reusing motor connection pool)"
        )
        _mongo_checkpointer = cp
        return _mongo_checkpointer

    except ImportError as e:
        logger.warning(f"MongoDB checkpointer not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to create MongoDB checkpointer: {e}")
        return None


def close_mongo_checkpointer():
    """释放 MongoDB checkpointer 单例引用，允许 GC 回收。"""
    global _mongo_checkpointer
    if _mongo_checkpointer is not None:
        _mongo_checkpointer = None
        logger.info("MongoDB checkpointer reference released")


def is_checkpoint_backend_enabled() -> bool:
    """Return whether persistent checkpoint storage is configured."""
    backend = str(getattr(settings, "CHECKPOINT_BACKEND", "mongodb") or "").strip().lower()
    return backend not in _DISABLED_CHECKPOINT_BACKENDS


async def get_pg_checkpointer() -> BaseCheckpointSaver[Any] | None:
    """
    获取 PostgreSQL checkpointer 单例（异步）

    使用 AsyncPostgresSaver + AsyncConnectionPool，无 16MB 文档大小限制。
    仅需 CHECKPOINT_BACKEND=postgres，独立于 ENABLE_POSTGRES_STORAGE。

    Returns:
        AsyncPostgresSaver 实例，如果创建失败则返回 None
    """
    global _pg_checkpointer, _pg_checkpointer_pool

    if _pg_checkpointer is not None:
        return _pg_checkpointer

    async with _get_pg_checkpointer_lock():
        if _pg_checkpointer is not None:
            return _pg_checkpointer

        return await _create_pg_checkpointer()


async def _create_pg_checkpointer() -> BaseCheckpointSaver[Any] | None:
    global _pg_checkpointer, _pg_checkpointer_pool

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool: AsyncConnectionPool[AsyncConnection[dict[str, Any]]] = AsyncConnectionPool(
            settings.checkpoint_postgres_url,
            min_size=settings.CHECKPOINT_PG_POOL_MIN_SIZE,
            max_size=settings.CHECKPOINT_PG_POOL_MAX_SIZE,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            open=False,
        )
        try:
            await pool.open(wait=True)
        except Exception:
            await pool.close()
            raise

        cp = AsyncPostgresSaver(pool)
        try:
            await cp.setup()
            logger.info(
                "PostgreSQL checkpointer created (AsyncPostgresSaver via connection pool, min=%d, max=%d)",
                settings.CHECKPOINT_PG_POOL_MIN_SIZE,
                settings.CHECKPOINT_PG_POOL_MAX_SIZE,
            )
            _pg_checkpointer_pool = pool
            _pg_checkpointer = cp
            return _pg_checkpointer
        except Exception:
            await pool.close()
            raise

    except ImportError as e:
        logger.warning(f"PostgreSQL checkpointer not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to create PostgreSQL checkpointer: {e}")
        return None


async def close_pg_checkpointer():
    """
    关闭 PostgreSQL checkpointer（释放连接）

    应在应用关闭时调用。
    """
    global _pg_checkpointer, _pg_checkpointer_pool

    async with _get_pg_checkpointer_lock():
        pool = _pg_checkpointer_pool
        if _pg_checkpointer is None and pool is None:
            return

        try:
            if pool is not None:
                await pool.close()
            logger.info("PostgreSQL checkpointer closed")
        except Exception as e:
            logger.warning(f"Error closing PostgreSQL checkpointer: {e}")
        finally:
            _pg_checkpointer = None
            _pg_checkpointer_pool = None


async def get_async_checkpointer(thread_id: str | None = None) -> BaseCheckpointSaver[Any]:
    """
    获取 checkpointer 实例（兼容异步调用）

    根据 CHECKPOINT_BACKEND 配置选择后端：
    - "postgres": 优先使用 PostgreSQL（无 16MB 限制）
    - "mongodb": 使用 MongoDB（默认）
    - 都不可用: 回退到 MemorySaver

    Args:
        thread_id: 可选的会话/线程 ID。仅在 MemorySaver fallback 时使用，
            用于按线程复用并限制进程内缓存规模。

    Returns:
        Checkpointer 实例
    """
    backend = getattr(settings, "CHECKPOINT_BACKEND", "mongodb")

    if backend == "postgres":
        logger.info("Using PostgreSQL checkpointer")
        checkpointer = await get_pg_checkpointer()
        if checkpointer is not None:
            return checkpointer
        logger.warning("PostgreSQL checkpointer unavailable, falling back")

    # MongoDB (default)
    logger.info("Using MongoDB checkpointer")
    checkpointer = get_mongo_checkpointer()
    if checkpointer is None:
        logger.warning("MongoDB checkpointer unavailable, falling back")
    if checkpointer is not None:
        return _ensure_string_channel_version_support(checkpointer)

    # MemorySaver fallback
    from langgraph.checkpoint.memory import MemorySaver

    if thread_id:
        if not hasattr(get_async_checkpointer, "_memory_saver_cache"):
            get_async_checkpointer._memory_saver_cache = OrderedDict()  # type: ignore[attr-defined]
            get_async_checkpointer._memory_saver_access_count = 0  # type: ignore[attr-defined]
            logger.warning(
                "Using thread-scoped MemorySaver fallback cache (data will be lost on restart)"
            )

        cache: OrderedDict[str, tuple[MemorySaver, float]] = getattr(
            get_async_checkpointer,
            "_memory_saver_cache",
        )
        access_count = getattr(get_async_checkpointer, "_memory_saver_access_count", 0) + 1
        get_async_checkpointer._memory_saver_access_count = access_count  # type: ignore[attr-defined]
        if access_count % _MEMORY_SAVER_CLEANUP_INTERVAL == 0:
            _cleanup_memory_saver_cache()

        now = time.time()
        cached = cache.get(thread_id)
        if cached is not None:
            saver, _ = cached
            cache.move_to_end(thread_id)
            cache[thread_id] = (saver, now)
            return saver

        saver = MemorySaver()
        cache[thread_id] = (saver, now)
        _cleanup_memory_saver_cache(now=now)
        return saver

    if not hasattr(get_async_checkpointer, "_memory_saver"):
        get_async_checkpointer._memory_saver = MemorySaver()  # type: ignore[attr-defined]
        logger.warning("Using MemorySaver singleton (data will be lost on restart)")
    return get_async_checkpointer._memory_saver  # type: ignore[attr-defined]


def _is_human_message(message: object) -> bool:
    return type(message).__name__ == "HumanMessage"


def _is_ai_message(message: object) -> bool:
    return type(message).__name__ == "AIMessage"


def _extract_checkpoint_messages(checkpoint_tuple: CheckpointTuple) -> list[object]:
    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
    messages = channel_values.get("messages", [])
    return messages if isinstance(messages, list) else []


def _matches_fork_boundary(
    checkpoint_tuple: CheckpointTuple, *, turn_index: int, target_type: str
) -> bool:
    messages = _extract_checkpoint_messages(checkpoint_tuple)
    human_count = sum(1 for message in messages if _is_human_message(message))
    if human_count != turn_index or not messages:
        return False

    last_message = messages[-1]
    if target_type == "user":
        return _is_human_message(last_message)
    if target_type == "assistant":
        return _is_ai_message(last_message)
    return False


def _copy_checkpoint_put_payload(
    checkpoint_tuple: CheckpointTuple,
) -> tuple[Checkpoint, CheckpointMetadata, ChannelVersions]:
    checkpoint = copy.deepcopy(checkpoint_tuple.checkpoint)
    metadata = copy.deepcopy(checkpoint_tuple.metadata)
    channel_versions = copy.deepcopy(checkpoint_tuple.checkpoint.get("channel_versions", {}))
    return checkpoint, metadata, channel_versions


async def _find_fork_boundary_checkpoint(
    source_saver: BaseCheckpointSaver[Any],
    default_config: RunnableConfig,
    *,
    turn_index: int,
    target_type: str,
) -> CheckpointTuple | None:
    before_config: RunnableConfig | None = None

    while True:
        page = [
            item
            async for item in source_saver.alist(
                default_config,
                before=before_config,
                limit=_FORK_CHECKPOINT_SCAN_PAGE_SIZE,
            )
        ]
        if not page:
            return None

        for checkpoint_tuple in page:
            if _matches_fork_boundary(
                checkpoint_tuple,
                turn_index=turn_index,
                target_type=target_type,
            ):
                return checkpoint_tuple

        last_config = getattr(page[-1], "config", None)
        if not last_config:
            return None
        before_config = last_config


async def clone_checkpoints_for_fork(
    source_thread_id: str,
    target_thread_id: str,
    *,
    turn_index: int,
    target_type: str,
) -> int:
    """Clone checkpoint state up to the fork boundary into a new thread."""
    source_saver = await get_async_checkpointer(thread_id=source_thread_id)
    target_saver = await get_async_checkpointer(thread_id=target_thread_id)
    default_config: RunnableConfig = {
        "configurable": {"thread_id": source_thread_id, "checkpoint_ns": ""}
    }
    boundary_tuple = await _find_fork_boundary_checkpoint(
        source_saver,
        default_config,
        turn_index=turn_index,
        target_type=target_type,
    )

    if boundary_tuple is None:
        raise ValueError(
            f"Unable to locate fork checkpoint for thread={source_thread_id} turn={turn_index} type={target_type}"
        )

    cfg = boundary_tuple.config["configurable"]
    target_config: RunnableConfig = {
        "configurable": {
            "thread_id": target_thread_id,
            "checkpoint_ns": cfg.get("checkpoint_ns", ""),
        }
    }
    checkpoint, metadata, channel_versions = await run_blocking_io(
        _copy_checkpoint_put_payload,
        boundary_tuple,
    )
    await target_saver.aput(
        target_config,
        checkpoint,
        metadata,
        channel_versions,
    )
    return 1


async def seed_checkpoint_from_messages(
    target_thread_id: str,
    messages: list[object],
) -> int:
    """Seed a fork with a minimal message checkpoint when source checkpoints are absent."""
    if not messages:
        return 0

    target_saver = await get_async_checkpointer(thread_id=target_thread_id)
    checkpoint = empty_checkpoint()
    copied_messages = await run_blocking_io(copy.deepcopy, messages)
    checkpoint["channel_values"] = {"messages": copied_messages}
    checkpoint["channel_versions"] = {"messages": "1"}
    checkpoint["versions_seen"] = {}
    checkpoint["updated_channels"] = ["messages"]

    await target_saver.aput(
        {"configurable": {"thread_id": target_thread_id, "checkpoint_ns": ""}},
        checkpoint,
        {"source": "fork", "step": 0},
        checkpoint["channel_versions"],
    )
    return 1


async def delete_checkpoints_for_thread(thread_id: str) -> None:
    """Delete persisted checkpoint state for a LangGraph thread/session."""
    if not thread_id or not is_checkpoint_backend_enabled():
        return

    saver = await get_async_checkpointer(thread_id=thread_id)
    async_delete = getattr(saver, "adelete_thread", None)
    if callable(async_delete):
        await async_delete(thread_id)
        return

    sync_delete = getattr(saver, "delete_thread", None)
    if callable(sync_delete):
        result = await run_blocking_io(sync_delete, thread_id)
        if inspect.isawaitable(result):
            await result
        return

    logger.warning("Checkpointer does not support thread deletion: %s", type(saver).__name__)


def build_messages_from_trace_events(traces: list[dict]) -> list[object]:
    """Build a minimal chat message list from persisted trace events."""
    messages: list[object] = []
    for trace in traces:
        assistant_chunks: list[str] = []
        for event in trace.get("events", []):
            event_type = event.get("event_type")
            data = event.get("data") or {}
            if event_type == "user:message":
                content = str(data.get("content") or data.get("message") or "")
                if content:
                    messages.append(HumanMessage(content=content))
            elif event_type == "message:chunk":
                content = str(data.get("content") or "")
                if content:
                    assistant_chunks.append(content)

        assistant_content = "".join(assistant_chunks)
        if assistant_content:
            messages.append(AIMessage(content=assistant_content))

    return messages
