"""Scheduled task execution engine.

Connects APScheduler triggers with the existing BackgroundTaskManager
so that dynamically-created tasks run through the normal agent pipeline.
"""

from __future__ import annotations

import asyncio
import collections.abc
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from src.infra.channel.manager import get_channel_coordinator
from src.infra.chat.user_message_timestamp import format_user_message_with_timestamp
from src.infra.logging import get_logger
from src.infra.role.storage import RoleStorage
from src.infra.scheduler.locks import (
    acquire_task_lock,
    acquire_task_slot_lock,
    release_task_lock,
)
from src.infra.scheduler.runtime import get_runtime_scheduler
from src.infra.scheduler.storage import get_scheduled_task_storage
from src.infra.session.trace_storage import get_trace_storage
from src.infra.user.storage import UserStorage
from src.infra.utils.datetime import ensure_utc, utc_now
from src.kernel.config import settings
from src.kernel.schemas.scheduled_task import (
    RunStatus,
    ScheduledTask,
    ScheduledTaskStatus,
    TaskRunRecord,
    TriggerType,
)
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

_POLL_INTERVAL = 2  # seconds between status checks when waiting for completion
_DEFAULT_TIMEOUT = 3600  # 60 minutes
_ASSISTANT_EVENT_TYPES = {
    "message",
    "assistant:message",
    "ai:message",
    "assistant",
    "ai",
    "content",
    "message:chunk",
    "summary",
}
_ASSISTANT_ROLES = {"assistant", "ai"}

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
    user = await UserStorage().get_by_id(user_id)
    if not user:
        return None

    roles = await RoleStorage().get_by_names(user.roles or [])
    permissions: set[str] = set()
    for role in roles:
        for permission in role.permissions:
            permissions.add(permission if isinstance(permission, str) else permission.value)

    return TokenPayload(
        sub=user.id,
        username=user.username,
        roles=[r.name for r in roles],
        permissions=sorted(permissions),
    )


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

        run_id = str(uuid.uuid4())

        # 1. Acquire distributed lock (multi-instance dedup)
        max_attempts = max(1, int(task.max_retries or 0) + 1)
        lock_token = await acquire_task_lock(
            task_id, run_id, ttl=task.timeout_seconds * max_attempts
        )
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
                        task, run_id, session_id, trigger_type, now=started_at
                    )
                    final_attempt = self._classify_attempt_result(result)
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
            delivery_result = await self._deliver_success_result(task, final_attempt, run_id)
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
            }
            await storage.update_run(run_id, update_payload)
            await storage.update_task_run_stats(task.id, run_id, final_attempt.status)

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
            finished = utc_now()
            duration = int((finished - started_at).total_seconds() * 1000)
            await storage.update_run(
                run_id,
                {
                    "status": RunStatus.FAILED,
                    "error_message": str(exc),
                    "finished_at": finished,
                    "duration_ms": duration,
                },
            )
            await storage.update_task_run_stats(task.id, run_id, RunStatus.FAILED)
            logger.exception("[Runner] task=%s run=%s failed after %dms", task.id, run_id, duration)

        finally:
            await release_task_lock(task.id, lock_token)
            if task.trigger_type == TriggerType.DATE and trigger_type == TriggerType.DATE.value:
                await storage.update_task(
                    task.id,
                    {"status": ScheduledTaskStatus.PAUSED, "enabled": False},
                )
                get_runtime_scheduler().unregister_job(task.id)

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
        if task.run_on_start and task.total_runs == 0:
            anchor = task.created_at or now
            return f"run_on_start:{int(ensure_utc(anchor).timestamp())}", 86400, None

        if trigger_type == TriggerType.INTERVAL.value and task.trigger_type == TriggerType.INTERVAL:
            seconds = max(1, int(task.trigger_config.get("seconds", 1)))
            interval_anchor = task.last_run_at or task.created_at
            if interval_anchor is not None:
                due_at = ensure_utc(interval_anchor) + timedelta(seconds=seconds)
                return f"interval:{int(due_at.timestamp())}", max(seconds * 2, 60), due_at
            bucket = int(now.timestamp()) // seconds
            return f"interval:{bucket}", max(seconds * 2, 60), None

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
    ) -> dict:
        """Execute the agent via BackgroundTaskManager in a dedicated session.

        ``now`` anchors the injected user-message timestamp to the run start so
        retries of the same run resend a byte-identical message (KV-cache
        stability, issue #212)."""
        from src.infra.session.manager import SessionManager
        from src.infra.task.concurrency import get_registered_executor
        from src.infra.task.manager import get_task_manager

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
        message = format_user_message_with_timestamp(
            display_message,
            user_timezone if isinstance(user_timezone, str) else None,
            now=now,
        )
        agent_options = task.input_payload.get("agent_options")
        if isinstance(agent_options, dict):
            from src.api.routes.chat import validate_agent_model_access

            user = await _resolve_task_owner(task.owner_id)
            if user is None:
                raise RuntimeError(f"Scheduled task owner '{task.owner_id}' not found")
            await validate_agent_model_access(agent_options, user)
        else:
            agent_options = None

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

            user = await _resolve_task_owner(task.owner_id)
            if user is None:
                raise RuntimeError(f"Scheduled task owner '{task.owner_id}' not found")
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
                executor_key="agent_stream",
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
        else:
            executor_fn = get_registered_executor("agent_stream")
            if executor_fn is None:
                raise RuntimeError(
                    "agent_stream executor not registered — "
                    "ensure the chat router is loaded before scheduled tasks run"
                )
            _, trace_id = await task_manager.submit(
                session_id=session_id,
                agent_id=task.agent_id,
                message=message,
                user_id=task.owner_id,
                executor=executor_fn,
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
            task_manager, session_id, run_id, task.owner_id, task.timeout_seconds
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
        timeout_seconds: int = _DEFAULT_TIMEOUT,
    ) -> dict:
        """Poll task status until completion or timeout."""
        from src.infra.task.status import TaskStatus

        start = time.monotonic()
        while time.monotonic() - start < timeout_seconds:
            status = await task_manager.get_run_status(session_id, run_id)
            if status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.EXPIRED,
            ):
                return {
                    "session_status": (status.value if hasattr(status, "value") else str(status))
                }
            await asyncio.sleep(_POLL_INTERVAL)

        try:
            await task_manager.cancel_run(run_id, user_id=user_id)
        except Exception as exc:
            logger.warning(
                "[Runner] failed to cancel timed-out task run=%s session=%s: %s",
                run_id,
                session_id,
                exc,
            )
        return {"session_status": "timeout"}

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
        parts: list[str] = []
        chunk_parts: list[str] = []

        def flush_chunks() -> None:
            if not chunk_parts:
                return
            chunk_text = "".join(chunk_parts).strip()
            if chunk_text:
                parts.append(chunk_text)
            chunk_parts.clear()

        for event in events:
            event_type = str(event.get("event_type") or "")
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            role = str(data.get("role") or "").lower()
            if role in {"user", "human"}:
                continue
            if event_type == "message" and role not in _ASSISTANT_ROLES:
                continue
            if event_type not in _ASSISTANT_EVENT_TYPES and role not in _ASSISTANT_ROLES:
                continue

            content = data.get("content")
            if content is None:
                content = data.get("message")
            if not isinstance(content, str) or not content.strip():
                continue

            if event_type == "message:chunk":
                chunk_parts.append(content)
            else:
                flush_chunks()
                parts.append(content.strip())

        flush_chunks()
        text = "\n".join(parts).strip()
        if len(text) > max_content_chars:
            return text[:max_content_chars].rstrip()
        return text


# ── Singleton ──────────────────────────────────────

_runner: Optional[ScheduledTaskRunner] = None


def get_scheduled_task_runner() -> ScheduledTaskRunner:
    global _runner
    if _runner is None:
        _runner = ScheduledTaskRunner()
    return _runner
