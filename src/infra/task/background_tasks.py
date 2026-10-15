"""Detached work uses a separate chat session and the normal authorized task queue."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from contextvars import ContextVar
from uuid import NAMESPACE_URL, uuid5

from src.infra.task.background_task_store import BackgroundTaskStore
from src.infra.task.concurrency import register_executor
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.session import SessionCreate

logger = logging.getLogger(__name__)
BACKGROUND_SUBMISSION_RUN: ContextVar[str | None] = ContextVar(
    "background_submission_run", default=None
)
BACKGROUND_EXECUTOR_KEY = "background_agent_stream"
BACKGROUND_RESTRICTIONS: ContextVar[dict | None] = ContextVar(
    "background_restrictions", default=None
)
INHERITED_FIELDS = (
    "disabled_tools",
    "disabled_skills",
    "enabled_skills",
    "disabled_mcp_tools",
    "enabled_mcp_servers",
    "persona_preset_id",
    "team_id",
    "user_timezone",
)


async def _load_user(user_id):
    from src.api.deps import _load_user_payload

    user = await _load_user_payload(user_id)
    _check_permission(user)
    return user


def _check_permission(user):
    if "chat:write" not in user.permissions:
        raise AppError(ErrorCode.PERMISSION_MISSING, args={"permission": "chat:write"})


async def _submit(*args, **kwargs):
    from src.api.routes.chat import chat_stream

    return await chat_stream(*args, **kwargs)


def _request_options(metadata):
    # Resolved provider configuration and cached authority never cross admission.
    options = metadata.get("agent_options") or {}
    return {
        key: value
        for key, value in options.items()
        if not key.startswith("_") and key not in {"api_key", "base_url", "model_config"}
    }


def apply_background_restrictions(request, restrictions):
    for field in ("disabled_tools", "disabled_skills", "disabled_mcp_tools"):
        existing = getattr(request, field) or []
        setattr(request, field, list(dict.fromkeys([*existing, *restrictions.get(field, [])])))
    for field in ("enabled_skills", "enabled_mcp_servers"):
        allowed = restrictions.get(field)
        if allowed is not None:
            selected = getattr(request, field)
            intersection = (
                list(allowed)
                if selected is None
                else [value for value in selected if value in allowed]
            )
            if not intersection:
                raise AppError(ErrorCode.PERMISSION_MISSING, args={"permission": field})
            setattr(request, field, intersection)


async def validate_background_execution(session_id, agent_id, user_id, options):
    """Recheck account, roles, model, persona and team before every worker execution."""
    from src.api.routes.chat import validate_agent_model_access
    from src.api.routes.chat_request_config import resolve_persona_request
    from src.api.routes.chat_validation import validate_team_agent_request
    from src.infra.session.manager import SessionManager

    session = await SessionManager().get_session(session_id)
    if session is None or session.user_id != user_id:
        raise AppError(ErrorCode.PERMISSION_MISSING, args={"permission": "chat:write"})
    user = await _load_user(user_id)
    metadata = session.metadata or {}
    request = AgentRequest(
        message="",
        agent_options=_request_options({"agent_options": options}),
        **{key: metadata[key] for key in INHERITED_FIELDS if key in metadata},
    )
    validate_team_agent_request(agent_id, request)
    await resolve_persona_request(request, user)
    await validate_agent_model_access(request.agent_options, user)
    apply_background_restrictions(request, metadata.get("background_restrictions") or metadata)
    return request


async def execute_background_stream(session_id, agent_id, message, user_id, **kwargs):
    from src.api.routes.chat_agent_execution import _execute_agent_stream
    from src.infra.task.background_admission import validate_background_run_admission

    presenter = kwargs.get("presenter")
    run_id = getattr(presenter, "run_id", None)
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Background execution requires its registered run ID")
    await validate_background_run_admission(session_id, user_id, run_id)
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


class BackgroundTaskService:
    def __init__(
        self, *, store=None, sessions=None, load_user=None, submit=None, publish_attention=None
    ):
        from src.infra.session.manager import SessionManager

        self.store = store or BackgroundTaskStore()
        self.sessions = sessions or SessionManager()
        self.load_user = load_user or _load_user
        self.submit = submit or _submit
        from src.infra.task.background_attention import publish_background_attention

        self.publish_attention = publish_attention or publish_background_attention

    async def start(
        self,
        *,
        user_id,
        parent_session_id,
        parent_run_id,
        call_id,
        description,
        agent_id="",
        model_id="",
        persona_preset_id="",
    ):
        if not description.strip() or not call_id or not parent_run_id:
            raise ValueError("A task description and source run/tool call are required")
        parent = await self.sessions.get_session(parent_session_id)
        if parent is None or parent.user_id != user_id:
            raise AppError(ErrorCode.PERMISSION_MISSING, args={"permission": "chat:write"})
        metadata = parent.metadata or {}
        if metadata.get("current_run_id") != parent_run_id:
            raise ValueError("The parent run no longer owns this conversation")
        if "start_background_task" in (metadata.get("disabled_tools") or []):
            raise AppError(
                ErrorCode.PERMISSION_MISSING, args={"permission": "start_background_task"}
            )
        if int(metadata.get("background_depth") or 0) >= 1:
            raise ValueError("Detached background task depth limit reached")
        user = await self.load_user(user_id)
        _check_permission(user)
        identity = hashlib.sha256(
            f"{user_id}\0{parent_session_id}\0{parent_run_id}\0{call_id}".encode()
        ).hexdigest()
        options = _request_options(metadata)
        if model_id:
            options = {**options, "model_id": model_id}
            options.pop("model", None)
        config = {key: metadata[key] for key in INHERITED_FIELDS if metadata.get(key) is not None}
        if persona_preset_id:
            config["persona_preset_id"] = persona_preset_id
        record = await self.store.reserve(
            {
                "_id": identity,
                "state": "reserved",
                "user_id": user_id,
                "parent_session_id": parent_session_id,
                "parent_run_id": parent_run_id,
                "call_id": call_id,
                "session_id": str(uuid5(NAMESPACE_URL, f"background:{identity}")),
                "run_id": str(uuid5(NAMESPACE_URL, f"background-run:{identity}")),
                "description": description,
                "agent_id": agent_id or metadata.get("agent_id") or "search",
                "agent_options": options,
                "config": config,
                "language": metadata.get("language") or "en",
                "execution_mode": settings.TASK_BACKEND,
                "created_at": utc_now(),
            }
        )
        if record["state"] == "reserved":
            claimed = await self.store.claim(identity)
            if claimed:
                return await self._dispatch(claimed)
        return self._result(record)

    def _result(self, record):
        result = {
            key: record[key]
            for key in ("session_id", "run_id", "parent_session_id", "execution_mode")
        }
        result.update(task_id=record["_id"], status=record.get("status", "queued"))
        if record["state"] in {"uncertain", "failed"}:
            result.update(
                status="error",
                error_code="background_task_uncertain"
                if record["state"] == "uncertain"
                else "background_task_unavailable",
            )
        return result

    async def _ensure_child_session(self, record, *, attention=False):
        existing = await self.sessions.get_session(record["session_id"])
        if existing is not None:
            if (
                existing.user_id != record["user_id"]
                or existing.metadata.get("background_task_id") != record["_id"]
            ):
                raise ValueError("Independent session identity is already owned")
            return
        metadata = {
            **record["config"],
            "background_restrictions": record["config"],
            "agent_options": record["agent_options"],
            "agent_id": record["agent_id"],
            "executor_key": BACKGROUND_EXECUTOR_KEY,
            "background_task_id": record["_id"],
            "background_parent_session_id": record["parent_session_id"],
            "background_parent_run_id": record["parent_run_id"],
            "background_source_tool_call_id": record["call_id"],
            "background_depth": 1,
            "background_execution_mode": record["execution_mode"],
        }
        if attention:
            metadata.update(task_status="failed", background_admission_state=record["state"])
        await self.sessions.storage.create(
            SessionCreate(name=record["description"][:80], metadata=metadata),
            user_id=record["user_id"],
            session_id=record["session_id"],
        )

    async def _attention(self, record, *, ensure_session=True):
        try:
            if ensure_session:
                await self._ensure_child_session(record, attention=True)
            await self.publish_attention(record, record["state"], self.sessions)
            await self.store.mark_attention_delivered(record["_id"])
        except Exception:
            logger.warning("Background admission attention pending: task=%s", record["_id"])

    async def _dispatch(self, record):
        from starlette.requests import Request

        from src.infra.goal_continuation import GOAL_DISPATCH
        from src.infra.goal_runtime import SUBMISSION_ACCEPTED, SUBMISSION_GOAL

        register_executor(BACKGROUND_EXECUTOR_KEY, execute_background_stream)
        token = record["lease_token"]
        try:
            user = await self.load_user(record["user_id"])
            _check_permission(user)
        except Exception:
            await self.store.finish(record["_id"], token, "failed", attention_pending=True)
            await self._attention({**record, "state": "failed"})
            return self._result({**record, "state": "failed"})
        request = AgentRequest(
            message=record["description"],
            session_id=record["session_id"],
            agent_options=record["agent_options"],
            **record["config"],
        )
        http = Request(
            {
                "type": "http",
                "scheme": "http",
                "server": ("127.0.0.1", 8000),
                "path": "/api/chat/stream",
                "headers": [(b"accept-language", record["language"].encode())],
            }
        )
        bindings = [
            (GOAL_DISPATCH, GOAL_DISPATCH.set(None)),
            (SUBMISSION_GOAL, SUBMISSION_GOAL.set(None)),
            (SUBMISSION_ACCEPTED, SUBMISSION_ACCEPTED.set(False)),
            (BACKGROUND_SUBMISSION_RUN, BACKGROUND_SUBMISSION_RUN.set(record["run_id"])),
            (BACKGROUND_RESTRICTIONS, BACKGROUND_RESTRICTIONS.set(record["config"])),
        ]
        child_created = False
        try:
            async with asyncio.timeout(90):
                await self._ensure_child_session(record)
                child_created = True
                value = await self.submit(request, http, agent_id=record["agent_id"], user=user)
            status = "queued" if value.get("status") == "queued" else "running"
            await self.store.finish(record["_id"], token, "submitted", status=status)
            return self._result({**record, "state": "submitted", "status": status})
        except BaseException as exc:
            # Admission may already have persisted/enqueued work. Never issue a new run.
            await self.store.finish(record["_id"], token, "uncertain", attention_pending=True)
            await self._attention(
                {**record, "state": "uncertain"}, ensure_session=not child_created
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
            logger.warning("Background admission uncertain: task=%s", record["_id"])
            return self._result({**record, "state": "uncertain"})
        finally:
            for variable, binding in reversed(bindings):
                variable.reset(binding)

    async def recover(self, record):
        if record["state"] in {"failed", "uncertain"}:
            await self._attention(record)
            return
        if record["state"] == "reserved":
            claimed = await self.store.claim(record["_id"])
            if claimed:
                await self._dispatch(claimed)
            return
        session = await self.sessions.get_session(record["session_id"])
        owns_run = bool(
            session
            and session.user_id == record["user_id"]
            and session.metadata.get("current_run_id") == record["run_id"]
        )
        if (
            owns_run
            and session is not None
            and record["execution_mode"] == "arq"
            and session.metadata.get("task_status") in ("queued", "pending")
        ):
            from src.infra.task.arq_payloads import TaskArqPayloadStore
            from src.infra.task.manager import get_task_manager

            payload = await TaskArqPayloadStore().load(record["run_id"])
            if payload:
                pool = await get_task_manager()._get_arq_pool()
                await pool.enqueue_job("run_agent_task", record["run_id"], _job_id=record["run_id"])
        await self.store.finish(
            record["_id"],
            record["lease_token"],
            "submitted" if owns_run else "uncertain",
            attention_pending=not owns_run,
        )
        if not owns_run:
            await self._attention({**record, "state": "uncertain"})


async def scan_background_tasks(ctx=None):
    del ctx
    service = BackgroundTaskService()
    try:
        async with asyncio.timeout(30):
            for record in await service.store.recoverable():
                try:
                    await service.recover(record)
                except Exception:
                    logger.warning(
                        "Background task admission recovery unavailable: task=%s", record["_id"]
                    )
    except TimeoutError:
        logger.warning("Background admission scanner reached its 30 second budget")


# Registration is process-local, so reinstall it whenever API/worker imports this owner.
register_executor(BACKGROUND_EXECUTOR_KEY, execute_background_stream)
