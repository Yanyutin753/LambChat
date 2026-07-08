from __future__ import annotations

from src.infra.channel.plugin_connectors import (
    connector_id_for_channel_type,
    ensure_channel_connector_available_for_type,
)
from src.kernel.extensions import PluginManifest, PluginRuntime
from src.kernel.schemas.channel import ChannelType


def _alternate_feishu_runtime() -> PluginRuntime:
    return PluginRuntime(
        [
            PluginManifest(
                id="alternate_feishu_connector",
                name="Alternate Feishu Connector",
                version="1.0.0",
                api_version="v1",
                frontend={
                    "channel_connectors": [
                        {
                            "id": "alternate_feishu_connector:feishu",
                            "channel_type": "feishu",
                        }
                    ]
                },
            )
        ]
    )


def test_connector_id_for_channel_type_prefers_runtime_manifest() -> None:
    runtime = _alternate_feishu_runtime()

    assert connector_id_for_channel_type(ChannelType.FEISHU, runtime) == (
        "alternate_feishu_connector:feishu"
    )


def test_plugin_managed_channel_requires_runtime_when_only_builtin_manifest_available() -> None:
    available, connector_id, exc = ensure_channel_connector_available_for_type(
        ChannelType.FEISHU,
        None,
    )

    assert available is False
    assert connector_id == "feishu_connector:feishu"
    assert exc is None


def test_connector_availability_uses_runtime_declared_connector_id() -> None:
    runtime = _alternate_feishu_runtime()
    enabled, enabled_connector_id, enabled_exc = ensure_channel_connector_available_for_type(
        ChannelType.FEISHU,
        runtime,
    )
    runtime.disable_plugin("alternate_feishu_connector")
    disabled, disabled_connector_id, disabled_exc = ensure_channel_connector_available_for_type(
        ChannelType.FEISHU,
        runtime,
    )

    assert enabled is True
    assert enabled_connector_id == "alternate_feishu_connector:feishu"
    assert enabled_exc is None
    assert disabled is False
    assert disabled_connector_id == "alternate_feishu_connector:feishu"
    assert disabled_exc is not None
