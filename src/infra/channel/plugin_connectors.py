"""Helpers for resolving plugin-declared channel connectors."""

from __future__ import annotations

from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS, PluginRuntime, PluginUnavailableError
from src.kernel.schemas.channel import ChannelType


def connector_id_for_channel_type(
    channel_type: ChannelType | str,
    runtime: PluginRuntime | None,
) -> str | None:
    """Return the plugin connector id declared for a channel type, if any."""
    value = channel_type.value if isinstance(channel_type, ChannelType) else str(channel_type)
    manifests = (
        runtime.manifests(enabled_only=False)
        if runtime is not None
        else BUILTIN_PLUGIN_MANIFESTS
    )
    for manifest in manifests:
        for connector in manifest.frontend.channel_connectors:
            if connector.channel_type == value:
                return connector.id
    return None


def ensure_channel_connector_available_for_type(
    channel_type: ChannelType | str,
    runtime: PluginRuntime | None,
) -> tuple[bool, str | None, PluginUnavailableError | None]:
    """Check a channel connector using manifest ownership instead of hardcoded ids."""
    connector_id = connector_id_for_channel_type(channel_type, runtime)
    if connector_id is None:
        return True, None, None
    if runtime is None:
        return False, connector_id, None
    try:
        runtime.ensure_channel_connector_available(connector_id)
    except PluginUnavailableError as exc:
        return False, connector_id, exc
    return True, connector_id, None
