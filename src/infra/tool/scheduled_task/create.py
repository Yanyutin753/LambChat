"""scheduled_task_create tool implementation."""

import sys
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any
from zoneinfo import ZoneInfo

from langchain_core.tools import InjectedToolArg

from src.infra.scheduler.service import ScheduledTaskService
from src.infra.tool.backend_utils import get_user_id_from_runtime
from src.infra.utils.datetime import ensure_utc, to_iso, utc_now
from src.kernel.extensions import WORKFLOW_PLUGIN_ID
from src.kernel.extensions.plugin_options import (
    AGENT_TEAM_PLUGIN_ID,
    AGENT_TEAM_SELECTED_TEAM_OPTION,
    agent_uses_agent_team_options,
    first_plugin_agent_id,
    with_plugin_option,
    with_plugin_options,
)
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


def _normalized_plugin_options(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for plugin_id, options in value.items():
        if not isinstance(plugin_id, str) or not plugin_id.strip():
            continue
        if not isinstance(options, dict):
            continue
        plugin_values = {
            key: option_value
            for key, option_value in options.items()
            if isinstance(key, str) and key.strip()
        }
        if plugin_values:
            normalized[plugin_id.strip()] = plugin_values
    return normalized


_plugin_runtime: Any | None = None


def set_plugin_runtime(runtime: Any | None) -> None:
    """Attach Plugin Runtime used to resolve manifest-owned scheduled task agents."""
    global _plugin_runtime
    _plugin_runtime = runtime


def _runtime() -> Any | None:
    return _plugin_runtime


def _agent_team_agent_id() -> str:
    return first_plugin_agent_id(AGENT_TEAM_PLUGIN_ID, runtime=_runtime()) or "team"


def _uses_agent_team_options(agent_id: str | None) -> bool:
    return agent_uses_agent_team_options(agent_id, runtime=_runtime())


def _plugin_unavailable(plugin_id: str) -> bool:
    runtime = _runtime()
    if runtime is None:
        return False
    is_enabled = getattr(runtime, "is_enabled", None)
    return callable(is_enabled) and not is_enabled(plugin_id)


def _agent_team_plugin_unavailable() -> bool:
    return _plugin_unavailable(AGENT_TEAM_PLUGIN_ID)


def _workflow_plugin_unavailable() -> bool:
    return _plugin_unavailable(WORKFLOW_PLUGIN_ID)


def _has_workflow_options(plugin_options: dict[str, dict[str, Any]]) -> bool:
    return bool(plugin_options.get(WORKFLOW_PLUGIN_ID))


@tool
async def scheduled_task_create(
    name: Annotated[str, "Task name, e.g. 'Daily Report', 'Cache Cleanup'"],
    message: Annotated[
        str,
        "The message sent to the agent when this task fires. "
        "Write clear, specific instructions for what the agent should do. "
        "Example: 'Generate a summary of today's conversations and save it to memory.'",
    ],
    trigger_type: Annotated[
        str,
        "Trigger type: 'date' (run once), 'interval' (fixed interval), or 'cron' (cron expression). "
        "Use 'date' for one-time requests like 'in 5 minutes', 'tomorrow at 9', or reminders.",
    ],
    delay_seconds: Annotated[
        int | None,
        "Delay in seconds before a one-time run. Use when trigger_type='date' for relative requests "
        "like '5 minutes later'. Minimum: 1.",
    ] = None,
    run_at_iso: Annotated[
        str | None,
        "Absolute ISO-8601 datetime for a one-time run. Use when trigger_type='date'. "
        "If timezone/offset is omitted, schedule_timezone is assumed.",
    ] = None,
    schedule_timezone: Annotated[
        str | None,
        "IANA timezone for interpreting user-facing schedule times, e.g. 'Asia/Shanghai' "
        "or 'America/Los_Angeles'. Usually omit this and inherit the current user's timezone. "
        "For cron schedules, cron_hour/cron_minute are in this timezone, not UTC.",
    ] = None,
    interval_seconds: Annotated[
        int | None,
        "Interval in seconds. Required when trigger_type='interval'. "
        "Examples: 300 (5min), 3600 (1h), 86400 (1d). Minimum: 60.",
    ] = None,
    cron_hour: Annotated[
        str | None,
        "Cron hour pattern (0-23). Only used when trigger_type='cron'. "
        "Examples: '9' (9 AM), '0,12' (midnight and noon), '*/3' (every 3 hours). "
        "Time is in schedule_timezone/the user's local timezone, not UTC.",
    ] = None,
    cron_minute: Annotated[
        str | None,
        "Cron minute pattern (0-59). Only used when trigger_type='cron'. "
        "Examples: '0' (on the hour), '30' (half past). Default: '0'.",
    ] = None,
    cron_day_of_week: Annotated[
        str | None,
        "Cron day-of-week pattern. Only used when trigger_type='cron'. "
        "Examples: 'mon-fri' (weekdays), '1-5' (same), 'mon,wed,fri'. Default: every day.",
    ] = None,
    cron_day: Annotated[
        str | None,
        "Cron day-of-month pattern (1-31). Only used when trigger_type='cron'. "
        "Examples: '1' (1st of month), '1,15' (1st and 15th). Default: every day.",
    ] = None,
    cron_month: Annotated[
        str | None,
        "Cron month pattern (1-12). Only used when trigger_type='cron'. Default: every month.",
    ] = None,
    agent_id: Annotated[
        str | None,
        "Agent ID to execute. If omitted, use the current conversation's agent.",
    ] = None,
    persona_preset_id: Annotated[
        str | None,
        "Persona preset ID for non-team agents. Ignored when the effective agent is 'team'.",
    ] = None,
    team_id: Annotated[
        str | None,
        "Team ID for the team agent. Ignored unless the effective agent is 'team'.",
    ] = None,
    role_query: Annotated[
        str | None,
        "Natural-language role/persona search text in the user's language. Use this when "
        "the user names a role but you do not know persona_preset_id. For Chinese users, "
        "search with Chinese role words such as '写作', '研究员', or '数据分析'. Ignored when "
        "persona_preset_id is provided or when the effective agent is 'team'.",
    ] = None,
    team_query: Annotated[
        str | None,
        "Natural-language team search text in the user's language. Use this when the user "
        "names a team but you do not know team_id. Providing this selects the team agent "
        "unless agent_id='team' was already explicit.",
    ] = None,
    plugin_options: Annotated[
        dict[str, dict[str, Any]] | None,
        "Plugin-scoped scheduled task options keyed by plugin id and local option key. "
        "Use only manifest-declared scheduled task options; legacy fields such as team_id "
        "remain supported for compatibility.",
    ] = None,
    model_id: Annotated[
        str | None,
        "LLM model ID to use. If omitted, use the current conversation's model.",
    ] = None,
    model: Annotated[
        str | None,
        "LLM model value/name to use. Usually omit this unless model_id is unavailable.",
    ] = None,
    description: Annotated[
        str | None,
        "Optional description of what this task does",
    ] = None,
    timeout_seconds: Annotated[
        int,
        "Maximum execution time in seconds. Range: 10-7200. Default: 3600s (60 min). "
        "Do not set this too short; omit it unless the user explicitly asks for a shorter timeout.",
    ] = 3600,
    run_on_start: Annotated[
        bool,
        "Whether to run the task immediately after creation",
    ] = False,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Create a scheduled task that automatically runs an agent at specified times.
    The agent will receive the 'message' as a user prompt on each execution.
    Use trigger_type='date' for one-time tasks (e.g. remind me in 5 minutes).
    Use trigger_type='interval' for periodic tasks (e.g. every 5 minutes),
    or trigger_type='cron' for calendar-based schedules (e.g. every weekday at 9 AM
    in the user's timezone).
    Each run creates a new session under the user's account.
    Before calling this tool, explain in the current conversation what the scheduled
    task will do. This tool does not run the task once for preview; it only asks
    for explicit human confirmation before creating the schedule."""
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
    normalized_plugin_options = _normalized_plugin_options(plugin_options)
    if _has_workflow_options(normalized_plugin_options) and _workflow_plugin_unavailable():
        return _json(
            {
                "error": "Workflow plugin is disabled; scheduled workflow tasks cannot be created.",
                "code": "plugin_unavailable",
                "plugin_id": WORKFLOW_PLUGIN_ID,
            }
        )

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
    agent_team_agent_id = _agent_team_agent_id()
    requested_agent_uses_team = _uses_agent_team_options(agent_id)
    session_agent_uses_team = _uses_agent_team_options(session_agent_id)
    if team_query:
        effective_agent_id = agent_team_agent_id
    elif role_query:
        effective_agent_id = (
            agent_id
            if agent_id and not requested_agent_uses_team
            else session_agent_id
            if session_agent_id and not session_agent_uses_team
            else "fast"
        )
    elif requested_agent_uses_team or (team_id and (not agent_id or session_agent_uses_team)):
        effective_agent_id = agent_team_agent_id
    elif persona_preset_id:
        effective_agent_id = (
            agent_id
            if agent_id and not requested_agent_uses_team
            else session_agent_id
            if session_agent_id and not session_agent_uses_team
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
    if _uses_agent_team_options(effective_agent_id):
        if _agent_team_plugin_unavailable():
            return _json(
                {
                    "error": "Agent Team plugin is disabled; scheduled team tasks cannot be created.",
                    "code": "plugin_unavailable",
                    "plugin_id": AGENT_TEAM_PLUGIN_ID,
                }
            )
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
            **(
                {"persona_preset_id": effective_persona_preset_id}
                if effective_persona_preset_id
                else {}
            ),
        }
        input_payload = with_plugin_options(
            input_payload,
            normalized_plugin_options,
        )
        if effective_team_id:
            input_payload = with_plugin_option(
                input_payload,
                plugin_id=AGENT_TEAM_PLUGIN_ID,
                key=AGENT_TEAM_SELECTED_TEAM_OPTION,
                value=effective_team_id,
            )
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
