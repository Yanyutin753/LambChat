"""Shared helpers for scheduled-task tools."""

import json
from typing import Any

from src.infra.logging import get_logger
from src.infra.role.storage import RoleStorage
from src.infra.user.storage import UserStorage
from src.kernel.schemas.scheduled_task import ChannelDeliveryConfig
from src.kernel.schemas.user import TokenPayload
from src.kernel.extensions.plugin_options import selected_agent_team_id_from_metadata

logger = get_logger(__name__)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _strip_resolved_agent_options(options: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in options.items()
        if key
        not in {
            "_resolved_model_config",
            "_resolved_supports_vision",
            "_resolved_fallback_model",
            "_resolved_model_profile",
        }
    }


async def _resolve_user(user_id: str) -> TokenPayload | None:
    """Resolve the latest roles and permissions for a user ID."""
    user = await UserStorage().get_by_id(user_id)
    if not user:
        return None

    role_storage = RoleStorage()
    roles = await role_storage.get_by_names(user.roles or [])

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


async def _get_current_session_defaults() -> tuple[
    str | None,
    dict[str, Any],
    str | None,
    ChannelDeliveryConfig | None,
    str | None,
    str | None,
]:
    """Return agent/model defaults from the conversation that invoked the tool."""
    from src.infra.logging.context import TraceContext
    from src.infra.session.manager import SessionManager

    ctx = TraceContext.get_request_context()
    if not ctx.session_id:
        return None, {}, None, None, None, None

    try:
        session = await SessionManager().get_session(ctx.session_id)
    except Exception as e:
        logger.warning("[ScheduledTask] Failed to load source session defaults: %s", e)
        return None, {}, None, None, None, None

    metadata = session.metadata if session else {}
    if not isinstance(metadata, dict):
        return None, {}, None, None, None, None

    agent_id = metadata.get("agent_id")
    raw_options = metadata.get("agent_options")
    agent_options = (
        _strip_resolved_agent_options(dict(raw_options)) if isinstance(raw_options, dict) else {}
    )
    user_timezone = metadata.get("user_timezone")
    channel_delivery = _coerce_channel_delivery(metadata.get("channel_delivery"))
    persona_preset_id = metadata.get("persona_preset_id")
    team_id = selected_agent_team_id_from_metadata(metadata)
    return (
        agent_id if isinstance(agent_id, str) and agent_id else None,
        agent_options,
        user_timezone if isinstance(user_timezone, str) and user_timezone else None,
        channel_delivery,
        persona_preset_id if isinstance(persona_preset_id, str) and persona_preset_id else None,
        team_id if isinstance(team_id, str) and team_id else None,
    )


def _coerce_channel_delivery(value: Any) -> ChannelDeliveryConfig | None:
    """Parse optional channel delivery metadata from the current session."""
    if not isinstance(value, dict):
        return None
    try:
        delivery = ChannelDeliveryConfig.model_validate(value)
    except Exception as e:
        logger.warning("[ScheduledTask] Ignoring invalid channel delivery metadata: %s", e)
        return None
    return delivery if delivery.enabled else None


async def _permission_error(
    user_id: str,
    permission: str,
) -> dict[str, Any] | None:
    user = await _resolve_user(user_id)
    if user and permission in set(user.permissions or []):
        return None
    return {
        "error": f"Missing permission: {permission}",
        "code": "permission_denied",
    }


def _format_trigger_preview(
    trigger_type,
    trigger_config: dict[str, Any],
    timezone_name: str = "UTC",
) -> str:
    from src.infra.utils.datetime import parse_iso, to_iso
    from src.kernel.schemas.scheduled_task import TriggerType

    if trigger_type == TriggerType.INTERVAL:
        seconds = int(trigger_config["seconds"])
        if seconds % 86400 == 0:
            return f"every {seconds // 86400} day(s)"
        if seconds % 3600 == 0:
            return f"every {seconds // 3600} hour(s)"
        if seconds % 60 == 0:
            return f"every {seconds // 60} minute(s)"
        return f"every {seconds} second(s)"

    if trigger_type == TriggerType.DATE:
        run_date = parse_iso(str(trigger_config["run_date"]))
        return f"once at {to_iso(run_date)} UTC"

    minute = trigger_config.get("minute", "0")
    hour = trigger_config.get("hour", "0")
    day = trigger_config.get("day", "*")
    month = trigger_config.get("month", "*")
    day_of_week = trigger_config.get("day_of_week", "*")
    return (
        "cron schedule "
        f"(minute={minute}, hour={hour}, day={day}, month={month}, "
        f"day_of_week={day_of_week}, timezone={timezone_name})"
    )


def _build_task_preview(
    *,
    name: str,
    message: str,
    trigger_type,
    trigger_config: dict[str, Any],
    timezone_name: str = "UTC",
    agent_id: str,
    description: str | None,
    timeout_seconds: int,
    run_on_start: bool,
) -> dict[str, Any]:
    schedule = _format_trigger_preview(trigger_type, trigger_config, timezone_name)
    return {
        "name": name,
        "description": description,
        "agent_id": agent_id,
        "trigger_type": trigger_type.value,
        "trigger_config": trigger_config,
        "timezone": timezone_name,
        "schedule": schedule,
        "message": message,
        "timeout_seconds": timeout_seconds,
        "run_on_start": run_on_start,
        "effect": (
            f"After creation, agent '{agent_id}' will run on {schedule}. "
            f"Each run will start a new session and send this prompt to the agent: {message!r}."
            + (" The task will also run immediately after creation." if run_on_start else "")
        ),
    }
