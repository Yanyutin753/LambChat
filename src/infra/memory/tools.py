"""
Unified Memory Tools - LangChain Tool Integration

Provides a single set of memory tools that work with any MemoryBackend.
The underlying backend is transparent to the Agent — tool names and interfaces
are identical regardless of which memory provider is active.
"""

import asyncio
import json
import uuid
from typing import Annotated, Any, Optional, Sequence

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from langsmith.run_helpers import tracing_context

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.memory.client.base import (
    MemoryBackend,
    create_memory_backend,
    get_user_id_from_runtime,
)
from src.infra.memory.compaction_agent import (
    get_memory_compaction_agent,
    stop_memory_compaction_agent,
)
from src.infra.memory.user_pref import user_memory_enabled
from src.infra.scheduler import ScheduledJob, get_runtime_scheduler
from src.kernel.config import settings
from src.kernel.schemas.conversation_history import ConversationSourceRef

logger = get_logger(__name__)


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


# Module-level cached backend (initialized lazily)
_backend: Optional[MemoryBackend] = None
_backend_lock: Optional[asyncio.Lock] = None
_backend_lock_loop: Optional[asyncio.AbstractEventLoop] = None
_backend_reset_task: Optional[asyncio.Task] = None
_background_tasks: set[asyncio.Task] = set()
_auto_capture_tasks_by_user: dict[str, asyncio.Task] = {}
_auto_capture_user_locks: dict[str, asyncio.Lock] = {}
_AUTO_CAPTURE_LOCKS_MAX = 500  # Prevent unbounded lock accumulation
_AUTO_CAPTURE_INPUT_MAX_CHARS = 8000
_AUTO_CAPTURE_MAX_TASKS = 8


def _get_auto_capture_lock_fns():
    from src.infra.memory.distributed import acquire_auto_capture_lock, release_auto_capture_lock

    return acquire_auto_capture_lock, release_auto_capture_lock


def _cleanup_local_auto_capture_lock(user_id: str, lock: asyncio.Lock) -> None:
    waiters = getattr(lock, "_waiters", None)
    has_waiters = bool(waiters) if waiters is not None else False
    if not lock.locked() and not has_waiters:
        current = _auto_capture_user_locks.get(user_id)
        if current is lock:
            _auto_capture_user_locks.pop(user_id, None)


def _evict_idle_auto_capture_locks() -> None:
    """Evict idle locks when the dict grows too large."""
    if len(_auto_capture_user_locks) <= _AUTO_CAPTURE_LOCKS_MAX:
        return
    idle_users = [
        uid
        for uid, lock in _auto_capture_user_locks.items()
        if not lock.locked() and not getattr(lock, "_waiters", None)
    ]
    for uid in idle_users[: len(_auto_capture_user_locks) // 4]:
        _auto_capture_user_locks.pop(uid, None)


def _get_backend_lock() -> asyncio.Lock:
    """Get or create the backend lock for the current event loop.

    Recreates the lock if the event loop has changed (e.g. after uvicorn reload).
    """
    global _backend_lock, _backend_lock_loop
    current_loop = asyncio.get_running_loop()
    if _backend_lock is None or _backend_lock_loop is not current_loop:
        _backend_lock = asyncio.Lock()
        _backend_lock_loop = current_loop
    return _backend_lock


def _clip_auto_capture_input(user_input: str) -> str:
    max_chars = max(
        int(
            getattr(
                settings,
                "NATIVE_MEMORY_AUTO_CAPTURE_INPUT_MAX_CHARS",
                _AUTO_CAPTURE_INPUT_MAX_CHARS,
            )
            or 0
        ),
        1,
    )
    if len(user_input) <= max_chars:
        return user_input
    return (
        user_input[:max_chars].rstrip()
        + f"\n\n[truncated from {len(user_input)} chars for auto memory capture]"
    )


def _get_auto_capture_max_tasks() -> int:
    return max(
        int(
            getattr(
                settings,
                "NATIVE_MEMORY_AUTO_CAPTURE_MAX_TASKS",
                _AUTO_CAPTURE_MAX_TASKS,
            )
            or 0
        ),
        1,
    )


async def _get_backend() -> Optional[MemoryBackend]:
    """Get or create the active memory backend (singleton)."""
    global _backend
    if _backend is not None:
        return _backend

    async with _get_backend_lock():
        if _backend is None:
            _backend = await create_memory_backend()
            if _backend is None:
                logger.warning(
                    "[Memory] No backend available (ENABLE_MEMORY=%s)",
                    settings.ENABLE_MEMORY,
                )
            else:
                logger.info("[Memory] Backend initialized: %s", _backend.name)
        return _backend


# ============================================================================
# Unified Memory Tools
# ============================================================================


@tool
async def memory_retain(
    content: Annotated[str, "The memory content to store (facts, observations, experiences)"],
    title: Annotated[
        Optional[str],
        "Short title for this memory (max 25 chars, e.g. 'Go expert new to React', 'prefers raw SQL')",
    ] = None,
    summary: Annotated[
        Optional[str],
        "Brief summary of this memory (max 80 chars)",
    ] = None,
    context: Annotated[
        Optional[str],
        "Optional context or category for this memory (e.g., 'user_identity', 'project_constraint', 'feedback_rule', 'reference_link')",
    ] = None,
    tags: Annotated[
        Optional[list[str]],
        "Optional keyword tags for this memory (e.g., ['Go', 'React', 'newcomer']). Max 5 tags.",
    ] = None,
    existing_memory_id: Annotated[
        Optional[str],
        "Optional existing memory ID to update instead of relying on fuzzy deduplication.",
    ] = None,
    source_refs: Annotated[
        Optional[list[ConversationSourceRef]],
        "Conversation sources for this memory. Use only session_id/run_id pairs returned by conversation history tools or memory_recall; never invent IDs.",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Store a memory for cross-session persistence. STRICT: only genuinely useful,
    non-temporary information is accepted. Content that is too short or resembles
    code/commands will be rejected. If a semantically similar memory already exists
    it is merged and updated automatically (result `updated_existing` is true), so
    write the FULL refreshed content including previously known details, not just
    the delta. Prefer storing high-signal facts like user preferences, project
    context, feedback, or external references. Use explicit context labels such as
    `user_identity`, `project_constraint`, `project_status`, `feedback_rule`, or
    `reference_link` instead of vague buckets like `user_preferences`.
    When a durable fact came from conversation history, preserve its authorized
    `source_refs`. Later, memory_recall returns these pointers and the SOP is to call
    get_conversation_detail for the original final answer.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return await _json_dumps_result({"success": False, "error": "User not authenticated"})
    if not await user_memory_enabled(user_id):
        return await _json_dumps_result({"success": False, "error": "memory_disabled_for_user"})

    backend = await _get_backend()
    if not backend:
        return await _json_dumps_result({"success": False, "error": "Memory service not available"})

    try:
        result = await backend.retain(
            user_id,
            content,
            context,
            title=title,
            summary=summary,
            tags=tags,
            existing_memory_id=existing_memory_id,
            source_refs=source_refs,
        )
        return await _json_dumps_result(result)
    except Exception as e:
        logger.error(f"[Memory] Failed to retain memory: {e}")
        return await _json_dumps_result({"success": False, "error": str(e)})


@tool
async def memory_recall(
    query: Annotated[str, "The search query to find relevant memories"],
    max_results: Annotated[int, "Maximum number of memories to return (default: 5)"] = 5,
    memory_types: Annotated[
        Optional[list[str]],
        "Filter by memory types (backend-specific), or None for all types",
    ] = None,
    context: Annotated[
        Optional[str],
        "Optional exact-match context scope filter (e.g. 'project_constraint'), or None for all scopes",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Search and retrieve relevant memories from cross-session storage.

    Use this tool to recall previously stored information. The search is
    semantic and will find memories that are conceptually related to the query.
    SOP for evidence: when a recalled memory contains `source_refs`, use each
    authorized `session_id` and `run_id` with get_conversation_detail to inspect
    the original final answer. Treat the memory as a locator/summary and the
    conversation detail as the source of truth.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return await _json_dumps_result({"success": False, "error": "User not authenticated"})
    if not await user_memory_enabled(user_id):
        return await _json_dumps_result({"success": False, "error": "memory_disabled_for_user"})

    backend = await _get_backend()
    if not backend:
        return await _json_dumps_result({"success": False, "error": "Memory service not available"})

    try:
        result = await backend.recall(user_id, query, max_results, memory_types, context)
        return await _json_dumps_result(result)
    except Exception as e:
        logger.error(f"[Memory] Failed to recall memories: {e}")
        return await _json_dumps_result({"success": False, "error": str(e)})


@tool
async def memory_delete(
    memory_id: Annotated[str, "The ID of the memory to delete"],
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Delete a specific memory by ID.

    Use this tool when a user wants to remove a specific memory.
    Get the memory ID from the memory_recall tool output.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return await _json_dumps_result({"success": False, "error": "User not authenticated"})
    if not await user_memory_enabled(user_id):
        return await _json_dumps_result({"success": False, "error": "memory_disabled_for_user"})

    backend = await _get_backend()
    if not backend:
        return await _json_dumps_result({"success": False, "error": "Memory service not available"})

    try:
        result = await backend.delete(user_id, memory_id)
        return await _json_dumps_result(result)
    except Exception as e:
        logger.error(f"[Memory] Failed to delete memory: {e}")
        return await _json_dumps_result({"success": False, "error": str(e)})


# ============================================================================
# Tool Factory Functions
# ============================================================================


def get_memory_retain_tool() -> BaseTool:
    return memory_retain


def get_memory_recall_tool() -> BaseTool:
    return memory_recall


def get_memory_delete_tool() -> BaseTool:
    return memory_delete


def get_all_memory_tools() -> list[BaseTool]:
    """Get all unified memory tools (works with any backend)."""
    return [memory_retain, memory_recall, memory_delete]


def _background_task_error(task: asyncio.Task) -> None:
    """Handle exceptions from background tasks."""
    try:
        exc = task.exception()
        if exc:
            logger.warning(f"[Memory] Background task failed: {exc}")
    except asyncio.CancelledError:
        pass


def _auto_capture_task_done(user_id: str, task: asyncio.Task) -> None:
    current = _auto_capture_tasks_by_user.get(user_id)
    if current is task:
        _auto_capture_tasks_by_user.pop(user_id, None)
    _background_tasks.discard(task)
    _background_task_error(task)


async def _auto_retain_user_memory(
    user_id: str,
    user_input: str,
    source_refs: Optional[Sequence[ConversationSourceRef | dict[str, str]]] = None,
) -> None:
    if not user_id or not user_input.strip():
        return
    if not await user_memory_enabled(user_id):
        logger.debug("[Memory] Auto-capture skipped: memory disabled by user %s", user_id)
        return
    lock = _auto_capture_user_locks.get(user_id)
    if lock is None:
        _evict_idle_auto_capture_locks()
        lock = asyncio.Lock()
        _auto_capture_user_locks[user_id] = lock
    try:
        async with lock:
            instance_id = uuid.uuid4().hex[:8]
            acquire_lock, release_lock = _get_auto_capture_lock_fns()
            lock_state = await acquire_lock(user_id, instance_id)
            if lock_state != "acquired":
                return
            try:
                from src.infra.memory.distributed import check_auto_retain_daily_limit

                daily_state = await check_auto_retain_daily_limit(user_id)
                if daily_state == "exceeded":
                    logger.debug(
                        "[Memory] Auto-retain daily limit reached for user %s, skipping",
                        user_id,
                    )
                    return
                backend = await _get_backend()
                if backend is None:
                    return
                if hasattr(backend, "auto_retain_from_text"):
                    if source_refs is None:
                        result = await backend.auto_retain_from_text(user_id, user_input)
                    else:
                        result = await backend.auto_retain_from_text(
                            user_id, user_input, source_refs
                        )
                    stored = 0
                    if isinstance(result, dict):
                        stored = int(result.get("stored") or 0)
                    logger.info(
                        "[Memory] Auto-retain completed for user %s: stored=%s candidates=%s",
                        user_id,
                        stored,
                        result.get("candidates") if isinstance(result, dict) else None,
                    )
                    if stored > 0:
                        try:
                            compaction_result = (
                                await get_memory_compaction_agent().maybe_compact_after_write(
                                    backend, user_id
                                )
                            )
                            logger.info(
                                "[Memory] Auto-compaction check for user %s: %s",
                                user_id,
                                compaction_result,
                            )
                        except Exception as e:
                            logger.warning(
                                "[Memory] Background memory compaction check failed: %s", e
                            )
            finally:
                await release_lock(user_id, instance_id)
    finally:
        _cleanup_local_auto_capture_lock(user_id, lock)


async def _auto_retain_user_memory_detached(
    user_id: str,
    user_input: str,
    source_refs: Optional[Sequence[ConversationSourceRef | dict[str, str]]] = None,
) -> None:
    """Run background memory capture without inheriting the chat trace parent."""
    with tracing_context(parent=False):
        if source_refs is None:
            await _auto_retain_user_memory(user_id, user_input)
        else:
            await _auto_retain_user_memory(user_id, user_input, source_refs)


def schedule_auto_memory_capture(
    user_id: str,
    user_input: str,
    source_refs: Optional[Sequence[ConversationSourceRef | dict[str, str]]] = None,
) -> None:
    """Best-effort background capture of durable user memories from latest input."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    existing = _auto_capture_tasks_by_user.get(user_id)
    if existing is not None and not existing.done():
        logger.debug("[Memory] Auto-retain already running for user %s, skipping", user_id)
        return
    active_auto_capture_tasks = sum(
        1 for task in _auto_capture_tasks_by_user.values() if not task.done()
    )
    if active_auto_capture_tasks >= _get_auto_capture_max_tasks():
        logger.warning(
            "[Memory] Auto-retain skipped for user %s: active task limit reached (%s)",
            user_id,
            active_auto_capture_tasks,
        )
        return

    clipped_input = _clip_auto_capture_input(user_input)
    logger.info("[Memory] Scheduling auto-retain for user %s", user_id)
    if source_refs is None:
        coro = _auto_retain_user_memory_detached(user_id, clipped_input)
    else:
        coro = _auto_retain_user_memory_detached(user_id, clipped_input, source_refs)
    task = loop.create_task(coro)
    _auto_capture_tasks_by_user[user_id] = task
    _background_tasks.add(task)
    task.add_done_callback(lambda done: _auto_capture_task_done(user_id, done))


async def run_scheduled_memory_compaction() -> dict:
    """Run the scheduled native memory compaction pass."""
    backend = await _get_backend()
    if backend is None:
        return {"checked": 0, "triggered": 0, "skipped": 1, "reason": "backend_unavailable"}
    return await get_memory_compaction_agent().run_periodic_once(backend)


def start_memory_compaction_agent() -> None:
    """Register periodic memory compaction checks with the unified scheduler."""
    if not settings.ENABLE_MEMORY:
        logger.info("[Memory] Auto-compaction scheduler not registered: ENABLE_MEMORY=false")
        return
    agent = get_memory_compaction_agent()
    get_runtime_scheduler().register_job(
        ScheduledJob.from_interval(
            id="memory.compaction",
            name="Memory compaction",
            interval_seconds=agent.get_periodic_interval_seconds,
            enabled=lambda: bool(settings.ENABLE_MEMORY) and agent.is_periodic_enabled(),
            handler=run_scheduled_memory_compaction,
        )
    )
    logger.info(
        "[Memory] Auto-compaction scheduler registered: enabled=%s threshold=%s interval=%ss",
        agent.is_periodic_enabled(),
        getattr(agent, "threshold", None),
        agent.get_periodic_interval_seconds(),
    )


# ============================================================================
# Backend Lifecycle (hot-swap support)
# ============================================================================


async def _close_and_reset_backend() -> None:
    """Close the current backend (if any) and reset the singleton."""
    global _backend
    lock = _get_backend_lock()
    async with lock:
        backend = _backend
        _backend = None
    if backend is not None:
        try:
            await backend.close()
        except Exception as e:
            logger.warning(f"[Memory] Error closing backend during reset: {e}")
    if settings.ENABLE_MEMORY:
        start_memory_compaction_agent()
        # 运行时开启记忆时补启动失效广播（boot 时才会随 runtime_services 启动）
        try:
            from src.infra.memory.distributed import get_memory_pubsub

            await get_memory_pubsub().start_listener()
        except Exception as e:
            logger.warning(f"[Memory] PubSub listener start after reset failed: {e}")
        # Qdrant 向量索引单例重建（URL/维度变更时旧实例已不可用）
        try:
            from src.infra.memory.client.native.vector_store import reset_vector_index

            await reset_vector_index()
        except Exception:
            pass
    logger.info("[Memory] Backend reset (will be recreated on next use)")


def _backend_reset_done(task: asyncio.Task) -> None:
    global _backend_reset_task
    if _backend_reset_task is task:
        _backend_reset_task = None
    _background_tasks.discard(task)
    _background_task_error(task)


def schedule_backend_reset() -> None:
    """Schedule a non-blocking backend reset (fire-and-forget).

    Call this when memory-related settings change so the next request
    picks up the new configuration without a server restart.
    """
    global _backend_reset_task

    existing = _backend_reset_task
    if existing is not None and not existing.done():
        logger.debug("[Memory] Backend reset already scheduled")
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop — reset synchronously (close may be incomplete but safe)
        global _backend
        _backend = None
        _backend_reset_task = None
        logger.info("[Memory] Backend reset (no event loop)")
        return

    task = loop.create_task(_close_and_reset_backend())
    _backend_reset_task = task
    _background_tasks.add(task)
    task.add_done_callback(_backend_reset_done)


async def shutdown() -> None:
    """Cancel all pending background tasks and close the backend.

    Call during application shutdown to prevent orphaned tasks.
    """
    global _backend, _backend_lock, _backend_lock_loop, _backend_reset_task

    # Cancel all background tasks
    for task in list(_background_tasks):
        task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()
    await stop_memory_compaction_agent()

    # Close backend
    backend = _backend
    _backend = None
    _backend_lock = None
    _backend_lock_loop = None
    _backend_reset_task = None
    _auto_capture_tasks_by_user.clear()
    _auto_capture_user_locks.clear()
    if backend is not None:
        try:
            await backend.close()
        except Exception as e:
            logger.warning(f"[Memory] Error closing backend during shutdown: {e}")
