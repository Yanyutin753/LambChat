"""Helpers for syncing plugin-scoped host options into plugin settings."""

from __future__ import annotations

from typing import Any, Literal

from src.infra.extensions.plugin_settings import PluginSettingsService
from src.kernel.extensions.manifest import PluginManifest, PluginScopedOption
from src.kernel.extensions.plugin_options import plugin_options_from_metadata, with_plugin_option
from src.kernel.extensions.runtime import PluginRuntime

PluginOptionScope = Literal["project", "session", "channel", "scheduled_task"]


def _manifest(runtime: PluginRuntime, plugin_id: str) -> PluginManifest | None:
    state = runtime.get_state(plugin_id)
    return state.manifest if state is not None else None


def _declared_options(manifest: PluginManifest, scope: PluginOptionScope) -> list[PluginScopedOption]:
    if scope == "project":
        return list(manifest.frontend.project_options)
    if scope == "session":
        return list(manifest.frontend.session_options)
    if scope == "channel":
        return list(manifest.frontend.channel_options)
    return list(manifest.frontend.scheduled_task_options)


def _has_scoped_settings(manifest: PluginManifest, scope: PluginOptionScope) -> bool:
    return any(setting.scope == scope for setting in manifest.settings)


def scoped_option_definition(
    runtime: PluginRuntime,
    *,
    scope: PluginOptionScope,
    plugin_id: str,
    key: str,
) -> PluginScopedOption:
    """Return a manifest-declared scoped option or raise KeyError."""
    manifest = _manifest(runtime, plugin_id)
    if manifest is None:
        raise KeyError(f"Plugin '{plugin_id}' not found")
    for option in _declared_options(manifest, scope):
        if option.key == key:
            return option
    raise KeyError(f"Plugin {scope} option '{plugin_id}.{key}' not declared")


def scoped_option_manifest(runtime: PluginRuntime, plugin_id: str) -> PluginManifest:
    """Return a plugin manifest for scoped option persistence."""
    manifest = _manifest(runtime, plugin_id)
    if manifest is None:
        raise KeyError(f"Plugin '{plugin_id}' not found")
    return manifest


def validate_scoped_plugin_option_value(option: PluginScopedOption, value: Any) -> Any:
    """Validate a plugin-scoped option value against its manifest type."""
    if value is None:
        return None
    if option.type in {"string", "text", "select"}:
        if not isinstance(value, str):
            raise ValueError("Plugin scoped option value must be a string")
        if option.options and value not in option.options:
            raise ValueError("Plugin scoped option value is not allowed")
        return value
    if option.type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Plugin scoped option value must be a number")
        return value
    if option.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Plugin scoped option value must be a boolean")
        return value
    if option.type == "json":
        return value
    raise ValueError("Unsupported plugin scoped option type")


def scoped_plugin_is_executable(runtime: PluginRuntime, plugin_id: str) -> bool:
    """Return whether a plugin-owned scoped option is currently effective."""
    state = runtime.get_state(plugin_id)
    return bool(state and state.executable)


async def sync_plugin_options_to_settings(
    *,
    runtime: PluginRuntime,
    service: PluginSettingsService,
    scope: PluginOptionScope,
    subject_id: str,
    plugin_options: dict[str, dict[str, Any]] | None,
    updated_by: str | None,
) -> None:
    """Persist manifest-declared scoped plugin options to plugin_settings."""
    normalized = plugin_options_from_metadata({"plugin_options": plugin_options or {}})
    for plugin_id, values in normalized.items():
        manifest = _manifest(runtime, plugin_id)
        if manifest is None:
            continue
        declared_keys = {option.key for option in _declared_options(manifest, scope)}
        for key, value in values.items():
            if key not in declared_keys:
                continue
            await service.set_setting(
                manifest,
                key=key,
                value=value,
                updated_by=updated_by,
                scope=scope,
                subject_id=subject_id,
            )


async def plugin_options_with_settings(
    *,
    runtime: PluginRuntime,
    service: PluginSettingsService,
    scope: PluginOptionScope,
    subject_id: str,
    plugin_options: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Return plugin_options with persisted scoped settings overlaid."""
    merged = plugin_options_from_metadata({"plugin_options": plugin_options or {}})
    for state in runtime.states():
        manifest = state.manifest
        if manifest is None:
            continue
        if not _declared_options(manifest, scope) and not _has_scoped_settings(manifest, scope):
            continue
        try:
            settings = await service.list_settings(
                manifest,
                mask_sensitive=True,
                scope=scope,
                subject_id=subject_id,
            )
        except Exception:
            continue
        for item in settings:
            value = item.get("value")
            default_value = item.get("default_value")
            if value is None or (value == "" and default_value in (None, "")):
                continue
            merged = with_plugin_option(
                {"plugin_options": merged},
                plugin_id=manifest.id,
                key=str(item["key"]),
                value=value,
            )["plugin_options"]
    return merged
