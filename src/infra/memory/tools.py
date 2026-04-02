"""
Unified Memory Tools - LangChain Tool Integration

Provides a single set of memory tools that work with any MemoryBackend.
The underlying backend is transparent to the Agent — tool names and interfaces
are identical regardless of which memory provider is active.
"""

import asyncio
import json
import uuid
from typing import Annotated, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.logging import get_logger
from src.infra.memory.client.base import MemoryBackend, create_memory_backend
from src.infra.memory.client.hindsight import get_user_id_from_runtime
from src.kernel.config import settings

logger = get_logger(__name__)

# Module-level cached backend (initialized lazily)
_backend: Optional[MemoryBackend] = None
_backend_lock: Optional[asyncio.Lock] = None
_backend_lock_loop: Optional[asyncio.AbstractEventLoop] = None
_background_tasks: set[asyncio.Task] = set()
_auto_capture_user_locks: dict[str, asyncio.Lock] = {}


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
                    "[Memory] No backend available (ENABLE_MEMORY=%s, MEMORY_PERFORM=%s)",
                    settings.ENABLE_MEMORY,
                    getattr(settings, "MEMORY_PERFORM", "N/A"),
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
    existing_memory_id: Annotated[
        Optional[str],
        "Optional existing memory ID to update instead of relying on fuzzy deduplication.",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Store a memory for cross-session persistence. STRICT: only genuinely useful,
    non-temporary information is accepted. Content that is too short, looks like a
    question, resembles code/commands, or duplicates an existing recent memory will
    be rejected. Prefer storing high-signal facts like user preferences, project
    context, feedback, or external references. Use explicit context labels such as
    `user_identity`, `project_constraint`, `project_status`, `feedback_rule`, or
    `reference_link` instead of vague buckets like `user_preferences`.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return json.dumps({"success": False, "error": "User not authenticated"}, ensure_ascii=False)

    backend = await _get_backend()
    if not backend:
        return json.dumps(
            {"success": False, "error": "Memory service not available"},
            ensure_ascii=False,
        )

    try:
        result = await backend.retain(
            user_id,
            content,
            context,
            title=title,
            summary=summary,
            existing_memory_id=existing_memory_id,
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[Memory] Failed to retain memory: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
async def memory_recall(
    query: Annotated[str, "The search query to find relevant memories"],
    max_results: Annotated[int, "Maximum number of memories to return (default: 5)"] = 5,
    memory_types: Annotated[
        Optional[list[str]],
        "Filter by memory types (backend-specific), or None for all types",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Search and retrieve relevant memories from cross-session storage.

    Use this tool to recall previously stored information. The search is
    semantic and will find memories that are conceptually related to the query.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return json.dumps({"success": False, "error": "User not authenticated"}, ensure_ascii=False)

    backend = await _get_backend()
    if not backend:
        return json.dumps(
            {"success": False, "error": "Memory service not available"},
            ensure_ascii=False,
        )

    try:
        result = await backend.recall(user_id, query, max_results, memory_types)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[Memory] Failed to recall memories: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


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
        return json.dumps({"success": False, "error": "User not authenticated"}, ensure_ascii=False)

    backend = await _get_backend()
    if not backend:
        return json.dumps(
            {"success": False, "error": "Memory service not available"},
            ensure_ascii=False,
        )

    try:
        result = await backend.delete(user_id, memory_id)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[Memory] Failed to delete memory: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


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
    return [memory_retain, memory_recall, memory_delete, memory_consolidate]


@tool
async def memory_consolidate(
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Consolidate memories: merge overlapping ones and prune stale entries.

    Use this when the user asks to clean up, organize, or consolidate their memories.
    This is a maintenance operation that should be run periodically.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return json.dumps({"success": False, "error": "User not authenticated"}, ensure_ascii=False)

    backend = await _get_backend()
    if not backend:
        return json.dumps(
            {"success": False, "error": "Memory service not available"},
            ensure_ascii=False,
        )

    try:
        # Only native backend supports consolidation
        if hasattr(backend, "consolidate_memories"):
            result = await backend.consolidate_memories(user_id)
            return json.dumps({"success": True, **result}, ensure_ascii=False)
        return json.dumps(
            {"success": False, "error": "Consolidation not supported for this backend"},
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"[Memory] Failed to consolidate memories: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _background_task_error(task: asyncio.Task) -> None:
    """Handle exceptions from background tasks."""
    try:
        exc = task.exception()
        if exc:
            logger.warning(f"[Memory] Background task failed: {exc}")
    except asyncio.CancelledError:
        pass


async def _auto_retain_user_memory(user_id: str, user_input: str) -> None:
    if not user_id or not user_input.strip():
        return
    lock = _auto_capture_user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _auto_capture_user_locks[user_id] = lock
    async with lock:
        instance_id = uuid.uuid4().hex[:8]
        acquire_lock, release_lock = _get_auto_capture_lock_fns()
        lock_state = await acquire_lock(user_id, instance_id)
        if lock_state != "acquired":
            _cleanup_local_auto_capture_lock(user_id, lock)
            return
        try:
            backend = await _get_backend()
            if backend is None or backend.name != "native":
                return
            if hasattr(backend, "auto_retain_from_text"):
                await backend.auto_retain_from_text(user_id, user_input)
        finally:
            await release_lock(user_id, instance_id)
    _cleanup_local_auto_capture_lock(user_id, lock)


def schedule_auto_memory_capture(user_id: str, user_input: str) -> None:
    """Best-effort background capture of durable user memories from latest input."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    task = loop.create_task(_auto_retain_user_memory(user_id, user_input))
    _background_tasks.add(task)
    task.add_done_callback(_background_task_error)
    task.add_done_callback(_background_tasks.discard)


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
    logger.info("[Memory] Backend reset (will be recreated on next use)")


def schedule_backend_reset() -> None:
    """Schedule a non-blocking backend reset (fire-and-forget).

    Call this when memory-related settings change so the next request
    picks up the new configuration without a server restart.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop — reset synchronously (close may be incomplete but safe)
        global _backend
        _backend = None
        logger.info("[Memory] Backend reset (no event loop)")
        return

    task = loop.create_task(_close_and_reset_backend())
    _background_tasks.add(task)
    task.add_done_callback(_background_task_error)
    task.add_done_callback(_background_tasks.discard)


async def shutdown() -> None:
    """Cancel all pending background tasks and close the backend.

    Call during application shutdown to prevent orphaned tasks.
    """
    global _backend, _backend_lock, _backend_lock_loop

    # Cancel all background tasks
    for task in list(_background_tasks):
        task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()

    # Close backend
    backend = _backend
    _backend = None
    _backend_lock = None
    _backend_lock_loop = None
    _auto_capture_user_locks.clear()
    if backend is not None:
        try:
            await backend.close()
        except Exception as e:
            logger.warning(f"[Memory] Error closing backend during shutdown: {e}")
