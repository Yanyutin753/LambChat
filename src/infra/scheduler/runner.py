"""Scheduled task execution engine.

Connects APScheduler triggers with the existing BackgroundTaskManager
so that dynamically-created tasks run through the normal agent pipeline.
"""

from __future__ import annotations

import asyncio
import collections.abc
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from src.infra.channel.manager import get_channel_coordinator
from src.infra.chat.user_message_timestamp import format_scheduled_message_with_timestamp
from src.infra.logging import get_logger
from src.infra.scheduler.locks import (
    acquire_task_lock,
    acquire_task_slot_lock,
    extend_task_lock,
    release_task_lock,
)
from src.infra.scheduler.runtime import SCHEDULED_FIRE_TIME, get_runtime_scheduler
from src.infra.scheduler.storage import get_scheduled_task_storage
from src.infra.session.trace_storage import get_trace_storage
from src.infra.utils.datetime import ensure_utc, utc_now
from src.kernel.config import settings
from src.kernel.schemas.scheduled_task import (
    RunStatus,
    ScheduledTask,
    TaskRunRecord,
    TriggerType,
)
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

_POLL_INTERVAL = 2  # seconds between status checks when waiting for completion
_EXECUTION_LOCK_TTL = 600  # Renewed while running; not an execution deadline.


class _ExecutionLeaseLostError(RuntimeError):
    pass


# Track detached monitor tasks so they can be drained on shutdown.
_detached_monitor_tasks: set[asyncio.Task[None]] = set()


def _spawn_monitor(coro: collections.abc.Coroutine[None, None, None]) -> asyncio.Task[None]:
    """Spawn a detached fire-and-forget task with crash-safe error handling."""

    async def _safe_run() -> None:
        try:
            await coro
        except Exception:
            logger.exception("[Runner] detached monitor task failed (lock will expire via TTL)")

    t = asyncio.create_task(_safe_run())
    _detached_monitor_tasks.add(t)
    t.add_done_callback(_detached_monitor_tasks.discard)
    return t


async def drain_detached_monitors(timeout: float = 10.0) -> None:
    """Wait for in-flight monitor tasks to finish during shutdown."""
    tasks = list(_detached_monitor_tasks)
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=max(0.0, float(timeout)))
    for t in pending:
        t.cancel()
    if pending:
        logger.warning(
            "[Runner] cancelled %d detached monitor task(s) on shutdown",
            len(pending),
        )
        await asyncio.gather(*pending, return_exceptions=True)


@dataclass(frozen=True)
class _AttemptResult:
    status: RunStatus
    result: dict[str, Any]
    error_message: str | None = None


async def _resolve_task_owner(user_id: str) -> TokenPayload | None:
    from src.api.deps import _load_user_payload

    return await _load_user_payload(user_id)


async def _agent_options_with_default_model(
    agent_options: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """未显式选模的定时任务注入全局默认模型。

    不注入时节点运行期照样静默走默认模型，但 presenter 配置与
    token:usage 事件都拿不到模型名——用量面板的模型列与费用全部缺失。
    已带 model/model_id 的选项原样返回，不覆盖创建时的显式选择。
    """
    options = dict(agent_options) if isinstance(agent_options, dict) else {}
    if options.get("model") or options.get("model_id"):
        return agent_options
    from src.infra.llm.models_service import get_default_model, get_default_model_id

    try:
        model = await get_default_model()
    except Exception as e:  # noqa: BLE001 - 模型归属尽力而为，不得阻塞任务执行
        logger.warning("[ScheduledTask] Failed to resolve default model for attribution: %s", e)
        return agent_options
    if not model:
        return agent_options
    options["model"] = model
    try:
        model_id = await get_default_model_id()
    except Exception:  # noqa: BLE001 - 同上，缺 model_id 不影响模型 value 归属
        model_id = ""
    if model_id:
        options["model_id"] = model_id
    return options


async def execute_standalone_schedule(session_id, agent_id, message, user_id, **kwargs):
    """Recheck account and model authority after local or distributed queueing."""
    from src.api.routes.chat_agent_execution import _execute_agent_stream
    from src.infra.task.background_tasks import (
        apply_background_restrictions,
        validate_background_execution,
    )

    request = await validate_background_execution(
        session_id, agent_id, user_id, kwargs.get("agent_options") or {}
    )
    apply_background_restrictions(request, kwargs)
    kwargs["agent_options"] = request.agent_options
    for field in (
        "persona_system_prompt",
        "disabled_tools",
        "disabled_skills",
        "enabled_skills",
        "disabled_mcp_tools",
        "enabled_mcp_servers",
        "team_id",
    ):
        kwargs[field] = getattr(request, field)
    async for event in _execute_agent_stream(session_id, agent_id, message, user_id, **kwargs):
        yield event


class ScheduledTaskRunner:
    """Execute a scheduled task: acquire lock → create record → run agent → record result."""

    async def run(self, task_id: str, trigger_type: str = "cron") -> dict:
        """Entry point for scheduled / manual task execution.

        Submits the agent and returns immediately. Completion monitoring
        (result recording, delivery, retries, lock release) runs in a
        detached background task.
        """
        storage = get_scheduled_task_storage()
        task = await storage.get_task_for_execution(task_id)
        if task is None:
            logger.warning("[Runner] task %s not found, skipping", task_id)
            return {"skipped": True, "reason": "task_not_found"}

        if not task.enabled or task.status != "active":
            return {"skipped": True, "reason": "disabled"}

        now = utc_now()
        if trigger_type != "manual":
            slot = self._build_schedule_slot(task, trigger_type, now)
            if slot is not None:
                slot_id, slot_ttl, due_at = slot
                if due_at is not None and due_at > now:
                    return {
                        "skipped": True,
                        "reason": "not_due",
                        "next_due_at": due_at.isoformat(),
                    }
                slot_claimed = await acquire_task_slot_lock(task_id, slot_id, ttl=slot_ttl)
                if not slot_claimed:
                    return {"skipped": True, "reason": "slot_contended"}

        if task.execution_mode == "conversation":
            record = await storage.enqueue_conversation(task, trigger_type)
            from src.infra.scheduler.conversation import dispatch_pending

            _spawn_monitor(dispatch_pending())
            return {
                "run_id": record["_id"],
                "status": "queued",
                "session_id": record["session_id"],
            }

        run_id = str(uuid.uuid4())

        # 1. Acquire distributed lock (multi-instance dedup)
        max_attempts = max(1, int(task.max_retries or 0) + 1)
        lock_token = await acquire_task_lock(task_id, run_id, ttl=_EXECUTION_LOCK_TTL)
        if lock_token is None:
            return {
                "skipped": True,
                "reason": "lock_contended",
                "run_id": run_id,
            }

        # 2. Create execution record
        base_session_id = self._build_session_id(task_id, run_id)
        record = TaskRunRecord.model_validate(
            {
                "_id": run_id,
                "task_id": task_id,
                "agent_id": task.agent_id,
                "trigger_type": trigger_type,
                "status": RunStatus.PENDING,
                "session_id": base_session_id,
                "input_snapshot": task.input_payload,
                "started_at": now,
                "created_at": now,
            }
        )
        await storage.create_run(record)

        # 3. Spawn detached monitor and return immediately so the APScheduler
        #    handler is not blocked by agent execution time.
        _spawn_monitor(
            self._monitor_and_finalize(
                task=task,
                run_id=run_id,
                base_session_id=base_session_id,
                lock_token=lock_token,
                max_attempts=max_attempts,
                trigger_type=trigger_type,
                started_at=now,
            )
        )
        logger.info(
            "[Runner] task=%s run=%s submitted (monitor running in background)",
            task_id,
            run_id,
        )
        return {"run_id": run_id, "status": "submitted"}

    async def _monitor_and_finalize(
        self,
        *,
        task: ScheduledTask,
        run_id: str,
        base_session_id: str,
        lock_token: str,
        max_attempts: int,
        trigger_type: str,
        started_at: datetime,
    ) -> None:
        """Detached background coroutine: wait for agent completion,
        record results, deliver to channel, retry on failure, release lock."""
        storage = get_scheduled_task_storage()
        terminal_persisted = False
        try:
            final_attempt: _AttemptResult | None = None
            for attempt in range(max_attempts):
                session_id = (
                    base_session_id if attempt == 0 else f"{base_session_id}_retry{attempt}"
                )
                await storage.update_run(
                    run_id,
                    {
                        "status": RunStatus.RUNNING,
                        "retry_count": attempt,
                        "session_id": session_id,
                    },
                )
                try:
                    result = await self._execute_agent(
                        task,
                        run_id,
                        session_id,
                        trigger_type,
                        now=started_at,
                        lock_token=lock_token,
                    )
                    final_attempt = self._classify_attempt_result(result)
                except _ExecutionLeaseLostError:
                    raise
                except Exception as exc:
                    final_attempt = _AttemptResult(
                        status=RunStatus.FAILED,
                        result={},
                        error_message=str(exc),
                    )

                if final_attempt.status == RunStatus.SUCCESS:
                    break
                if final_attempt.status != RunStatus.FAILED:
                    break
                if attempt + 1 < max_attempts:
                    logger.warning(
                        "[Runner] task=%s run=%s attempt=%d failed status=%s, retrying",
                        task.id,
                        run_id,
                        attempt,
                        final_attempt.status.value,
                    )

            assert final_attempt is not None
            try:
                delivery_result = await self._deliver_success_result(task, final_attempt, run_id)
            except Exception as exc:
                logger.warning("[Runner] result delivery failed: %s", run_id, exc_info=True)
                delivery_result = {"status": "failed", "error": str(exc)}
            if delivery_result is not None:
                final_attempt.result["delivery"] = delivery_result
            finished = utc_now()
            duration = int((finished - started_at).total_seconds() * 1000)
            update_payload: dict[str, Any] = {
                "status": final_attempt.status,
                "output_result": final_attempt.result,
                "session_id": final_attempt.result.get("session_id", base_session_id),
                "trace_id": final_attempt.result.get("trace_id"),
                "error_message": final_attempt.error_message,
                "finished_at": finished,
                "duration_ms": duration,
                "finalization_pending": True,
                "scheduled_trigger_config": task.trigger_config,
                "scheduled_timezone": task.timezone,
            }
            await storage.update_run(run_id, update_payload)
            terminal_persisted = True
            await self.finalize_standalone_run(
                {
                    **update_payload,
                    "_id": run_id,
                    "task_id": task.id,
                    "trigger_type": trigger_type,
                }
            )

            if final_attempt.status == RunStatus.SUCCESS:
                logger.info(
                    "[Runner] task=%s run=%s completed in %dms",
                    task.id,
                    run_id,
                    duration,
                )
            else:
                logger.warning(
                    "[Runner] task=%s run=%s finished status=%s after %dms: %s",
                    task.id,
                    run_id,
                    final_attempt.status.value,
                    duration,
                    final_attempt.error_message,
                )

        except Exception as exc:
            if terminal_persisted:
                logger.warning(
                    "[Runner] finalization deferred: task=%s run=%s", task.id, run_id, exc_info=True
                )
                return
            finished = utc_now()
            duration = int((finished - started_at).total_seconds() * 1000)
            failed = {
                "status": RunStatus.FAILED,
                "error_message": str(exc),
                "finished_at": finished,
                "duration_ms": duration,
                "finalization_pending": True,
                "scheduled_trigger_config": task.trigger_config,
                "scheduled_timezone": task.timezone,
            }
            await storage.update_run(run_id, failed)
            try:
                await self.finalize_standalone_run(
                    {
                        **failed,
                        "_id": run_id,
                        "task_id": task.id,
                        "trigger_type": trigger_type,
                    }
                )
            except Exception:
                logger.warning(
                    "[Runner] failed-run finalization deferred: %s", run_id, exc_info=True
                )
            logger.exception("[Runner] task=%s run=%s failed after %dms", task.id, run_id, duration)

        finally:
            await release_task_lock(task.id, lock_token)

    async def finalize_standalone_run(self, record):
        storage = get_scheduled_task_storage()
        await storage.update_task_run_stats(
            record["task_id"], record["_id"], RunStatus(record["status"])
        )
        if record["trigger_type"] == TriggerType.DATE.value and record.get(
            "scheduled_trigger_config"
        ):
            if await storage.pause_completed_date_task(
                record["task_id"], record["scheduled_trigger_config"], record["scheduled_timezone"]
            ):
                get_runtime_scheduler().unregister_job(record["task_id"])
        await storage.complete_run_finalization(record["_id"])

    # ── Internal ───────────────────────────────────

    @staticmethod
    def _build_session_id(task_id: str, run_id: str) -> str:
        return f"sch_{task_id}_{run_id[:8]}"

    @staticmethod
    def _build_schedule_slot(
        task: ScheduledTask,
        trigger_type: str,
        now: datetime,
    ) -> tuple[str, int, datetime | None] | None:
        """Return a distributed schedule slot id, TTL, and optional due time."""
        now = ensure_utc(SCHEDULED_FIRE_TIME.get() or now)
        anchor = ensure_utc(task.created_at or now)
        if trigger_type == TriggerType.INTERVAL.value and task.trigger_type == TriggerType.INTERVAL:
            seconds = max(1, int(task.trigger_config.get("seconds", 1)))
            if task.created_at is None:
                bucket = int(now.timestamp()) // seconds
                return f"interval:{bucket}", max(seconds * 2, 60), None
            elapsed = (now - anchor).total_seconds()
            if task.run_on_start and task.total_runs == 0 and elapsed < seconds:
                return f"run_on_start:{int(anchor.timestamp())}", 86400, None
            # Completion time must never shift the cadence or the cross-instance slot identity.
            slot = max(1, int(elapsed // seconds))
            due_at = anchor + timedelta(seconds=slot * seconds)
            return f"interval:{int(due_at.timestamp())}", max(seconds * 2, 60), due_at

        if task.run_on_start and task.total_runs == 0:
            return f"run_on_start:{int(anchor.timestamp())}", 86400, None

        if trigger_type == TriggerType.DATE.value and task.trigger_type == TriggerType.DATE:
            run_date = task.trigger_config.get("run_date")
            if run_date:
                due_at = ensure_utc(datetime.fromisoformat(str(run_date)))
                return f"date:{int(due_at.timestamp())}", 86400, due_at
            return f"date:{int(now.timestamp())}", 86400, None

        if trigger_type == TriggerType.CRON.value and task.trigger_type == TriggerType.CRON:
            slot_time = now.replace(microsecond=0)
            return f"cron:{int(slot_time.timestamp())}", 86400, None

        return None

    async def _execute_agent(
        self,
        task: ScheduledTask,
        run_id: str,
        session_id: str,
        trigger_type: str | None = None,
        now: datetime | None = None,
        lock_token: str | None = None,
    ) -> dict:
        """Execute the agent via BackgroundTaskManager in a dedicated session.

        ``now`` anchors the injected user-message timestamp to the run start so
        retries of the same run resend a byte-identical message (KV-cache
        stability, issue #212)."""
        from src.api.routes.chat import validate_agent_model_access
        from src.infra.session.manager import SessionManager
        from src.infra.task.background_tasks import _request_options
        from src.infra.task.manager import get_task_manager
        from src.kernel.errors import AppError, ErrorCode

        task_manager = get_task_manager()
        use_arq_backend = settings.TASK_BACKEND == "arq"

        display_message = task.input_payload.get("message", "")
        if not display_message and task.input_payload.get("prompt"):
            display_message = task.input_payload["prompt"]
        display_message = str(display_message or "")
        user_timezone = task.input_payload.get("user_timezone")
        raw_attachments = task.input_payload.get("attachments")
        attachments = (
            [dict(item) for item in raw_attachments if isinstance(item, dict)]
            if isinstance(raw_attachments, list)
            else None
        )
        message = format_scheduled_message_with_timestamp(
            display_message,
            user_timezone if isinstance(user_timezone, str) else task.timezone,
            now=now,
        )
        user = await _resolve_task_owner(task.owner_id)
        if user is None:
            raise AppError(ErrorCode.USER_NOT_FOUND)
        if "chat:write" not in (user.permissions or []):
            raise AppError(ErrorCode.PERMISSION_MISSING, args={"permission": "chat:write"})
        raw_options = task.input_payload.get("agent_options")
        agent_options = _request_options(
            {
                "agent_options": raw_options if isinstance(raw_options, dict) else {},
            }
        )
        await validate_agent_model_access(agent_options, user)
        agent_options = await _agent_options_with_default_model(agent_options)

        persona_preset_id = task.input_payload.get("persona_preset_id")
        persona_preset_id = (
            persona_preset_id if isinstance(persona_preset_id, str) and persona_preset_id else None
        )
        team_id = task.input_payload.get("team_id")
        team_id = team_id if isinstance(team_id, str) and team_id else None
        if task.agent_id != "team":
            team_id = None
        else:
            persona_preset_id = None

        persona_system_prompt: str | None = None
        enabled_skills: list[str] | None = None
        persona_snapshot: dict | None = None
        if persona_preset_id:
            from src.api.routes.chat import resolve_persona_request
            from src.kernel.schemas.agent import AgentRequest

            persona_request = AgentRequest(
                message=display_message,
                persona_preset_id=persona_preset_id,
            )
            await resolve_persona_request(persona_request, user)
            persona_system_prompt = persona_request.persona_system_prompt
            enabled_skills = persona_request.enabled_skills
            if persona_request.persona_snapshot:
                persona_snapshot = persona_request.persona_snapshot.model_dump()

        session_metadata = {
            "source": "scheduled_task",
            "scheduled_task_id": task.id,
            "executor_key": "scheduled_agent_stream",
            "scheduled_task_run_id": run_id,
            "scheduled_task_trigger_type": trigger_type or task.trigger_type.value,
            "hidden_from_conversation_list": True,
        }
        if persona_preset_id:
            session_metadata["persona_preset_id"] = persona_preset_id
        if persona_snapshot:
            session_metadata["persona_preset_name"] = persona_snapshot["name"]
            session_metadata["persona_snapshot"] = persona_snapshot
            if persona_snapshot.get("avatar"):
                session_metadata["persona_avatar"] = persona_snapshot["avatar"]
        if team_id:
            session_metadata["team_id"] = team_id

        if use_arq_backend:
            _, trace_id = await task_manager.submit_arq(
                session_id=session_id,
                agent_id=task.agent_id,
                message=message,
                user_id=task.owner_id,
                executor_key="scheduled_agent_stream",
                run_id=run_id,
                dispatch_id=f"scheduled:{run_id}:{session_id}",
                disabled_tools=task.input_payload.get("disabled_tools"),
                agent_options=agent_options,
                attachments=attachments,
                project_id=None,
                enabled_skills=enabled_skills,
                persona_system_prompt=persona_system_prompt,
                team_id=team_id,
                session_name=f"{task.name}",
                display_message=display_message,
                recommendation_input=display_message,
                session_metadata=session_metadata,
                auto_mode=True,
                write_user_message_immediately=True,
            )
        else:
            _, trace_id = await task_manager.submit(
                session_id=session_id,
                agent_id=task.agent_id,
                message=message,
                user_id=task.owner_id,
                executor=execute_standalone_schedule,
                run_id=run_id,
                disabled_tools=task.input_payload.get("disabled_tools"),
                agent_options=agent_options,
                attachments=attachments,
                project_id=None,
                enabled_skills=enabled_skills,
                persona_system_prompt=persona_system_prompt,
                team_id=team_id,
                session_name=f"{task.name}",
                display_message=display_message,
                recommendation_input=display_message,
                session_metadata=session_metadata,
                auto_mode=True,
                write_user_message_immediately=True,
            )
        await SessionManager().update_session_metadata(
            session_id,
            session_metadata,
        )

        result = await self._wait_for_completion(
            task_manager, session_id, run_id, task.owner_id, task_id=task.id, lock_token=lock_token
        )
        result["session_id"] = session_id
        result["trace_id"] = trace_id
        return result

    async def _wait_for_completion(
        self,
        task_manager: Any,
        session_id: str,
        run_id: str,
        user_id: str,
        *,
        task_id: str | None = None,
        lock_token: str | None = None,
    ) -> dict:
        """Wait for a terminal state, renewing ownership regardless of elapsed time."""
        from src.infra.task.status import TaskStatus

        while True:
            if task_id and lock_token:
                try:
                    owned = await extend_task_lock(
                        task_id, lock_token, extra_seconds=_EXECUTION_LOCK_TTL
                    )
                except Exception:
                    logger.exception("Scheduled task execution lease renewal failed: %s", task_id)
                    owned = False
                if not owned:
                    try:
                        await task_manager.cancel_run(run_id, user_id=user_id)
                    finally:
                        raise _ExecutionLeaseLostError(
                            "Scheduled task execution ownership was lost"
                        )
            status = await task_manager.get_run_status(session_id, run_id)
            if status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.EXPIRED,
            ):
                return {"session_status": status.value if hasattr(status, "value") else str(status)}
            await asyncio.sleep(_POLL_INTERVAL)

    @staticmethod
    def _classify_attempt_result(result: dict[str, Any]) -> _AttemptResult:
        """Map BackgroundTaskManager terminal state into scheduled-task status."""
        session_status = str(result.get("session_status") or "").lower()
        if session_status == "completed":
            return _AttemptResult(status=RunStatus.SUCCESS, result=result)
        if session_status == "timeout":
            return _AttemptResult(
                status=RunStatus.TIMEOUT,
                result=result,
                error_message="Scheduled task execution timed out",
            )
        if session_status in {"failed", "cancelled", "expired"}:
            return _AttemptResult(
                status=RunStatus.FAILED,
                result=result,
                error_message=f"Agent run ended with status: {session_status}",
            )
        return _AttemptResult(
            status=RunStatus.FAILED,
            result=result,
            error_message=f"Unexpected agent run status: {session_status or 'unknown'}",
        )

    async def _deliver_success_result(
        self,
        task: ScheduledTask,
        attempt: _AttemptResult,
        run_id: str,
    ) -> dict[str, Any] | None:
        """Send a successful scheduled-task result back to the configured channel."""
        delivery = task.delivery
        if (
            attempt.status != RunStatus.SUCCESS
            or delivery is None
            or not delivery.enabled
            or not delivery.send_on_success
        ):
            return None

        session_id = attempt.result.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return {
                "status": "skipped",
                "reason": "missing_session_id",
                "channel_type": delivery.channel_type.value,
                "chat_id": delivery.chat_id,
                "channel_instance_id": delivery.channel_instance_id,
            }

        events = await get_trace_storage().get_run_events(session_id, run_id)
        content = self._extract_channel_delivery_text(events, delivery.max_content_chars)
        if not content:
            return {
                "status": "skipped",
                "reason": "empty_result",
                "channel_type": delivery.channel_type.value,
                "chat_id": delivery.chat_id,
                "channel_instance_id": delivery.channel_instance_id,
            }

        try:
            sent = await get_channel_coordinator().send_message(
                task.owner_id,
                delivery.channel_type,
                delivery.chat_id,
                content,
                instance_id=delivery.channel_instance_id,
            )
        except Exception as exc:
            logger.warning(
                "[Runner] failed to deliver task=%s result to channel=%s chat=%s: %s",
                task.id,
                delivery.channel_type.value,
                delivery.chat_id,
                exc,
            )
            return {
                "status": "failed",
                "error": str(exc),
                "channel_type": delivery.channel_type.value,
                "chat_id": delivery.chat_id,
                "channel_instance_id": delivery.channel_instance_id,
            }

        return {
            "status": "sent" if sent else "failed",
            **({} if sent else {"error": "channel_send_returned_false"}),
            "channel_type": delivery.channel_type.value,
            "chat_id": delivery.chat_id,
            "channel_instance_id": delivery.channel_instance_id,
        }

    @staticmethod
    def _extract_channel_delivery_text(
        events: list[dict[str, Any]],
        max_content_chars: int,
    ) -> str:
        """Extract assistant text from trace events for channel delivery."""
        from src.infra.channel.delivery import extract_delivery_text

        return extract_delivery_text(events, max_chars=max_content_chars)


# ── Singleton ──────────────────────────────────────

_runner: Optional[ScheduledTaskRunner] = None


def get_scheduled_task_runner() -> ScheduledTaskRunner:
    global _runner
    if _runner is None:
        _runner = ScheduledTaskRunner()
    return _runner


async def reconcile_standalone_finalizations():
    storage = get_scheduled_task_storage()
    for record in await storage.pending_standalone_finalizations():
        try:
            await get_scheduled_task_runner().finalize_standalone_run(record)
        except Exception:
            logger.warning(
                "[Runner] standalone finalization deferred: %s", record["_id"], exc_info=True
            )
