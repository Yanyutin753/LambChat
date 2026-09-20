"""Compatibility exports for scheduled task tools.

The implementations live in ``src.infra.tool.scheduled_task``. This module keeps
the historical import path and test monkeypatch points working.
"""

import sys
import types
from typing import Any

from src.api.routes.human import create_approval, wait_for_response
from src.infra.persona_preset.manager import PersonaPresetManager
from src.infra.scheduler.service import ScheduledTaskService
from src.infra.team.manager import TeamManager
from src.infra.tool.scheduled_task import approval as _approval_mod
from src.infra.tool.scheduled_task import create as _create_mod
from src.infra.tool.scheduled_task import delete as _delete_mod
from src.infra.tool.scheduled_task import get_scheduled_task_tools
from src.infra.tool.scheduled_task import helpers as _helpers_mod
from src.infra.tool.scheduled_task import read as _read_mod
from src.infra.tool.scheduled_task import update as _update_mod
from src.infra.tool.scheduled_task.approval import (
    _confirm_scheduled_task_creation,
    _format_approval_message,
    _resolve_persona_preset_id_from_query,
    _resolve_team_id_from_query,
    _send_scheduled_task_approval_event,
)
from src.infra.tool.scheduled_task.create import _parse_run_at_iso, scheduled_task_create
from src.infra.tool.scheduled_task.delete import scheduled_task_delete
from src.infra.tool.scheduled_task.helpers import (
    _build_task_preview,
    _coerce_channel_delivery,
    _format_trigger_preview,
    _get_current_session_defaults,
    _json,
    _permission_error,
    _resolve_user,
    _strip_resolved_agent_options,
)
from src.infra.tool.scheduled_task.read import scheduled_task_list
from src.infra.tool.scheduled_task.update import scheduled_task_update
from src.infra.utils.datetime import utc_now

__all__ = [
    "ScheduledTaskService",
    "PersonaPresetManager",
    "TeamManager",
    "create_approval",
    "wait_for_response",
    "utc_now",
    "_json",
    "_strip_resolved_agent_options",
    "_resolve_user",
    "_get_current_session_defaults",
    "_coerce_channel_delivery",
    "_permission_error",
    "_format_trigger_preview",
    "_build_task_preview",
    "_format_approval_message",
    "_resolve_persona_preset_id_from_query",
    "_resolve_team_id_from_query",
    "_send_scheduled_task_approval_event",
    "_confirm_scheduled_task_creation",
    "_parse_run_at_iso",
    "scheduled_task_create",
    "scheduled_task_list",
    "scheduled_task_update",
    "scheduled_task_delete",
    "get_scheduled_task_tools",
]

_PATCH_TARGETS = {
    "ScheduledTaskService": (_create_mod, _read_mod, _update_mod, _delete_mod),
    "utc_now": (_create_mod,),
    "_get_current_session_defaults": (_create_mod, _helpers_mod),
    "_permission_error": (_create_mod, _read_mod, _update_mod, _delete_mod, _helpers_mod),
    "_resolve_user": (_helpers_mod,),
    "PersonaPresetManager": (_approval_mod,),
    "TeamManager": (_approval_mod,),
    "create_approval": (_approval_mod,),
    "wait_for_response": (_approval_mod,),
    "_send_scheduled_task_approval_event": (_approval_mod,),
    "_confirm_scheduled_task_creation": (_create_mod, _approval_mod),
}


class _ScheduledTaskToolCompatModule(types.ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        for module in _PATCH_TARGETS.get(name, ()):
            setattr(module, name, value)


sys.modules[__name__].__class__ = _ScheduledTaskToolCompatModule
