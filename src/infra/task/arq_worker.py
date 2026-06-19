from __future__ import annotations

import asyncio
from importlib import import_module
from typing import Any

from src.agents import ensure_agent_executable
from src.infra.distributed_validation import validate_distributed_runtime_settings
from src.infra.logging import get_logger
from src.kernel.extensions import PluginUnavailableError
from src.kernel.config import settings

from .arq_payloads import TaskArqPayloadStore
from .concurrency import get_concurrency_limiter, get_registered_executor
from .exceptions import TaskInterruptedError
from .manager import get_task_manager
from .status import TaskStatus

logger = get_logger(__name__)


async def worker_startup(ctx: dict[str, Any]) -> None:
    """Validate worker runtime configuration before accepting jobs."""
    del ctx
    validate_distributed_runtime_settings(settings)


def _resolve_executor(executor_key: str) -> Any:
    executor_fn = get_registered_executor(executor_key)
    if executor_fn is not None:
        return executor_fn

    if executor_key == "agent_stream":
        import_module("src.api.routes.chat")
        return get_registered_executor(executor_key)

    return None


async def _is_user_cancelled_run(task_manager: Any, session_id: str, run_id: str) -> bool:
    storage = getattr(task_manager, "storage", None)
    if storage is None:
        return False

    try:
        session = await storage.get_by_session_id(session_id)
    except Exception as e:
        logger.warning("Failed to inspect cancelled run state: %s", e)
        return False

    metadata = getattr(session, "metadata", None) or {}
    current_run_id = metadata.get("current_run_id")
    if current_run_id and str(current_run_id) != str(run_id):
        return False

    return (
        metadata.get("task_error_code") == "cancelled"
        or metadata.get("task_status") == TaskStatus.CANCELLED.value
    )


async def _release_concurrency_slot(user_id: str | None, run_id: str, *, dequeue: bool) -> None:
    if not user_id:
        return

    try:
        limiter = get_concurrency_limiter()
        await limiter.release(user_id, run_id, dequeue=dequeue)
    except Exception as e:
        logger.warning("Failed to release arq concurrency slot: %s", e)


async def run_agent_task(ctx: dict[str, Any], run_id: str) -> None:
    """Run a previously persisted LambChat task from an arq worker."""
    payload_store: TaskArqPayloadStore = ctx.get("payload_store") or TaskArqPayloadStore()
    payload = await payload_store.load(run_id)
    if payload is None:
        logger.warning("Missing arq task payload for run_id=%s", run_id)
        return

    task_manager = get_task_manager()
    task_executor = task_manager._ensure_executor()

    executor_key = str(payload["executor_key"])
    executor_fn = _resolve_executor(executor_key)
    if executor_fn is None:
        error_message = f"No executor registered for key '{executor_key}'"
        logger.error("%s: run_id=%s", error_message, run_id)
        await task_executor._update_session_status(
            payload["session_id"],
            TaskStatus.FAILED,
            error_message,
            run_id=run_id,
        )
        await payload_store.delete(run_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
        return

    try:
        ensure_agent_executable(str(payload["agent_id"]))
    except PluginUnavailableError as exc:
        error_message = str(exc) or "Plugin-owned agent is unavailable"
        logger.warning(
            "Rejecting arq task for unavailable plugin-owned agent: run_id=%s, agent_id=%s, plugin_id=%s",
            run_id,
            payload.get("agent_id"),
            exc.plugin_id,
        )
        await task_executor._update_session_status(
            payload["session_id"],
            TaskStatus.FAILED,
            error_message,
            run_id=run_id,
        )
        await payload_store.delete(run_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
        return

    task_manager._run_info[run_id] = {
        "session_id": payload["session_id"],
        "trace_id": payload.get("trace_id"),
        "agent_id": payload["agent_id"],
        "user_id": payload["user_id"],
        "user_message_written": payload.get("user_message_written", False),
    }

    try:
        await task_executor.run_task(
            session_id=payload["session_id"],
            run_id=run_id,
            agent_id=payload["agent_id"],
            message=payload["message"],
            user_id=payload["user_id"],
            executor=executor_fn,
            disabled_tools=payload.get("disabled_tools"),
            agent_options=payload.get("agent_options"),
            attachments=payload.get("attachments"),
            existing_trace_id=payload.get("trace_id"),
            user_message_written=payload.get("user_message_written", False),
            disabled_skills=payload.get("disabled_skills"),
            enabled_skills=payload.get("enabled_skills"),
            persona_system_prompt=payload.get("persona_system_prompt"),
            disabled_mcp_tools=payload.get("disabled_mcp_tools"),
            display_message=payload.get("display_message"),
            recommendation_input=payload.get("recommendation_input"),
            team_id=payload.get("team_id"),
            active_goal=payload.get("active_goal"),
        )
    except TaskInterruptedError:
        await payload_store.delete(run_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
        logger.info("Deleted arq payload after user interruption: run_id=%s", run_id)
    except asyncio.CancelledError:
        if await _is_user_cancelled_run(task_manager, payload["session_id"], run_id):
            await payload_store.delete(run_id)
            await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
            logger.info("Deleted arq payload after user cancellation: run_id=%s", run_id)
            return
        await task_manager._mark_run_recoverable_failure(
            payload["session_id"],
            run_id,
            "Server shutdown",
        )
        await payload_store.delete(run_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=False)
        raise
    except Exception:
        logger.warning("Keeping arq task payload for retry: run_id=%s", run_id)
        raise
    else:
        await payload_store.delete(run_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
    finally:
        task_manager._run_info.pop(run_id, None)


class WorkerSettings:
    functions = [run_agent_task]
    on_startup = worker_startup
