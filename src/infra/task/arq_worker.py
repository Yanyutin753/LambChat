from __future__ import annotations

import asyncio
import inspect
import uuid
from importlib import import_module
from typing import Any

from arq import Retry

from src.infra.distributed_validation import validate_distributed_runtime_settings
from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings

from .arq_payloads import TaskArqPayloadStore, UserMessageSearchIndexPayloadStore
from .concurrency import get_concurrency_limiter, get_registered_executor
from .exceptions import TaskInterruptedError
from .hitl import (
    mark_hitl_source_released,
    wait_for_hitl_resume_activation,
    wait_for_hitl_source_release,
)
from .manager import get_task_manager
from .status import TaskStatus

logger = get_logger(__name__)

HITL_RESUME_STARTUP_LOCK_PREFIX = "hitl:resume-starting:"
HITL_RESUME_STARTUP_LOCK_TTL_SECONDS = 30


async def _acquire_hitl_resume_startup_lock(run_id: str) -> str | None:
    token = uuid.uuid4().hex
    acquired = await get_redis_client().set(
        f"{HITL_RESUME_STARTUP_LOCK_PREFIX}{run_id}",
        token,
        ex=HITL_RESUME_STARTUP_LOCK_TTL_SECONDS,
        nx=True,
    )
    return token if acquired else None


async def _release_hitl_resume_startup_lock(run_id: str, token: str) -> None:
    lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    try:
        result = get_redis_client().eval(
            lua,
            1,
            f"{HITL_RESUME_STARTUP_LOCK_PREFIX}{run_id}",
            token,
        )
        if inspect.isawaitable(result):
            await result
    except Exception as e:
        logger.warning("Failed to release HITL resume startup lock for %s: %s", run_id, e)


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


async def run_agent_task(ctx: dict[str, Any], dispatch_id: str) -> None:
    """Run a previously persisted LambChat task from an arq worker."""
    payload_store: TaskArqPayloadStore = ctx.get("payload_store") or TaskArqPayloadStore()
    payload = await payload_store.load(dispatch_id)
    if payload is None:
        logger.warning("Missing arq task payload for dispatch_id=%s", dispatch_id)
        return
    run_id = str(payload.get("run_id") or dispatch_id)

    hitl_resume = payload.get("hitl_resume") or {}
    resume_attempt_id = hitl_resume.get("resume_attempt_id")
    if resume_attempt_id and not await wait_for_hitl_resume_activation(
        str(hitl_resume.get("approval_id") or ""), str(resume_attempt_id)
    ):
        await payload_store.delete(dispatch_id)
        return

    task_manager = get_task_manager()
    task_executor = task_manager._ensure_executor()

    interrupted_resume = bool(payload.get("interrupted_resume"))
    hitl_slot_acquired = False
    resume_slot_acquired = False
    if payload.get("hitl_resume"):
        startup_token = await _acquire_hitl_resume_startup_lock(run_id)
        if startup_token is None:
            raise Retry(defer=1)
        try:
            if not await wait_for_hitl_source_release(run_id, payload.get("user_id")):
                raise Retry(defer=1)
            limiter = get_concurrency_limiter()
            if not await limiter.try_acquire_run_slot(payload["user_id"], run_id):
                raise Retry(defer=1)
            hitl_slot_acquired = True
            try:
                await task_executor._update_session_status(
                    payload["session_id"], TaskStatus.PENDING, run_id=run_id
                )
            except BaseException:
                await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=False)
                raise
        finally:
            await _release_hitl_resume_startup_lock(run_id, startup_token)
    elif interrupted_resume:
        # 系统中断后的同 run 无缝续跑：源执行者已死（恢复入口校验过心跳），
        # 只需原子重占并发槽；占不到就 defer 重试，避免排队复制语义。
        # 提交到 worker 拾取之间若心跳又变新鲜（误判死活），defer 等真死，
        # 防止与原执行者并发写同一条流。
        from .heartbeat import TaskHeartbeat

        if not await TaskHeartbeat().is_stale(run_id):
            logger.info(
                "Interrupted resume deferred, heartbeat fresh again: run_id=%s", run_id
            )
            raise Retry(defer=5)
        limiter = get_concurrency_limiter()
        if not await limiter.try_acquire_run_slot(payload["user_id"], run_id):
            raise Retry(defer=1)
        resume_slot_acquired = True
        try:
            await task_executor._update_session_status(
                payload["session_id"], TaskStatus.PENDING, run_id=run_id
            )
        except BaseException:
            await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=False)
            raise

    executor_key = str(payload["executor_key"])
    try:
        executor_fn = _resolve_executor(executor_key)
    except BaseException:
        if hitl_slot_acquired or resume_slot_acquired:
            await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=False)
        raise
    if executor_fn is None:
        error_message = f"No executor registered for key '{executor_key}'"
        logger.error("%s: run_id=%s", error_message, run_id)
        await task_executor._update_session_status(
            payload["session_id"],
            TaskStatus.FAILED,
            error_message,
            run_id=run_id,
        )
        await payload_store.delete(dispatch_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
        return

    task_manager._run_info[run_id] = {
        "session_id": payload["session_id"],
        "trace_id": payload.get("trace_id"),
        "agent_id": payload["agent_id"],
        "user_id": payload["user_id"],
        "user_message_written": payload.get("user_message_written", False),
        "attachment_references_claimed": payload.get("attachment_references_claimed", False),
    }

    try:
        suspended = await task_executor.run_task(
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
            auto_mode=bool(payload.get("auto_mode", False)),
            attachment_references_claimed=bool(payload.get("attachment_references_claimed", False)),
            hitl_resume=payload.get("hitl_resume"),
            interrupted_resume=interrupted_resume,
        )
    except TaskInterruptedError:
        await payload_store.delete(dispatch_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
        logger.info("Deleted arq payload after user interruption: run_id=%s", run_id)
    except asyncio.CancelledError:
        if await _is_user_cancelled_run(task_manager, payload["session_id"], run_id):
            await payload_store.delete(dispatch_id)
            await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
            logger.info("Deleted arq payload after user cancellation: run_id=%s", run_id)
            return
        await task_manager._mark_run_recoverable_failure(
            payload["session_id"],
            run_id,
            "Server shutdown",
        )
        await payload_store.delete(dispatch_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=False)
        raise
    except Exception:
        logger.warning("Keeping arq task payload for retry: run_id=%s", run_id)
        raise
    else:
        await payload_store.delete(dispatch_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
        if suspended:
            await mark_hitl_source_released(run_id)
    finally:
        task_manager._run_info.pop(run_id, None)


async def update_user_message_search_index(ctx: dict[str, Any], run_id: str) -> None:
    """Apply a durable user-message search-index update on any ARQ worker."""
    payload_store: UserMessageSearchIndexPayloadStore = (
        ctx.get("search_index_payload_store") or UserMessageSearchIndexPayloadStore()
    )
    payload = await payload_store.load(run_id)
    if payload is None:
        logger.warning("Missing user-message search-index payload for run_id=%s", run_id)
        return

    try:
        from src.infra.session.storage import SessionStorage

        await SessionStorage().append_user_message_search_content(
            str(payload["session_id"]),
            str(payload["content"]),
        )
    except Exception as exc:
        logger.warning(
            "Distributed user-message search-index update failed; retrying: run_id=%s",
            run_id,
        )
        raise Retry(defer=5) from exc

    await payload_store.delete(run_id)


class WorkerSettings:
    functions = [run_agent_task, update_user_message_search_index]
    on_startup = worker_startup
