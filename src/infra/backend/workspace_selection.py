"""Resolve an opaque, machine-bound directory selection from session options."""

import json
import re


def selected_workspace_id(options: dict | None) -> str | None:
    options = options or {}
    raw = options.get("sandbox_workspace")
    if not isinstance(raw, str):
        return None
    try:
        selection = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(selection, dict):
        return None
    key = selection.get("id")
    machine = options.get("sandbox_machine_id")
    if (
        not machine
        or selection.get("machineId") != machine
        or not isinstance(key, str)
        or not re.fullmatch(r"local-[0-9a-f]{32}", key)
    ):
        return None
    return key
