from src.kernel.extensions import (
    AUDIO_TRANSCRIPTION_PLUGIN_ID,
    PluginResourceType,
    PluginRuntime,
    PluginRuntimeStatus,
    build_audio_transcription_plugin_manifest,
    build_uninstall_dry_run,
)
from src.kernel.types import Permission


def test_audio_transcription_plugin_manifest_preserves_legacy_tool_name(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.kernel.extensions.builtin_plugins.settings.ENABLE_AUDIO_TRANSCRIPTION",
        True,
    )

    manifest = build_audio_transcription_plugin_manifest()

    assert manifest.id == AUDIO_TRANSCRIPTION_PLUGIN_ID
    assert manifest.enabled_by_default is True
    assert [(tool.name, tool.legacy_ids) for tool in manifest.tools] == [
        ("audio_transcribe", ["audio_transcribe"])
    ]
    assert manifest.tools[0].required_permissions == [Permission.MCP_READ.value]
    assert manifest.frontend.tool_renderers[0].id == "audio_transcription:audio-transcribe"
    assert manifest.frontend.tool_renderers[0].tool_names == [
        "audio_transcription.audio_transcribe",
        "audio_transcribe",
    ]
    assert manifest.setting_keys() == ["API_KEY", "BASE_URL", "MODEL", "MAX_DOWNLOAD_BYTES"]
    assert "ENABLE_AUDIO_TRANSCRIPTION" in manifest.legacy_setting_keys()
    assert "AUDIO_TRANSCRIPTION_MAX_DOWNLOAD_BYTES" in manifest.legacy_setting_keys()


def test_audio_transcription_plugin_runtime_can_start_disabled_by_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.kernel.extensions.builtin_plugins.settings.ENABLE_AUDIO_TRANSCRIPTION",
        False,
    )
    runtime = PluginRuntime([build_audio_transcription_plugin_manifest()])

    state = runtime.get_state(AUDIO_TRANSCRIPTION_PLUGIN_ID)

    assert state is not None
    assert state.status is PluginRuntimeStatus.DISABLED
    assert state.issues == []
    assert runtime.tools() == []
    assert [(tool.plugin_id, tool.name) for tool in runtime.tools(enabled_only=False)] == [
        (AUDIO_TRANSCRIPTION_PLUGIN_ID, "audio_transcribe")
    ]


def test_audio_transcription_plugin_resources_and_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.kernel.extensions.builtin_plugins.settings.ENABLE_AUDIO_TRANSCRIPTION",
        True,
    )
    runtime = PluginRuntime([build_audio_transcription_plugin_manifest()])

    resource_keys = {
        (resource.resource_type, resource.resource_id)
        for resource in runtime.resource_ledger.list(plugin_id=AUDIO_TRANSCRIPTION_PLUGIN_ID)
    }
    dry_run = build_uninstall_dry_run(
        plugin_id=AUDIO_TRANSCRIPTION_PLUGIN_ID,
        ledger=runtime.resource_ledger,
    )

    assert (PluginResourceType.TOOL, "audio_transcribe") in resource_keys
    assert (
        PluginResourceType.TOOL_RENDERER,
        "audio_transcription:audio-transcribe",
    ) in resource_keys
    assert (PluginResourceType.SETTING, "audio_transcription.API_KEY") in resource_keys
    assert (
        PluginResourceType.SETTING,
        "audio_transcription.MAX_DOWNLOAD_BYTES",
    ) in resource_keys
    assert (
        PluginResourceType.ENV_KEY_DECLARATION,
        "AUDIO_TRANSCRIPTION_API_KEY",
    ) in resource_keys
    assert dry_run.resource_count == 8
    assert dry_run.will_delete == []
    assert dry_run.needs_manual_review == []
    assert dry_run.forbidden_to_delete == []


def test_audio_transcription_plugin_tool_guard_uses_legacy_tool_name(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.kernel.extensions.builtin_plugins.settings.ENABLE_AUDIO_TRANSCRIPTION",
        True,
    )
    runtime = PluginRuntime([build_audio_transcription_plugin_manifest()])

    registration = runtime.ensure_tool_available("audio_transcribe")

    assert registration.plugin_id == AUDIO_TRANSCRIPTION_PLUGIN_ID
    runtime.disable_plugin(AUDIO_TRANSCRIPTION_PLUGIN_ID)
    assert runtime.tools() == []
