"""scheduled_task_create tool implementation."""

import sys
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any, Literal
from zoneinfo import ZoneInfo

from langchain_core.tools import InjectedToolArg

from src.infra.scheduler.service import ScheduledTaskService
from src.infra.tool.backend_utils import get_attachments_from_runtime, get_user_id_from_runtime
from src.infra.utils.datetime import ensure_utc, to_iso, utc_now
from src.kernel.schemas.scheduled_task import ScheduledTaskCreate, TriggerType
from src.kernel.types import Permission

if TYPE_CHECKING:
    from langchain.tools import ToolRuntime
else:
    try:
        from langchain.tools import ToolRuntime  # type: ignore[assignment]
    except ImportError:  # pragma: no cover
        _mod = type(sys)("langchain.tools")  # type: ignore[assignment]
        _mod.ToolRuntime = Any  # type: ignore[assignment]
        sys.modules.setdefault("langchain.tools", _mod)
        from langchain.tools import ToolRuntime  # type: ignore[assignment]

from langchain.tools import tool  # noqa: E402

from src.infra.tool.scheduled_task.approval import (
    _confirm_scheduled_task_creation,
    _resolve_persona_preset_id_from_query,
    _resolve_team_id_from_query,
)
from src.infra.tool.scheduled_task.helpers import (
    _build_task_preview,
    _get_current_session_defaults,
    _json,
    _permission_error,
    _resolve_user,
)


def _parse_run_at_iso(value: str, timezone_name: str) -> datetime:
    run_date = datetime.fromisoformat(value)
    if run_date.tzinfo is None:
        run_date = run_date.replace(tzinfo=ZoneInfo(timezone_name))
    return ensure_utc(run_date)


@tool
async def scheduled_task_create(
    name: Annotated[str, "Task name."],
    message: Annotated[
        str,
        "Instructions sent to the agent on each run.",
    ],
    trigger_type: Annotated[
        Literal["date", "interval", "cron"],
        "date=once, interval=fixed seconds, cron=calendar schedule.",
    ],
    delay_seconds: Annotated[
        int | None,
        "Relative one-time delay for date trigger (min 1).",
    ] = None,
    run_at_iso: Annotated[
        str | None,
        "ISO-8601 time for date trigger; naive values use schedule_timezone.",
    ] = None,
    schedule_timezone: Annotated[
        str | None,
        "IANA timezone; defaults to user timezone. Cron fields use it, not UTC.",
    ] = None,
    interval_seconds: Annotated[
        int | None,
        "Seconds for interval trigger (min 60).",
    ] = None,
    cron_hour: Annotated[
        str | None,
        "Cron hour (0-23), e.g. 9, 0,12, or */3; uses schedule_timezone.",
    ] = None,
    cron_minute: Annotated[
        str | None,
        "Cron minute (0-59); default 0.",
    ] = None,
    cron_day_of_week: Annotated[
        str | None,
        "Cron weekday, e.g. mon-fri or mon,wed,fri.",
    ] = None,
    cron_day: Annotated[
        str | None,
        "Cron day of month (1-31).",
    ] = None,
    cron_month: Annotated[
        str | None,
        "Cron month (1-12).",
    ] = None,
    agent_id: Annotated[
        str | None,
        "Agent ID; defaults to current conversation.",
    ] = None,
    persona_preset_id: Annotated[
        str | None,
        "Persona ID for non-team agent.",
    ] = None,
    team_id: Annotated[
        str | None,
        "Team ID for team agent.",
    ] = None,
    role_query: Annotated[
        str | None,
        "Role query when persona_preset_id is unknown; ignored for team agent.",
    ] = None,
    team_query: Annotated[
        str | None,
        "Team query when team_id is unknown; selects team agent.",
    ] = None,
    model_id: Annotated[
        str | None,
        "Model config ID; defaults to current conversation.",
    ] = None,
    model: Annotated[
        str | None,
        "Model name fallback when model_id is unavailable.",
    ] = None,
    description: Annotated[
        str | None,
        "Optional task description.",
    ] = None,
    timeout_seconds: Annotated[
        int,
        "Execution timeout seconds (10-7200). Default: 3600s. Do not set this too short.",
    ] = 3600,
    run_on_start: Annotated[
        bool,
        "Run once immediately after creation.",
    ] = False,
    attachments: Annotated[
        list[dict[str, Any]] | None,
        "Attachment objects reused on each run; defaults to current message attachments.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Create a confirmed agent schedule: date for one run, interval for fixed periods,
    or cron for calendar times in the user's timezone. Explain it before calling; each
    run creates a new session and creation does not run a preview."""
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return _json({"error": "No user context available"})
    error = await _permission_error(user_id, Permission.SCHEDULED_TASK_WRITE.value)
    if error:
        return _json(error)

    (
        session_agent_id,
        session_agent_options,
        session_user_timezone,
        session_channel_delivery,
        session_persona_preset_id,
        session_team_id,
    ) = await _get_current_session_defaults()
    effective_timezone = schedule_timezone or session_user_timezone or "UTC"

    # Build trigger_config from structured params
    try:
        trigger_enum = TriggerType(trigger_type)
    except ValueError:
        return _json(
            {"error": f"Invalid trigger_type '{trigger_type}'. Use 'date', 'interval', or 'cron'."}
        )

    trigger_config: dict[str, Any]
    if trigger_enum == TriggerType.DATE:
        if delay_seconds is None and run_at_iso is None:
            return _json(
                {
                    "error": (
                        "delay_seconds or run_at_iso is required when trigger_type='date'. "
                        "For one-time relative requests such as '5 minutes later', use delay_seconds."
                    )
                }
            )
        try:
            if delay_seconds is not None:
                if delay_seconds < 1:
                    return _json({"error": "delay_seconds must be at least 1"})
                run_date = utc_now() + timedelta(seconds=delay_seconds)
            else:
                run_date = _parse_run_at_iso(str(run_at_iso), effective_timezone)
        except Exception as e:
            return _json({"error": f"Invalid one-time schedule: {e}"})

        if run_date <= utc_now():
            return _json({"error": "run_at_iso must be in the future"})
        trigger_config = {"run_date": to_iso(run_date)}
    elif trigger_enum == TriggerType.INTERVAL:
        if not interval_seconds:
            return _json({"error": "interval_seconds is required when trigger_type='interval'"})
        if interval_seconds < 60:
            return _json({"error": "interval_seconds must be at least 60"})
        trigger_config = {"seconds": interval_seconds}
    else:
        # Cron trigger — at least one cron field should be provided
        trigger_config = {}
        if cron_hour is not None:
            trigger_config["hour"] = cron_hour
        if cron_minute is not None:
            trigger_config["minute"] = cron_minute
        if cron_day_of_week is not None:
            trigger_config["day_of_week"] = cron_day_of_week
        if cron_day is not None:
            trigger_config["day"] = cron_day
        if cron_month is not None:
            trigger_config["month"] = cron_month
        # Provide sensible defaults if nothing specified
        if "hour" not in trigger_config:
            trigger_config["hour"] = "0"
        if "minute" not in trigger_config:
            trigger_config["minute"] = "0"

    user = await _resolve_user(user_id)
    effective_attachments = _normalize_attachments(
        attachments if attachments is not None else get_attachments_from_runtime(runtime)
    )
    if team_query:
        effective_agent_id = "team"
    elif role_query:
        effective_agent_id = (
            agent_id
            if agent_id and agent_id != "team"
            else session_agent_id
            if session_agent_id and session_agent_id != "team"
            else "fast"
        )
    elif agent_id == "team" or (team_id and (not agent_id or session_agent_id == "team")):
        effective_agent_id = "team"
    elif persona_preset_id:
        effective_agent_id = (
            agent_id
            if agent_id and agent_id != "team"
            else session_agent_id
            if session_agent_id and session_agent_id != "team"
            else "fast"
        )
    else:
        effective_agent_id = agent_id or session_agent_id or "fast"
    effective_agent_options = dict(session_agent_options)
    if model_id:
        effective_agent_options["model_id"] = model_id
    if model:
        effective_agent_options["model"] = model
    effective_persona_preset_id = None
    effective_team_id = None
    resolved_role_match = None
    resolved_team_match = None
    if effective_agent_id == "team":
        effective_team_id = team_id
        if not effective_team_id:
            (
                effective_team_id,
                resolved_team_match,
                resolve_error,
            ) = await _resolve_team_id_from_query(user_id=user_id, query=team_query)
            if resolve_error:
                return _json({"error": resolve_error, "code": "team_not_found"})
        if not effective_team_id:
            effective_team_id = session_team_id
    else:
        effective_persona_preset_id = persona_preset_id
        if not effective_persona_preset_id:
            (
                effective_persona_preset_id,
                resolved_role_match,
                resolve_error,
            ) = await _resolve_persona_preset_id_from_query(
                user_id=user_id,
                user=user,
                query=role_query,
            )
            if resolve_error:
                return _json({"error": resolve_error, "code": "persona_preset_not_found"})
        if not effective_persona_preset_id:
            effective_persona_preset_id = session_persona_preset_id

    effective_run_on_start = False if trigger_enum == TriggerType.DATE else run_on_start
    preview = _build_task_preview(
        name=name,
        message=message,
        trigger_type=trigger_enum,
        trigger_config=trigger_config,
        timezone_name=effective_timezone,
        agent_id=effective_agent_id,
        description=description,
        timeout_seconds=timeout_seconds,
        run_on_start=effective_run_on_start,
    )
    if resolved_role_match:
        preview["resolved_persona_preset"] = resolved_role_match
    if resolved_team_match:
        preview["resolved_team"] = resolved_team_match
    confirmation = await _confirm_scheduled_task_creation(preview=preview, user_id=user_id)
    if not confirmation["approved"]:
        return _json(
            {
                "success": False,
                "action": "not_created",
                "reason": confirmation["status"],
                "approval_id": confirmation["approval_id"],
                "approved": confirmation["approved"],
                "status": confirmation["status"],
                "approval_status": confirmation["status"],
                "preview": preview,
                "message": confirmation["message"],
            }
        )

    service = ScheduledTaskService()
    from src.infra.logging.context import TraceContext

    ctx = TraceContext.get_request_context()
    try:
        input_payload = {
            "message": message,
            **({"agent_options": effective_agent_options} if effective_agent_options else {}),
            **({"user_timezone": session_user_timezone} if session_user_timezone else {}),
            **({"attachments": effective_attachments} if effective_attachments else {}),
            **(
                {"persona_preset_id": effective_persona_preset_id}
                if effective_persona_preset_id
                else {}
            ),
            **({"team_id": effective_team_id} if effective_team_id else {}),
        }
        task = await service.create_task(
            request=ScheduledTaskCreate(
                name=name,
                agent_id=effective_agent_id,
                trigger_type=trigger_enum,
                trigger_config=trigger_config,
                timezone=effective_timezone,
                input_payload=input_payload,
                description=description,
                enabled=True,
                timeout_seconds=timeout_seconds,
                run_on_start=effective_run_on_start,
                max_retries=0,
                source_session_id=ctx.session_id or None,
                source_run_id=ctx.run_id or None,
                created_by="agent",
                delivery=session_channel_delivery,
            ),
            owner_id=user_id,
        )
    except Exception as e:
        return _json({"error": f"Failed to create task: {e}"})

    resp = ScheduledTaskService.to_response(task)
    return _json(
        {
            "success": True,
            "action": "created",
            "task": resp.model_dump(mode="json"),
            "preview": preview,
            "approval_id": confirmation["approval_id"],
            "approved": confirmation["approved"],
            "status": confirmation["status"],
            "approval_status": confirmation["status"],
            "message": (
                f"Scheduled task '{task.name}' created (trigger: {trigger_type}, id: {task.id})."
            ),
        }
    )


def _normalize_attachments(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    attachments = [dict(item) for item in value if isinstance(item, dict)]
    return attachments or None
