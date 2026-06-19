"""Helpers for plugin-scoped metadata options."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

AGENT_TEAM_PLUGIN_ID = "agent_team"
AGENT_TEAM_DEFAULT_TEAM_OPTION = "DEFAULT_TEAM_ID"
AGENT_TEAM_SELECTED_TEAM_OPTION = "SELECTED_TEAM_ID"


def plugin_options_from_metadata(metadata: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return a normalized copy of metadata.plugin_options."""
    if not isinstance(metadata, dict):
        return {}
    plugin_options = metadata.get("plugin_options")
    if not isinstance(plugin_options, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for plugin_id, values in plugin_options.items():
        if isinstance(plugin_id, str) and plugin_id and isinstance(values, dict):
            normalized[plugin_id] = dict(values)
    return normalized


def plugin_option_from_metadata(
    metadata: dict[str, Any] | None,
    *,
    plugin_id: str,
    key: str,
) -> Any:
    """Return one plugin-scoped metadata option value."""
    return plugin_options_from_metadata(metadata).get(plugin_id, {}).get(key)


def filter_declared_plugin_options(
    runtime: Any,
    metadata: dict[str, Any] | None,
    *,
    scope: str,
) -> dict[str, dict[str, Any]]:
    """Keep only plugin options declared by manifests for a host scope.

    When no runtime is attached, callers keep compatibility with older saved
    metadata and tests by returning normalized plugin options unchanged.
    """
    plugin_options = plugin_options_from_metadata(metadata)
    if runtime is None or not plugin_options:
        return plugin_options
    get_state = getattr(runtime, "get_state", None)
    if not callable(get_state):
        return plugin_options

    filtered: dict[str, dict[str, Any]] = {}
    for plugin_id, values in plugin_options.items():
        state = get_state(plugin_id)
        manifest = getattr(state, "manifest", None)
        if manifest is None:
            continue
        declared_keys = _declared_option_keys_for_scope(manifest, scope)
        plugin_values = {
            key: value for key, value in values.items() if key in declared_keys
        }
        if plugin_values:
            filtered[plugin_id] = plugin_values
    return filtered


def declared_session_options_from_project_defaults(
    runtime: Any,
    project_metadata: dict[str, Any] | None,
    *,
    agent_id: str | None = None,
    executable_only: bool = True,
) -> dict[str, dict[str, Any]]:
    """Map plugin-declared project defaults into session-scoped options.

    Plugins use ``project_options[].applies_to_session_key`` to say that a
    project-level default should initialize a session option when the current
    request has not selected one explicitly.
    """
    if runtime is None:
        return {}
    manifests = _runtime_manifests(runtime)
    if not manifests:
        from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS

        manifests = list(BUILTIN_PLUGIN_MANIFESTS)
    project_options = plugin_options_from_metadata(project_metadata)
    if not project_options:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for manifest in manifests:
        plugin_id = getattr(manifest, "id", None)
        if not isinstance(plugin_id, str) or not plugin_id:
            continue
        if executable_only and not _runtime_plugin_is_executable(runtime, plugin_id):
            continue
        values = project_options.get(plugin_id, {})
        if not values:
            continue
        declared_session_keys = _declared_option_keys_for_scope(manifest, "session")
        for option in _frontend_options_for_scope(manifest, "project"):
            if not _option_visible_for_agent(option, agent_id):
                continue
            project_key = getattr(option, "key", None)
            session_key = getattr(option, "applies_to_session_key", None)
            if not isinstance(project_key, str) or not isinstance(session_key, str):
                continue
            if session_key not in declared_session_keys or project_key not in values:
                continue
            value = values.get(project_key)
            if value is None or value == "":
                continue
            result.setdefault(plugin_id, {})[session_key] = value
    return result


def declared_plugin_options_from_metadata(
    runtime: Any,
    metadata: dict[str, Any] | None,
    *,
    scope: str,
    agent_id: str | None = None,
    executable_only: bool = False,
    legacy_payload_keys_provided: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return plugin options declared for a scope, importing legacy payload keys.

    Explicit ``metadata.plugin_options`` values win. Legacy top-level payload keys
    are imported only through manifest-declared scoped option definitions, so old
    fields such as ``team_id`` remain compatibility input instead of becoming a
    new hardcoded execution contract.
    """
    explicit_options = plugin_options_from_metadata(metadata)
    if runtime is None:
        return explicit_options
    manifests = _runtime_manifests(runtime)
    if not manifests:
        return explicit_options

    normalized_metadata = metadata if isinstance(metadata, dict) else {}
    explicit_legacy_keys = set(legacy_payload_keys_provided or [])
    result: dict[str, dict[str, Any]] = {}
    for manifest in manifests:
        plugin_id = getattr(manifest, "id", None)
        if not isinstance(plugin_id, str) or not plugin_id:
            continue
        if executable_only and not _runtime_plugin_is_executable(runtime, plugin_id):
            continue
        declared_keys = _declared_option_keys_for_scope(manifest, scope)
        values = {
            key: value
            for key, value in explicit_options.get(plugin_id, {}).items()
            if key in declared_keys
        }

        for option in _frontend_options_for_scope(manifest, scope):
            key = getattr(option, "key", None)
            if not isinstance(key, str) or not key:
                continue
            legacy_keys = getattr(option, "legacy_payload_keys", []) or []
            legacy_key_provided = False
            for legacy_key in legacy_keys:
                if legacy_key in normalized_metadata:
                    legacy_key_provided = (
                        legacy_payload_keys_provided is not None
                        and legacy_key in explicit_legacy_keys
                    )
                    if key in values and not legacy_key_provided:
                        break
                    legacy_value = normalized_metadata.get(legacy_key)
                    if legacy_value is None:
                        values.pop(key, None)
                    else:
                        values[key] = legacy_value
                    break
            if legacy_key_provided:
                continue
            if key in values:
                continue
            if not _option_visible_for_agent(option, agent_id):
                continue

        if values:
            result[plugin_id] = values
    return result


def with_plugin_options(
    metadata: dict[str, Any] | None,
    plugin_options: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return metadata with a group of plugin-scoped options merged in."""
    next_metadata = deepcopy(metadata or {})
    for plugin_id, values in plugin_options.items():
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            next_metadata = with_plugin_option(
                next_metadata,
                plugin_id=plugin_id,
                key=key,
                value=value,
            )
    return next_metadata


def _runtime_manifests(runtime: Any) -> list[Any]:
    manifests = getattr(runtime, "manifests", None)
    if callable(manifests):
        try:
            return list(manifests(enabled_only=False))
        except TypeError:
            return list(manifests())
    states = getattr(runtime, "states", None)
    if callable(states):
        return [state.manifest for state in states() if getattr(state, "manifest", None)]
    return []


def _runtime_plugin_is_executable(runtime: Any, plugin_id: str) -> bool:
    is_enabled = getattr(runtime, "is_enabled", None)
    if callable(is_enabled):
        return bool(is_enabled(plugin_id))
    get_state = getattr(runtime, "get_state", None)
    if not callable(get_state):
        return True
    state = get_state(plugin_id)
    if state is None:
        return False
    return bool(getattr(state, "executable", False))


def _frontend_options_for_scope(manifest: Any, scope: str) -> list[Any]:
    frontend = getattr(manifest, "frontend", None)
    option_attr = {
        "project": "project_options",
        "session": "session_options",
        "channel": "channel_options",
        "scheduled_task": "scheduled_task_options",
    }.get(scope)
    if frontend is None or not option_attr:
        return []
    return list(getattr(frontend, option_attr, []) or [])


def _option_visible_for_agent(option: Any, agent_id: str | None) -> bool:
    visible_when = getattr(option, "visible_when", None)
    expected_agent_id = getattr(visible_when, "agent_id", None)
    if not expected_agent_id:
        return True
    return agent_id == expected_agent_id


def _declared_option_keys_for_scope(manifest: Any, scope: str) -> set[str]:
    declared: set[str] = set()
    declared.update(
        option.key for option in _frontend_options_for_scope(manifest, scope) if getattr(option, "key", None)
    )
    declared.update(
        setting.key
        for setting in getattr(manifest, "settings", [])
        if getattr(setting, "scope", None) == scope and getattr(setting, "key", None)
    )
    return declared


def plugin_id_for_agent(
    agent_id: str | None,
    *,
    runtime: Any = None,
    manifests: Any = None,
) -> str | None:
    """Return the plugin that declares an agent id, if any."""
    if not isinstance(agent_id, str) or not agent_id.strip():
        return None
    normalized_agent_id = agent_id.strip()
    plugin_for_agent = getattr(runtime, "plugin_for_agent", None)
    if callable(plugin_for_agent):
        plugin_id = plugin_for_agent(normalized_agent_id)
        if isinstance(plugin_id, str) and plugin_id:
            return plugin_id
    if manifests is None:
        from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS

        manifests = BUILTIN_PLUGIN_MANIFESTS
    for manifest in manifests or []:
        for agent in getattr(manifest, "agents", []) or []:
            if getattr(agent, "id", None) == normalized_agent_id:
                return getattr(manifest, "id", None)
    return None


def plugin_agent_ids(
    plugin_id: str,
    *,
    runtime: Any = None,
    manifests: Any = None,
) -> list[str]:
    """Return agent ids declared by a plugin manifest."""
    if not isinstance(plugin_id, str) or not plugin_id.strip():
        return []
    normalized_plugin_id = plugin_id.strip()
    if runtime is not None:
        agents = getattr(runtime, "agents", None)
        if callable(agents):
            try:
                registrations = list(agents(enabled_only=False))
            except TypeError:
                registrations = list(agents())
            return [
                registration.id
                for registration in registrations
                if getattr(registration, "plugin_id", None) == normalized_plugin_id
                and getattr(registration, "id", None)
            ]
    if manifests is None:
        from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS

        manifests = BUILTIN_PLUGIN_MANIFESTS
    agent_ids: list[str] = []
    for manifest in manifests or []:
        if getattr(manifest, "id", None) != normalized_plugin_id:
            continue
        agent_ids.extend(
            agent.id for agent in getattr(manifest, "agents", []) or [] if getattr(agent, "id", None)
        )
    return agent_ids


def first_plugin_agent_id(
    plugin_id: str,
    *,
    runtime: Any = None,
    manifests: Any = None,
) -> str | None:
    """Return the first agent id declared by a plugin manifest, if any."""
    ids = plugin_agent_ids(plugin_id, runtime=runtime, manifests=manifests)
    return ids[0] if ids else None


def agent_uses_agent_team_options(
    agent_id: str | None,
    *,
    runtime: Any = None,
    manifests: Any = None,
) -> bool:
    """Return whether an agent should consume Agent Team scoped options."""
    return plugin_id_for_agent(agent_id, runtime=runtime, manifests=manifests) == AGENT_TEAM_PLUGIN_ID


def plugin_session_option_visible_for_agent(
    manifest: Any,
    key: str,
    agent_id: str | None,
) -> bool:
    """Return whether a manifest session option is visible for an agent context."""
    for option in _frontend_options_for_scope(manifest, "session"):
        if getattr(option, "key", None) == key:
            return _option_visible_for_agent(option, agent_id)
    return False


def plugin_session_options_suppress_core_persona(
    agent_id: str | None,
    metadata: dict[str, Any] | None,
    *,
    runtime: Any = None,
    manifests: Any = None,
) -> bool:
    """Return whether selected plugin session options suppress core persona state."""
    if not isinstance(agent_id, str) or not agent_id.strip():
        return False
    normalized_agent_id = agent_id.strip()
    normalized_metadata = metadata if isinstance(metadata, dict) else {}
    plugin_options = plugin_options_from_metadata(normalized_metadata)
    declared_manifests = _runtime_manifests(runtime) if runtime is not None else []
    if not declared_manifests:
        if manifests is None:
            from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS

            manifests = BUILTIN_PLUGIN_MANIFESTS
        declared_manifests = list(manifests or [])
    owning_plugin_id = plugin_id_for_agent(
        normalized_agent_id,
        runtime=runtime,
        manifests=declared_manifests,
    )
    for manifest in declared_manifests:
        plugin_id = getattr(manifest, "id", None)
        if not isinstance(plugin_id, str) or not plugin_id:
            continue
        for option in _frontend_options_for_scope(manifest, "session"):
            if not getattr(option, "suppresses_core_persona_selector", False):
                continue
            if plugin_id != owning_plugin_id:
                visible_when = getattr(option, "visible_when", None)
                expected_agent_id = getattr(visible_when, "agent_id", None)
                if expected_agent_id != normalized_agent_id:
                    continue
            key = getattr(option, "key", None)
            if not isinstance(key, str) or not key:
                continue
            value = plugin_options.get(plugin_id, {}).get(key)
            if value not in (None, ""):
                return True
            for legacy_key in getattr(option, "legacy_payload_keys", []) or []:
                legacy_value = normalized_metadata.get(legacy_key)
                if legacy_value not in (None, ""):
                    return True
    return False


def selected_agent_team_id_from_metadata(metadata: dict[str, Any] | None) -> str | None:
    """Return the Agent Team session option, falling back to legacy team_id."""
    selected_team_id = plugin_option_from_metadata(
        metadata,
        plugin_id=AGENT_TEAM_PLUGIN_ID,
        key=AGENT_TEAM_SELECTED_TEAM_OPTION,
    )
    if isinstance(selected_team_id, str) and selected_team_id:
        return selected_team_id
    if not isinstance(metadata, dict):
        return None
    legacy_team_id = metadata.get("team_id")
    return legacy_team_id if isinstance(legacy_team_id, str) and legacy_team_id else None


def agent_team_session_plugin_options(team_id: str) -> dict[str, dict[str, str]]:
    """Build the session plugin_options payload for Agent Team selection."""
    return {AGENT_TEAM_PLUGIN_ID: {AGENT_TEAM_SELECTED_TEAM_OPTION: team_id}}


def with_agent_team_session_option(
    metadata: dict[str, Any],
    team_id: str | None,
) -> dict[str, Any]:
    """Return metadata with Agent Team selection written under plugin_options."""
    if not team_id:
        return metadata
    return with_plugin_option(
        metadata,
        plugin_id=AGENT_TEAM_PLUGIN_ID,
        key=AGENT_TEAM_SELECTED_TEAM_OPTION,
        value=team_id,
    )


def with_plugin_option(
    metadata: dict[str, Any] | None,
    *,
    plugin_id: str,
    key: str,
    value: Any,
) -> dict[str, Any]:
    """Return metadata with one plugin option written in metadata.plugin_options."""
    _validate_plugin_option_path(plugin_id=plugin_id, key=key)
    next_metadata = deepcopy(metadata or {})
    plugin_options = plugin_options_from_metadata(next_metadata)
    plugin_values = dict(plugin_options.get(plugin_id, {}))
    if value is None:
        plugin_values.pop(key, None)
    else:
        plugin_values[key] = value
    if plugin_values:
        plugin_options[plugin_id] = plugin_values
    else:
        plugin_options.pop(plugin_id, None)
    next_metadata["plugin_options"] = plugin_options
    return next_metadata


def _validate_plugin_option_path(*, plugin_id: str, key: str) -> None:
    if not plugin_id or any(part in {"", ".", ".."} for part in plugin_id.replace("\\", "/").split("/")):
        raise ValueError("plugin_id must be a safe plugin id")
    if not key or "." in key or any(part in {"", ".", ".."} for part in key.replace("\\", "/").split("/")):
        raise ValueError("plugin option key must be a safe plugin-local key")
