"""Durable, coalesced wakeups through the authorized conversation submission path."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar

from src.infra.utils.datetime import ensure_utc, utc_now
from src.kernel.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)
SCHEDULED_SUBMISSION: ContextVar[dict | None] = ContextVar("scheduled_submission", default=None)
BUSY = {"queued", "pending", "starting", "running", "waiting_human", "cancelling", "recovering"}


class ConversationBusyError(Exception):
    """Keep the durable wakeup pending until the conversation becomes idle."""


async def ensure_idle(session):
    from src.infra.goal_continuation import _has_pending

    metadata = session.metadata or {}
    if (
        metadata.get("task_status") in BUSY
        or metadata.get("persistent_goal_status") in {"active", "waiting_human"}
        or await _has_pending(session.id, session.user_id)
    ):
        raise ConversationBusyError()


def build_request(task, session, run_id):
    from src.infra.task.background_tasks import INHERITED_FIELDS, _request_options
    from src.kernel.schemas.agent import AgentRequest

    metadata = session.metadata or {}
    instructions = str(task.input_payload.get("message") or task.input_payload.get("prompt") or "")
    message = (
        f"Scheduled follow-up: {task.name} (task {task.id}, run {run_id}).\n"
        "Use this conversation's latest context and previous results. Avoid repeating completed work.\n"
        + instructions
    )
    if task.notification_policy == "meaningful_changes":
        message += (
            "\nIf there is no meaningful change and no action or human input is needed, "
            "respond with exactly NO_UPDATE. Otherwise report the findings."
        )
    return AgentRequest(
        session_id=session.id,
        message=message,
        agent_options=_request_options(metadata),
        project_id=metadata.get("project_id"),
        attachments=task.input_payload.get("attachments"),
        workspace_dir=metadata.get("workspace_dir") or "./workspace",
        **{key: metadata[key] for key in INHERITED_FIELDS if metadata.get(key) is not None},
    )


@asynccontextmanager
async def conversation_submission(session_id, user_id):
    """Serialize admission with foreground chat; the persisted run status owns execution."""
    if not session_id:
        yield
        return
    from src.infra.channel.chat_lease import ChatLease
    from src.infra.scheduler.storage import get_scheduled_task_storage
    from src.infra.session.manager import SessionManager

    identity = hashlib.sha256(f"{user_id}\0{session_id}".encode()).hexdigest()
    lease = ChatLease(f"chat:submission:{identity}", ttl=90)
    if not await lease.acquire():
        if SCHEDULED_SUBMISSION.get():
            raise ConversationBusyError()
        raise AppError(ErrorCode.CONFLICT)
    owner = asyncio.current_task()

    async def renew():
        while True:
            await asyncio.sleep(20)
            try:
                renewed = await lease.renew()
            except Exception:
                renewed = False
            if not renewed:
                if owner:
                    owner.cancel()
                return

    renewal = asyncio.create_task(renew())
    try:
        session = await SessionManager().get_session(session_id)
        scheduled = SCHEDULED_SUBMISSION.get()
        if scheduled:
            if not session or session.user_id != user_id:
                raise AppError(ErrorCode.SCHEDULED_TASK_ERROR)
            await ensure_idle(session)
            task = await get_scheduled_task_storage().get_task(scheduled["task_id"])
            if not task or not task.enabled or task.status != "active":
                raise AppError(ErrorCode.SCHEDULED_TASK_ERROR)
        elif session and (session.metadata or {}).get("task_status") in BUSY:
            # A normal submit must not supersede a running scheduled check.
            current = (
                await get_scheduled_task_storage()
                ._get_collection("task_run_records")
                .find_one(
                    {
                        "_id": session.metadata.get("current_run_id"),
                        "conversation_state": {"$in": ["submitting", "submitted"]},
                    }
                )
            )
            if current:
                raise AppError(ErrorCode.CONFLICT)
        yield
    finally:
        renewal.cancel()
        await asyncio.gather(renewal, return_exceptions=True)
        await lease.release()


def is_quiet_result(status, policy, text):
    return status == "completed" and policy == "meaningful_changes" and text.strip() == "NO_UPDATE"


async def completion_context(session_id, run_id, status):
    """Resolve identity from the exact run, never overwrite original session metadata."""
    from src.infra.scheduler.storage import get_scheduled_task_storage

    storage = get_scheduled_task_storage()
    record = await storage._get_collection("task_run_records").find_one(
        {
            "_id": run_id,
            "session_id": session_id,
        }
    )
    if not record:
        return None, False
    task = await storage.get_task(record["task_id"])
    quiet = False
    if task and status == "completed" and task.notification_policy == "meaningful_changes":
        from src.infra.channel.delivery import extract_delivery_text
        from src.infra.session.trace_storage import get_trace_storage

        events = await get_trace_storage().get_run_events(session_id, run_id)
        quiet = is_quiet_result(
            status, task.notification_policy, extract_delivery_text(events, max_chars=20000)
        )
    if task and status == "completed":
        await storage.update_run(run_id, {"quiet": quiet})
    return record["task_id"], quiet


async def _finish(storage, record, status, error=None):
    from src.infra.session.trace_storage import get_trace_storage
    from src.kernel.schemas.scheduled_task import RunStatus

    trace = await get_trace_storage().collection.find_one(
        {"session_id": record["session_id"], "run_id": record["_id"]},
        {"completed_at": 1, "started_at": 1},
        sort=[("started_at", -1)],
    )
    finished_at = (trace or {}).get("completed_at") or utc_now()
    values = {
        "conversation_state": "finished",
        "conversation_pending": False,
        "status": status,
        "finished_at": finished_at,
        "error_message": error,
    }
    result = await storage._get_collection("task_run_records").update_one(
        {"_id": record["_id"], "conversation_state": record["conversation_state"]},
        {"$set": values},
    )
    if result.modified_count:
        await storage.update_task_run_stats(record["task_id"], record["_id"], RunStatus(status))
        task = await storage.get_task(record["task_id"])
        if status == "success" and task and task.delivery:
            from src.infra.scheduler.runner import ScheduledTaskRunner, _AttemptResult

            _, quiet = await completion_context(record["session_id"], record["_id"], "completed")
            if not quiet:
                delivery = await ScheduledTaskRunner()._deliver_success_result(
                    task,
                    _AttemptResult(
                        status=RunStatus.SUCCESS, result={"session_id": record["session_id"]}
                    ),
                    record["_id"],
                )
                if delivery is not None:
                    await storage.update_run(
                        record["_id"], {"output_result": {"delivery": delivery}}
                    )
        if status in {"failed", "timeout"}:
            from src.infra.task.manager import get_task_manager
            from src.infra.task.status import TaskStatus

            await (
                get_task_manager()
                ._ensure_executor()
                ._send_task_notification(
                    record["session_id"],
                    record["_id"],
                    TaskStatus.FAILED,
                    record["owner_id"],
                )
            )
        if task and task.trigger_type == "date":
            await storage.update_task(task.id, {"enabled": False, "status": "paused"})


async def dispatch_pending():
    from src.infra.scheduler.storage import get_scheduled_task_storage
    from src.infra.session.manager import SessionManager
    from src.infra.task.manager import get_task_manager

    storage = get_scheduled_task_storage()
    for record in await storage.pending_conversation_runs():
        try:
            task = await storage.get_task(record["task_id"])
            if record["conversation_state"] == "submitted":
                state = await get_task_manager().get_run_status(record["session_id"], record["_id"])
                state = getattr(state, "value", state)
                if state in {"completed", "failed", "cancelled", "expired"}:
                    await _finish(storage, record, "success" if state == "completed" else "failed")
                continue
            if record["conversation_state"] == "submitting":
                if ensure_utc(record["claim_until"]) > utc_now():
                    continue
                # Admission may have succeeded before a crash. Reconcile, never replay.
                session = await SessionManager().get_session(record["session_id"])
                if session and (session.metadata or {}).get("current_run_id") == record["_id"]:
                    await storage.update_run(
                        record["_id"],
                        {
                            "conversation_state": "submitted",
                            "conversation_pending": False,
                            "started_at": record.get("created_at"),
                        },
                    )
                else:
                    await _finish(
                        storage,
                        record,
                        "failed",
                        "Submission outcome uncertain; inspect before running again",
                    )
                continue
            if not task or not task.enabled or task.status != "active":
                await _finish(storage, record, "skipped")
                continue
            session = (
                await SessionManager().get_session(task.target_session_id)
                if task.target_session_id
                else None
            )
            if not session or session.user_id != task.owner_id:
                await storage.update_task(task.id, {"enabled": False, "status": "paused"})
                await _finish(storage, record, "failed", "Target conversation is unavailable")
                continue
            try:
                await ensure_idle(session)
            except ConversationBusyError:
                continue
            claimed = await storage.claim_conversation_run(record["_id"])
            if not claimed:
                continue
            from starlette.requests import Request

            from src.api.deps import _load_user_payload
            from src.api.routes.chat import chat_stream

            try:
                user = await _load_user_payload(task.owner_id)
            except AppError:
                await storage.update_task(task.id, {"enabled": False, "status": "paused"})
                await _finish(storage, claimed, "failed", "Task owner is unavailable")
                continue
            if "chat:write" not in user.permissions:
                await storage.update_task(task.id, {"enabled": False, "status": "paused"})
                await _finish(storage, claimed, "failed", "Chat permission is unavailable")
                continue
            token = SCHEDULED_SUBMISSION.set({"task_id": task.id, "run_id": record["_id"]})
            try:
                result = await chat_stream(
                    build_request(task, session, record["_id"]),
                    Request(
                        {
                            "type": "http",
                            "headers": [
                                (
                                    b"accept-language",
                                    str((session.metadata or {}).get("language") or "en").encode(),
                                )
                            ],
                            "scheme": "http",
                            "server": ("127.0.0.1", 8000),
                            "path": "/api/chat/stream",
                        }
                    ),
                    agent_id=(session.metadata or {}).get("agent_id", task.agent_id),
                    user=user,
                )
            except ConversationBusyError:
                await storage.update_run(record["_id"], {"conversation_state": "pending"})
                continue
            finally:
                SCHEDULED_SUBMISSION.reset(token)
            await storage.update_run(
                record["_id"],
                {
                    "conversation_state": "submitted",
                    "conversation_pending": False,
                    "status": "running",
                    "started_at": utc_now(),
                    "owner_id": task.owner_id,
                    "timeout_seconds": task.timeout_seconds,
                    "trace_id": result.get("trace_id"),
                },
            )
        except Exception:
            # Retain uncertain admission for reconciliation; don't replay external work.
            logger.exception("Conversation schedule dispatch deferred: run=%s", record["_id"])


async def execute_conversation_schedule(session_id, agent_id, message, user_id, **kwargs):
    """Revalidate exact-run authority and current account permissions at worker admission."""
    from src.api.routes.chat_agent_execution import _execute_agent_stream
    from src.infra.task.background_tasks import validate_background_execution

    await validate_scheduled_run_admission(session_id, user_id, kwargs["presenter"].run_id)
    request = await validate_background_execution(
        session_id, agent_id, user_id, kwargs.get("agent_options") or {}
    )
    kwargs["agent_options"] = request.agent_options
    for key in (
        "persona_system_prompt",
        "disabled_tools",
        "disabled_skills",
        "enabled_skills",
        "disabled_mcp_tools",
        "enabled_mcp_servers",
        "team_id",
    ):
        kwargs[key] = getattr(request, key)
    async for event in _execute_agent_stream(session_id, agent_id, message, user_id, **kwargs):
        yield event


async def validate_scheduled_run_admission(session_id, user_id, run_id):
    from src.infra.goal_runtime import GoalRunAdmissionError
    from src.infra.scheduler.storage import get_scheduled_task_storage
    from src.infra.session.manager import SessionManager

    session = await SessionManager().get_session(session_id)
    record = (
        await get_scheduled_task_storage()
        ._get_collection("task_run_records")
        .find_one(
            {
                "_id": run_id,
                "session_id": session_id,
                "owner_id": user_id,
                "conversation_state": {"$in": ["submitting", "submitted"]},
            }
        )
    )
    metadata = (session.metadata or {}) if session else {}
    terminal = metadata.get("task_status") in {"completed", "cancelled", "cancelling", "expired"}
    failed = metadata.get("task_status") == "failed" and (
        metadata.get("task_recoverable") is not True
        or metadata.get("task_error_code") == "cancelled"
    )
    if (
        not session
        or session.user_id != user_id
        or not record
        or metadata.get("current_run_id") != run_id
        or terminal
        or failed
    ):
        raise GoalRunAdmissionError("Scheduled run no longer owns the conversation")
