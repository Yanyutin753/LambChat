"""Resolve an opaque, machine-bound directory selection from session options."""

import json
import re

from src.kernel.errors import AppError, ErrorCode

WORKSPACE_OPTION_KEYS = ("sandbox", "sandbox_machine_id", "sandbox_workspace")


async def resolve_workspace_options(
    options: dict | None,
    user_id: str,
    *,
    project_id: str | None = None,
    existing_metadata: dict | None = None,
) -> dict:
    """Snapshot project defaults once; explicit workspace choices form one binding."""
    values = dict(options or {})
    if existing_metadata is not None:
        stored = existing_metadata.get("agent_options")
        stored = stored if isinstance(stored, dict) else {}
        defaults = {key: stored[key] for key in WORKSPACE_OPTION_KEYS if key in stored}
    elif project_id:
        from src.infra.folder.storage import get_project_storage

        project = await get_project_storage().get_by_id(project_id, user_id)
        if project is None:
            raise AppError(ErrorCode.PROJECT_NOT_FOUND)
        workspace = project.workspace
        defaults = (
            {
                "sandbox": "local",
                "sandbox_machine_id": workspace.machine_id,
                "sandbox_workspace": json.dumps(workspace.model_dump(by_alias=True)),
            }
            if workspace
            else {}
        )
    else:
        defaults = {}
    if not any(key in values for key in WORKSPACE_OPTION_KEYS):
        values = {**defaults, **values}
    validate_workspace_options(values)
    if (
        existing_metadata is not None
        and existing_metadata.get("persistent_goal_status") in {"active", "waiting_human"}
        and _workspace_binding(values) != _workspace_binding(defaults)
    ):
        raise AppError(ErrorCode.CONFLICT)
    return values


def _workspace_binding(options: dict) -> tuple:
    validate_workspace_options(options)
    if options.get("sandbox") == "cloud":
        return ("cloud",)
    return (
        options.get("sandbox"),
        options.get("sandbox_machine_id") or "",
        json.loads(options.get("sandbox_workspace") or "null"),
    )


def validate_workspace_options(options: dict) -> None:
    mode = options.get("sandbox")
    machine = options.get("sandbox_machine_id")
    if mode is not None and mode not in ("local", "cloud"):
        raise AppError(ErrorCode.SANDBOX_WORKSPACE_INVALID)
    if machine is not None and (not isinstance(machine, str) or len(machine) > 256):
        raise AppError(ErrorCode.SANDBOX_WORKSPACE_INVALID)
    if mode != "cloud":
        selected_workspace_id(options)


def selected_workspace_id(options: dict | None) -> str | None:
    options = options or {}
    raw = options.get("sandbox_workspace")
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str) or len(raw) > 16384:
        raise AppError(ErrorCode.SANDBOX_WORKSPACE_INVALID)
    try:
        selection = json.loads(raw)
    except ValueError:
        raise AppError(ErrorCode.SANDBOX_WORKSPACE_INVALID) from None
    if not isinstance(selection, dict):
        raise AppError(ErrorCode.SANDBOX_WORKSPACE_INVALID)
    key = selection.get("id")
    machine = options.get("sandbox_machine_id")
    if (
        not isinstance(machine, str)
        or not machine
        or len(machine) > 256
        or selection.get("machineId") != machine
        or not isinstance(key, str)
        or not re.fullmatch(r"local-[0-9a-f]{32}", key)
    ):
        raise AppError(ErrorCode.SANDBOX_WORKSPACE_INVALID)
    return key
