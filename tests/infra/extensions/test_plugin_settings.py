import pytest

from src.infra.extensions import (
    MASKED_SECRET_VALUE,
    InMemoryPluginSettingsStorage,
    PluginSettingsResolver,
    PluginSettingsService,
    plugin_owned_system_setting_keys,
)
from src.kernel.extensions import build_audio_transcription_plugin_manifest
from src.kernel.extensions.builtin_plugins import build_image_generation_plugin_manifest
from src.kernel.extensions.manifest import PluginManifest


class HangingPluginSettingsStorage:
    async def list(self, **_kwargs):
        import asyncio

        await asyncio.sleep(5)
        return []

    async def get(self, **_kwargs):
        import asyncio

        await asyncio.sleep(5)
        return None


@pytest.mark.asyncio
async def test_plugin_settings_service_masks_sensitive_values_and_preserves_mask() -> None:
    manifest = build_image_generation_plugin_manifest()
    storage = InMemoryPluginSettingsStorage()
    service = PluginSettingsService(storage=storage)

    await service.set_setting(manifest, key="API_KEY", value="sk-test", updated_by="admin")
    await service.set_setting(
        manifest,
        key="API_KEY",
        value=MASKED_SECRET_VALUE,
        updated_by="admin-2",
    )

    settings = await service.list_settings(manifest)
    raw = await storage.get(plugin_id=manifest.id, key="API_KEY")

    assert raw is not None
    assert raw.value == "sk-test"
    assert next(item for item in settings if item["key"] == "API_KEY")["value"] == MASKED_SECRET_VALUE


@pytest.mark.asyncio
async def test_plugin_settings_resolver_reads_plugin_values() -> None:
    manifest = build_audio_transcription_plugin_manifest()
    storage = InMemoryPluginSettingsStorage()
    service = PluginSettingsService(storage=storage)
    await service.set_setting(manifest, key="MAX_DOWNLOAD_BYTES", value="42", updated_by="admin")

    resolver = PluginSettingsResolver(
        plugin_id=manifest.id,
        manifests=(manifest,),
        service=service,
    )

    assert await resolver.get_int("MAX_DOWNLOAD_BYTES", 1) == 42


def test_plugin_owned_system_setting_keys_include_migrated_media_provider_keys() -> None:
    manifests = (
        build_image_generation_plugin_manifest(),
        build_audio_transcription_plugin_manifest(),
    )

    mapping = plugin_owned_system_setting_keys(manifests)

    assert mapping["IMAGE_GENERATION_API_KEY"] == "image_generation"
    assert mapping["IMAGE_GENERATION_BASE_URL"] == "image_generation"
    assert mapping["ENABLE_IMAGE_GENERATION"] == "image_generation"
    assert mapping["AUDIO_TRANSCRIPTION_API_KEY"] == "audio_transcription"
    assert mapping["ENABLE_AUDIO_TRANSCRIPTION"] == "audio_transcription"


@pytest.mark.asyncio
async def test_plugin_settings_list_falls_back_when_storage_read_is_unavailable() -> None:
    manifest = build_image_generation_plugin_manifest()
    service = PluginSettingsService(storage=HangingPluginSettingsStorage())

    settings = await service.list_settings(manifest)

    values_by_key = {item["key"]: item for item in settings}
    assert set(values_by_key) == {"API_KEY", "BASE_URL", "MODEL", "TIMEOUT"}
    assert values_by_key["MODEL"]["value"] == "gpt-image-2"
    assert values_by_key["MODEL"]["source"] in {
        "default",
        "plugin_data:default",
        "legacy:IMAGE_GENERATION_MODEL",
        "env:IMAGE_GENERATION_MODEL",
    }


@pytest.mark.asyncio
async def test_plugin_settings_service_isolates_project_and_session_scopes() -> None:
    manifest = PluginManifest(
        id="agent_team",
        name="Agent Team",
        version="1.0.0",
        api_version="v1",
        settings=[
            {
                "key": "API_MODE",
                "type": "string",
                "scope": "system",
                "default": "managed",
            },
            {
                "key": "SELECTED_TEAM_ID",
                "type": "string",
                "scope": "session",
                "default": "",
            },
            {
                "key": "SELECTED_TEAM_ID",
                "type": "string",
                "scope": "channel",
                "default": "",
            },
            {
                "key": "SELECTED_TEAM_ID",
                "type": "string",
                "scope": "scheduled_task",
                "default": "",
            },
        ],
    )
    storage = InMemoryPluginSettingsStorage()
    service = PluginSettingsService(storage=storage)

    await service.set_setting(
        manifest,
        key="SELECTED_TEAM_ID",
        value="team-1",
        scope="session",
        subject_id="session-1",
        updated_by="user-1",
    )
    await service.set_setting(
        manifest,
        key="SELECTED_TEAM_ID",
        value="team-channel",
        scope="channel",
        subject_id="channel-1",
        updated_by="user-1",
    )
    await service.set_setting(
        manifest,
        key="SELECTED_TEAM_ID",
        value="team-task",
        scope="scheduled_task",
        subject_id="task-1",
        updated_by="user-1",
    )

    system_settings = await service.list_settings(manifest)
    session_settings = await service.list_settings(
        manifest,
        scope="session",
        subject_id="session-1",
    )
    channel_settings = await service.list_settings(
        manifest,
        scope="channel",
        subject_id="channel-1",
    )
    scheduled_task_settings = await service.list_settings(
        manifest,
        scope="scheduled_task",
        subject_id="task-1",
    )

    assert [item["key"] for item in system_settings] == ["API_MODE"]
    assert [item["key"] for item in session_settings] == ["SELECTED_TEAM_ID"]
    assert session_settings[0]["value"] == "team-1"
    assert session_settings[0]["source"] == "manual"
    assert channel_settings[0]["value"] == "team-channel"
    assert scheduled_task_settings[0]["value"] == "team-task"

    with pytest.raises(KeyError):
        await service.set_setting(
            manifest,
            key="SELECTED_TEAM_ID",
            value="team-2",
            updated_by="user-1",
        )


@pytest.mark.asyncio
async def test_plugin_settings_export_includes_scoped_subject_values_and_masks_sensitive() -> None:
    manifest = PluginManifest(
        id="agent_team",
        name="Agent Team",
        version="1.0.0",
        api_version="v1",
        settings=[
            {
                "key": "API_TOKEN",
                "type": "string",
                "scope": "system",
                "sensitive": True,
                "default": "",
            },
            {
                "key": "SELECTED_TEAM_ID",
                "type": "string",
                "scope": "channel",
                "default": "",
            },
            {
                "key": "SELECTED_TEAM_ID",
                "type": "string",
                "scope": "scheduled_task",
                "default": "",
            },
        ],
    )
    storage = InMemoryPluginSettingsStorage()
    service = PluginSettingsService(storage=storage)

    await service.set_setting(manifest, key="API_TOKEN", value="secret", updated_by="admin")
    await service.set_setting(
        manifest,
        key="SELECTED_TEAM_ID",
        value="team-channel",
        scope="channel",
        subject_id="channel-1",
        updated_by="admin",
    )
    await service.set_setting(
        manifest,
        key="SELECTED_TEAM_ID",
        value="team-task",
        scope="scheduled_task",
        subject_id="task-1",
        updated_by="admin",
    )

    exported = await service.export_settings(manifest)
    by_scope_subject = {
        (item["scope"], item["subject_id"], item["key"]): item for item in exported
    }

    assert by_scope_subject[("system", None, "API_TOKEN")]["value"] == MASKED_SECRET_VALUE
    assert by_scope_subject[("channel", "channel-1", "SELECTED_TEAM_ID")]["value"] == "team-channel"
    assert by_scope_subject[("scheduled_task", "task-1", "SELECTED_TEAM_ID")]["value"] == "team-task"
    assert by_scope_subject[("channel", None, "SELECTED_TEAM_ID")]["source"] == "default"
    assert by_scope_subject[("scheduled_task", None, "SELECTED_TEAM_ID")]["source"] == "default"
