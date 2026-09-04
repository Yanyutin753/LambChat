"""
Unified Memory Tools - LangChain Tool Integration

Provides a single set of memory tools that work with any MemoryBackend.
The underlying backend is transparent to the Agent — tool names and interfaces
are identical regardless of which memory provider is active.
"""

import asyncio
import json
from typing import Annotated, Any, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.memory.client.base import (
    MemoryBackend,
    create_memory_backend,
    get_session_id_from_runtime,
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
        "Short title (max 25 chars)",
    ] = None,
    summary: Annotated[
        Optional[str],
        "Brief summary (max 80 chars)",
    ] = None,
    context: Annotated[
        Optional[str],
        "Optional context label, e.g. 'user_identity' or 'feedback_rule'",
    ] = None,
    tags: Annotated[
        Optional[list[str]],
        "Optional keyword tags. Max 5.",
    ] = None,
    existing_memory_id: Annotated[
        Optional[str],
        "Optional existing memory ID to update instead of relying on fuzzy deduplication.",
    ] = None,
    scope: Annotated[
        Optional[str],
        "Ownership scope: 'user' (cross-project personal preference, default), "
        "'project' (bound to the current session's project), or 'reference' "
        "(external docs/links). Project ownership is inherited from the current "
        "session; when the session has no project, project-scoped content is "
        "automatically stored as 'user' scope (see result note).",
    ] = None,
    source_refs: Annotated[
        Optional[list[ConversationSourceRef]],
        "Conversation sources for this memory. Use only session_id/run_id pairs returned by conversation history tools or memory_recall; never invent IDs.",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Store a memory for cross-session persistence. STRICT: only genuinely useful,
    non-temporary information is accepted — follow the Cross-Session Memory
    guide's Remember/Skip policy. Content that is too short or resembles
    code/commands will be rejected. If a semantically similar memory already
    exists it is merged and updated automatically (result `updated_existing`
    is true), so write the FULL refreshed content including previously known
    details, not just the delta. Use explicit context labels such as
    `user_identity`, `project_constraint`, `project_status`, `feedback_rule`,
    or `reference_link`. For durable facts from conversation history, preserve
    their authorized `source_refs`; memory_recall returns them for the
    get_conversation_detail evidence SOP.
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
        from src.infra.memory.scope import resolve_session_project_id

        project_id = await resolve_session_project_id(get_session_id_from_runtime(runtime))
        # 无项目会话里 LLM 显式要 scope='project'：backend 会硬拒绝（生产上
        # 表现为前端红色报错 + agent 重试一轮）。工具层先降级为自动推导
        # （无归属 → user），不丢数据；结果里带 note 告知实际归属。
        scope_downgraded = scope == "project" and not project_id
        result = await backend.retain(
            user_id,
            content,
            context,
            title=title,
            summary=summary,
            tags=tags,
            existing_memory_id=existing_memory_id,
            source_refs=source_refs,
            scope=None if scope_downgraded else scope,
            project_id=project_id,
        )
        if scope_downgraded and isinstance(result, dict) and result.get("success"):
            result.setdefault("scope", "user")
            result["note"] = (
                "session has no project context; stored as 'user' scope "
                "(assign the session to a project to keep it project-scoped)"
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
        "Filter by memory types, or None for all",
    ] = None,
    context: Annotated[
        Optional[str],
        "Optional context family prefix filter ('project' also matches project_status/"
        "project_constraint), or None for all scopes",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Search and retrieve relevant memories from cross-session storage.

    Memories are not injected into user messages. When prior facts, preferences,
    project state, decisions, or corrections may matter, call this tool with a
    focused query instead of guessing from the compact index.
    Scope isolation is automatic: results include user/reference memories plus
    the current session's project memories; other projects' memories are
    never returned — do not generalize a project constraint to other contexts.
    Each result returns complete `text`: read it in full and do not omit
    fine-grained facts. If `text_complete` is false, `preview` is truncated —
    search the cited source instead of treating it as complete evidence.
    With `source_refs`, call `get_conversation_detail` (`session_id`, `run_id`)
    for the original final answer: the memory is a locator, the conversation
    detail is the source of truth.
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
        from src.infra.memory.scope import resolve_session_project_id

        project_id = await resolve_session_project_id(get_session_id_from_runtime(runtime))
        result = await backend.recall(
            user_id, query, max_results, memory_types, context, project_id=project_id
        )
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
    return [*get_inline_memory_tools(), *get_deferred_memory_tools()]


def get_inline_memory_tools() -> list[BaseTool]:
    """High-frequency, non-destructive tools mounted directly on the agent."""
    return [memory_retain, memory_recall]


def get_deferred_memory_tools() -> list[BaseTool]:
    """Destructive, low-frequency tools exposed through the `search_tools` channel."""
    return [memory_delete]


def _background_task_error(task: asyncio.Task) -> None:
    """Handle exceptions from background tasks."""
    try:
        exc = task.exception()
        if exc:
            logger.warning(f"[Memory] Background task failed: {exc}")
    except asyncio.CancelledError:
        pass


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
    from src.infra.memory.extraction import stop_memory_extraction_tasks

    await stop_memory_extraction_tasks()
    await stop_memory_compaction_agent()

    # Close backend
    backend = _backend
    _backend = None
    _backend_lock = None
    _backend_lock_loop = None
    _backend_reset_task = None
    if backend is not None:
        try:
            await backend.close()
        except Exception as e:
            logger.warning(f"[Memory] Error closing backend during shutdown: {e}")
