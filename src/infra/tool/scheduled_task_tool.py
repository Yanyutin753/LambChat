"""Backward-compatible facade for scheduled task tools.

The scheduled task tools now live in the ``scheduled_task`` package. This module
keeps the legacy import path working for tests and extensions that still patch
helpers on ``src.infra.tool.scheduled_task_tool``.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from src.infra.tool.scheduled_task import approval as _approval
from src.infra.tool.scheduled_task import create as _create
from src.infra.tool.scheduled_task import delete as _delete
from src.infra.tool.scheduled_task import (
    get_scheduled_task_tools,
    scheduled_task_create,
    scheduled_task_delete,
    scheduled_task_get,
    scheduled_task_list,
    scheduled_task_pause,
    scheduled_task_resume,
    scheduled_task_run,
    scheduled_task_update,
)
from src.infra.tool.scheduled_task import helpers as _helpers
from src.infra.tool.scheduled_task import read as _read
from src.infra.tool.scheduled_task import update as _update
from src.infra.utils.datetime import utc_now

ScheduledTaskService = _create.ScheduledTaskService
PersonaPresetManager = _approval.PersonaPresetManager
TeamManager = _approval.TeamManager
_build_task_preview = _helpers._build_task_preview
_confirm_scheduled_task_creation = _approval._confirm_scheduled_task_creation
_get_current_session_defaults = _helpers._get_current_session_defaults
_json = _helpers._json
_permission_error = _helpers._permission_error
_resolve_persona_preset_id_from_query = _approval._resolve_persona_preset_id_from_query
_resolve_team_id_from_query = _approval._resolve_team_id_from_query
_resolve_user = _helpers._resolve_user
_normalized_plugin_options = _create._normalized_plugin_options
set_plugin_runtime = _create.set_plugin_runtime
_send_scheduled_task_approval_event = _approval._send_scheduled_task_approval_event
create_approval = _approval.create_approval
wait_for_response = _approval.wait_for_response

_PATCH_TARGETS: dict[str, list[tuple[ModuleType, str]]] = {
    "ScheduledTaskService": [
        (_create, "ScheduledTaskService"),
        (_read, "ScheduledTaskService"),
        (_update, "ScheduledTaskService"),
        (_delete, "ScheduledTaskService"),
    ],
    "PersonaPresetManager": [(_approval, "PersonaPresetManager")],
    "TeamManager": [(_approval, "TeamManager")],
    "utc_now": [(_create, "utc_now")],
    "_build_task_preview": [
        (_helpers, "_build_task_preview"),
        (_create, "_build_task_preview"),
    ],
    "_confirm_scheduled_task_creation": [
        (_approval, "_confirm_scheduled_task_creation"),
        (_create, "_confirm_scheduled_task_creation"),
    ],
    "_get_current_session_defaults": [
        (_helpers, "_get_current_session_defaults"),
        (_create, "_get_current_session_defaults"),
    ],
    "_json": [
        (_helpers, "_json"),
        (_create, "_json"),
        (_read, "_json"),
        (_update, "_json"),
        (_delete, "_json"),
    ],
    "_permission_error": [
        (_helpers, "_permission_error"),
        (_create, "_permission_error"),
        (_read, "_permission_error"),
        (_update, "_permission_error"),
        (_delete, "_permission_error"),
    ],
    "_resolve_persona_preset_id_from_query": [
        (_approval, "_resolve_persona_preset_id_from_query"),
        (_create, "_resolve_persona_preset_id_from_query"),
    ],
    "_resolve_team_id_from_query": [
        (_approval, "_resolve_team_id_from_query"),
        (_create, "_resolve_team_id_from_query"),
    ],
    "_resolve_user": [
        (_helpers, "_resolve_user"),
        (_create, "_resolve_user"),
    ],
    "_normalized_plugin_options": [(_create, "_normalized_plugin_options")],
    "set_plugin_runtime": [(_create, "set_plugin_runtime")],
    "_send_scheduled_task_approval_event": [
        (_approval, "_send_scheduled_task_approval_event"),
    ],
    "create_approval": [(_approval, "create_approval")],
    "wait_for_response": [(_approval, "wait_for_response")],
}


class _ScheduledTaskToolModule(ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        for module, attr in _PATCH_TARGETS.get(name, []):
            setattr(module, attr, value)


sys.modules[__name__].__class__ = _ScheduledTaskToolModule

__all__ = [
    "scheduled_task_create",
    "scheduled_task_list",
    "scheduled_task_get",
    "scheduled_task_update",
    "scheduled_task_pause",
    "scheduled_task_resume",
    "scheduled_task_delete",
    "scheduled_task_run",
    "get_scheduled_task_tools",
    "ScheduledTaskService",
    "PersonaPresetManager",
    "TeamManager",
    "utc_now",
    "_build_task_preview",
    "_confirm_scheduled_task_creation",
    "_get_current_session_defaults",
    "_json",
    "_permission_error",
    "_resolve_persona_preset_id_from_query",
    "_resolve_team_id_from_query",
    "_resolve_user",
    "_normalized_plugin_options",
    "set_plugin_runtime",
    "_send_scheduled_task_approval_event",
    "create_approval",
    "wait_for_response",
]
