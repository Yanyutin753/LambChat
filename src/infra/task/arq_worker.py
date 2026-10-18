from __future__ import annotations

import asyncio
import inspect
import uuid
from importlib import import_module
from typing import Any

from arq import Retry, cron
from arq.typing import WorkerCoroutine

from src.infra.distributed_validation import validate_distributed_runtime_settings
from src.infra.goal_continuation import continue_persistent_goal, scan_persistent_goals
from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings

from .arq_payloads import TaskArqPayloadStore, UserMessageSearchIndexPayloadStore
from .background_tasks import scan_background_tasks
from .concurrency import get_concurrency_limiter, get_registered_executor
from .exceptions import TaskInterruptedError
from .hitl import (
    mark_hitl_source_released,
    wait_for_hitl_resume_activation,
    wait_for_hitl_source_release,
)
from .manager import get_task_manager
from .state_machine import TaskStateMachine
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

    # 登记本进程事件循环：本地沙箱同步文件操作的协程桥接统一投递到该循环，
    # 共享 redis.asyncio 连接池不再跨循环复用（对齐 API 进程 lifespan 的登记）
    from src.infra.async_utils import loop_bridge

    loop_bridge.set_main_loop(asyncio.get_running_loop())

    _schedule_model_warmup()


async def _warmup_model_clients() -> None:
    """预创建所有已启用模型的 LLM 客户端（尽力而为，不阻塞不致命）。

    生产测量（2026-09-17 yang）：worker 冷启动后每个模型的第一个请求要现场
    建实例（含 api_key 查库/Fernet 解密），TaskGroup 段 ~0.8s。预热结果进
    LLMClient 进程级 LRU，重复创建无副作用。
    """
    from src.infra.agent.model_storage import get_model_storage
    from src.infra.llm.client import LLMClient

    try:
        models = await get_model_storage().list_models(include_disabled=False)
    except Exception:
        logger.warning("[ModelWarmup] Skipping warmup: model listing failed", exc_info=True)
        return

    warmed = 0
    for model_cfg in models:
        try:
            await LLMClient.get_model(model=model_cfg.value, model_config=model_cfg)
            warmed += 1
        except Exception:
            logger.debug("[ModelWarmup] Warmup failed for %s", model_cfg.value, exc_info=True)
    logger.info("[ModelWarmup] Pre-created %d/%d enabled model clients", warmed, len(models))


def _schedule_model_warmup() -> asyncio.Task[None] | None:
    """在 worker 启动时后台调度模型客户端预热；配置关闭时返回 None。"""
    if not getattr(settings, "LLM_MODEL_WARMUP_ON_STARTUP", True):
        return None
    return asyncio.create_task(_warmup_model_clients())


async def worker_shutdown(ctx: dict[str, Any]) -> None:
    """Mark the worker process as shutting down so recovery entrypoints go quiet."""
    del ctx
    from src.infra.async_utils import loop_bridge

    from .lifecycle import mark_shutting_down

    loop_bridge.clear_main_loop()
    mark_shutting_down()


def _resolve_executor(executor_key: str) -> Any:
    if executor_key == "scheduled_agent_stream":
        from src.infra.scheduler.runner import execute_standalone_schedule

        return execute_standalone_schedule
    executor_fn = get_registered_executor(executor_key)
    if executor_fn is not None:
        return executor_fn

    if executor_key == "conversation_schedule":
        from src.infra.scheduler.conversation import execute_conversation_schedule

        return execute_conversation_schedule
    if executor_key == "background_agent_stream":
        from .background_tasks import execute_background_stream

        return execute_background_stream
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


def _run_watchdog_timeout() -> float | None:
    """Run-level watchdog deadline; None disables the watchdog."""
    timeout = getattr(settings, "TASK_RUN_WATCHDOG_TIMEOUT", 0.0)
    return timeout if timeout and timeout > 0 else None


async def _validate_standalone_scheduled_admission(payload: dict, run_id: str) -> None:
    from src.infra.goal_runtime import GoalRunAdmissionError
    from src.kernel.errors import AppError

    from .background_tasks import apply_background_restrictions, validate_background_execution

    session = await get_task_manager().storage.get_by_session_id(payload["session_id"])
    metadata = (session.metadata or {}) if session else {}
    status = metadata.get("task_status")
    if (
        not session
        or session.user_id != payload["user_id"]
        or metadata.get("current_run_id") != run_id
        or metadata.get("task_error_code") == "cancelled"
        or status in {"completed", "cancelled", "cancelling", "expired"}
        or (
            status == "failed"
            and not (payload.get("interrupted_resume") and metadata.get("task_recoverable") is True)
        )
        or (status == "waiting_human" and not payload.get("hitl_resume"))
    ):
        raise GoalRunAdmissionError("Scheduled task no longer owns a runnable conversation")
    try:
        request = await validate_background_execution(
            payload["session_id"],
            payload["agent_id"],
            payload["user_id"],
            payload.get("agent_options") or {},
        )
        apply_background_restrictions(request, payload)
    except AppError as error:
        if error.http_status >= 500:
            raise
        executor = get_task_manager()._ensure_executor()
        await executor._update_session_status(
            payload["session_id"],
            TaskStatus.FAILED,
            "Scheduled task authorization is no longer valid",
            run_id=run_id,
            expected_run_id=run_id,
        )
        try:
            if payload.get("trace_id"):
                from src.infra.writer.present import Presenter, PresenterConfig

                presenter = Presenter(
                    PresenterConfig(
                        session_id=payload["session_id"],
                        agent_id=payload["agent_id"],
                        user_id=payload["user_id"],
                        run_id=run_id,
                        trace_id=payload["trace_id"],
                    )
                )
                presenter._trace_created = True
                await executor._handle_generic_error(
                    payload["session_id"], run_id, payload["user_id"], error, None, presenter
                )
                done = presenter.done()
                done["data"]["status"] = "error"
                await presenter.emit(done)
                writer = await presenter._get_dual_writer()
                await writer.flush_mongo_buffer(require_empty=True)
        finally:
            await _release_concurrency_slot(payload["user_id"], run_id, dequeue=True)
        raise GoalRunAdmissionError("Scheduled task authorization is no longer valid") from error
    payload["agent_options"] = request.agent_options
    for field in (
        "persona_system_prompt",
        "disabled_tools",
        "disabled_skills",
        "enabled_skills",
        "disabled_mcp_tools",
        "enabled_mcp_servers",
        "team_id",
    ):
        payload[field] = getattr(request, field)


async def run_agent_task(ctx: dict[str, Any], dispatch_id: str) -> None:
    """Run a previously persisted LambChat task from an arq worker."""
    payload_store: TaskArqPayloadStore = ctx.get("payload_store") or TaskArqPayloadStore()
    payload = await payload_store.load(dispatch_id)
    if payload is None:
        logger.warning("Missing arq task payload for dispatch_id=%s", dispatch_id)
        return
    run_id = str(payload.get("run_id") or dispatch_id)

    from src.infra.goal_runtime import (
        GOAL_LEASE_TTL_SECONDS,
        GoalRunAdmissionError,
        GoalRunAlreadyOwnedError,
        goal_run_lease,
        validate_goal_admission,
    )

    try:
        background = (
            (payload["user_id"], payload["session_id"])
            if payload.get("executor_key")
            in {"background_agent_stream", "conversation_schedule", "scheduled_agent_stream"}
            else None
        )
        async with goal_run_lease(
            payload.get("active_goal"), run_id, background_identity=background
        ):
            if payload.get("executor_key") == "scheduled_agent_stream":
                await _validate_standalone_scheduled_admission(payload, run_id)
            await validate_goal_admission({**payload, "run_id": run_id})
            if payload.get("executor_key") == "background_agent_stream":
                from .background_admission import validate_background_run_admission

                await validate_background_run_admission(
                    payload["session_id"], payload["user_id"], run_id
                )
            if payload.get("executor_key") == "conversation_schedule":
                from src.infra.scheduler.conversation import validate_scheduled_run_admission

                await validate_scheduled_run_admission(
                    payload["session_id"], payload["user_id"], run_id
                )
            await _run_agent_payload(payload_store, payload, dispatch_id, run_id)
    except GoalRunAdmissionError:
        if payload.get("recovery_claim"):
            from .recovery import restore_recovery_claim

            await restore_recovery_claim(
                get_task_manager().storage,
                payload["session_id"],
                run_id,
                payload["recovery_claim"],
                recoverable=False,
            )
        await payload_store.delete(dispatch_id)
        logger.info("Discarded stale Goal admission: run_id=%s", run_id)
    except GoalRunAlreadyOwnedError:
        # The current owner still needs the payload, concurrency slot and run info.
        if payload.get("interrupted_resume") or payload.get("hitl_resume"):
            logger.info("Deferred task resume while execution lease is owned: run_id=%s", run_id)
            raise Retry(defer=GOAL_LEASE_TTL_SECONDS)
        logger.info("Ignored duplicate Goal runner: run_id=%s", run_id)
    except Retry:
        raise
    except Exception:
        if payload.get("recovery_claim"):
            from .recovery import restore_recovery_claim

            await restore_recovery_claim(
                get_task_manager().storage,
                payload["session_id"],
                run_id,
                payload["recovery_claim"],
                recoverable=True,
            )
        raise


async def _run_agent_payload(payload_store, payload, dispatch_id: str, run_id: str) -> None:

    hitl_resume = payload.get("hitl_resume") or {}
    resume_attempt_id = hitl_resume.get("resume_attempt_id")
    if resume_attempt_id and not await wait_for_hitl_resume_activation(
        str(hitl_resume.get("approval_id") or ""), str(resume_attempt_id)
    ):
        await payload_store.delete(dispatch_id)
        return

    if payload.get("executor_key") == "scheduled_agent_stream":
        await _validate_standalone_scheduled_admission(payload, run_id)

    task_manager = get_task_manager()
    task_executor = task_manager._ensure_executor()

    interrupted_resume = bool(payload.get("interrupted_resume"))
    persistent_goal = bool((payload.get("active_goal") or {}).get("_persistent_id"))
    background_run = payload.get("executor_key") == "background_agent_stream"
    scheduled_run = payload.get("executor_key") == "conversation_schedule"
    fenced_resume = persistent_goal or background_run or scheduled_run

    async def admit_goal_resume():
        if fenced_resume:
            from src.infra.goal_runtime import validate_goal_admission

            await validate_goal_admission({**payload, "run_id": run_id})
            if background_run:
                from .background_admission import validate_background_run_admission

                await validate_background_run_admission(
                    payload["session_id"], payload["user_id"], run_id
                )
            if scheduled_run:
                from src.infra.scheduler.conversation import validate_scheduled_run_admission

                await validate_scheduled_run_admission(
                    payload["session_id"], payload["user_id"], run_id
                )
            if not interrupted_resume:
                await task_executor._update_session_status(
                    payload["session_id"], TaskStatus.PENDING, run_id=run_id, expected_run_id=run_id
                )

    hitl_slot_acquired = False
    resume_slot_acquired = False
    if payload.get("hitl_resume"):
        startup_token = await _acquire_hitl_resume_startup_lock(run_id)
        if startup_token is None:
            raise Retry(defer=1)
        try:
            if not await wait_for_hitl_source_release(run_id, payload.get("user_id")):
                raise Retry(defer=1)
            await admit_goal_resume()
            limiter = get_concurrency_limiter()
            if not await limiter.try_acquire_run_slot(payload["user_id"], run_id):
                raise Retry(defer=1)
            hitl_slot_acquired = True
            try:
                if not fenced_resume:
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
            logger.info("Interrupted resume deferred, heartbeat fresh again: run_id=%s", run_id)
            raise Retry(defer=5)
        admitted = await task_manager.storage.claim_run_recovery(
            payload["session_id"],
            run_id,
            {
                **TaskStateMachine().build_metadata(TaskStatus.PENDING, run_id=run_id),
                **(
                    {
                        key: payload["recovery_claim"]["metadata"].get(key)
                        for key in ("task_error", "task_error_code")
                    }
                    if payload.get("recovery_claim")
                    else {}
                ),
            },
            **(
                {"expected_recovery_token": payload["recovery_claim"]["token"]}
                if payload.get("recovery_claim")
                else {}
            ),
        )
        if not admitted:
            # Heartbeat I/O and queue delivery can outlive this run. Discard
            # only this dispatch without disturbing its completed/new owner.
            await payload_store.delete(dispatch_id)
            logger.info("Discarded stale interrupted resume: run_id=%s", run_id)
            return
        await admit_goal_resume()
        limiter = get_concurrency_limiter()
        if not await limiter.try_acquire_run_slot(payload["user_id"], run_id):
            raise Retry(defer=1)
        resume_slot_acquired = True

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

    # Cancel must reach ARQ execution even before the agent registers its graph task.
    owner = asyncio.current_task()
    assert owner is not None
    task_manager._tasks[run_id] = owner
    try:
        run_kwargs = dict(
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
            enabled_mcp_servers=payload.get("enabled_mcp_servers"),
            display_message=payload.get("display_message"),
            recommendation_input=payload.get("recommendation_input"),
            team_id=payload.get("team_id"),
            active_goal=payload.get("active_goal"),
            auto_mode=bool(payload.get("auto_mode", False)),
            attachment_references_claimed=bool(payload.get("attachment_references_claimed", False)),
            hitl_resume=payload.get("hitl_resume"),
            interrupted_resume=interrupted_resume,
            recovery_claim=payload.get("recovery_claim"),
            base_url=str(payload.get("base_url") or ""),
        )
        watchdog_timeout = (
            None
            if executor_key in {"conversation_schedule", "scheduled_agent_stream"}
            else _run_watchdog_timeout()
        )
        if watchdog_timeout is None:
            suspended = await task_executor.run_task(**run_kwargs)
        else:
            async with asyncio.timeout(watchdog_timeout):
                suspended = await task_executor.run_task(**run_kwargs)
    except TaskInterruptedError:
        await payload_store.delete(dispatch_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
        logger.info("Deleted arq payload after interruption or stale admission: run_id=%s", run_id)
    except asyncio.CancelledError:
        if await _is_user_cancelled_run(task_manager, payload["session_id"], run_id):
            await payload_store.delete(dispatch_id)
            await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
            logger.info("Deleted arq payload after user cancellation: run_id=%s", run_id)
            return
        from .lifecycle import is_shutting_down

        await task_manager._mark_run_recoverable_failure(
            payload["session_id"],
            run_id,
            "Server shutdown" if is_shutting_down() else "Worker task interrupted",
        )
        await payload_store.delete(dispatch_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=False)
        raise
    except TimeoutError:
        # Watchdog 触发：run_task 内部的取消处理已终结 trace，这里确保
        # session 终态是 FAILED（而非 CANCELLED），并清理 payload 不重试。
        error_message = f"Task run exceeded watchdog timeout ({watchdog_timeout}s)"
        logger.error("arq run watchdog timeout: run_id=%s", run_id)
        try:
            await task_executor._update_session_status(
                payload["session_id"],
                TaskStatus.FAILED,
                error_message,
                run_id=run_id,
            )
        except Exception as e:
            logger.warning("Failed to mark watchdog timeout status: run_id=%s: %s", run_id, e)
        await payload_store.delete(dispatch_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
    except Exception:
        logger.warning("Keeping arq task payload for retry: run_id=%s", run_id)
        raise
    else:
        await payload_store.delete(dispatch_id)
        await _release_concurrency_slot(payload.get("user_id"), run_id, dequeue=True)
        if suspended:
            await mark_hitl_source_released(run_id)
    finally:
        if task_manager._tasks.get(run_id) is owner:
            task_manager._tasks.pop(run_id)
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


_SCHEDULED_RENEW_INTERVAL = 30


async def run_scheduled_agent_task(ctx: dict[str, Any], dispatch_id: str) -> None:
    """Keep ARQ ownership and recovery data alive without a total execution deadline."""
    from arq.constants import in_progress_key_prefix

    owner = asyncio.current_task()

    async def renew():
        try:
            while True:
                if not await ctx["redis"].expire(in_progress_key_prefix + ctx["job_id"], 90):
                    raise RuntimeError("Scheduled ARQ execution ownership was lost")
                await asyncio.sleep(_SCHEDULED_RENEW_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled ARQ ownership renewal failed: dispatch=%s", dispatch_id)
            if owner:
                owner.cancel()

    renewal = asyncio.create_task(renew())
    try:
        await run_agent_task(ctx, dispatch_id)
    finally:
        renewal.cancel()
        await asyncio.gather(renewal, return_exceptions=True)


class WorkerSettings:
    functions: list[WorkerCoroutine] = [
        run_scheduled_agent_task,
        run_agent_task,
        update_user_message_search_index,
        continue_persistent_goal,
    ]
    cron_jobs = [
        cron(scan_persistent_goals, second={0, 10, 20, 30, 40, 50}, run_at_startup=True),
        cron(scan_background_tasks, second={5, 15, 25, 35, 45, 55}, run_at_startup=True),
    ]
    on_startup = worker_startup
    on_shutdown = worker_shutdown
