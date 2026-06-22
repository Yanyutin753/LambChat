from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.routes import channels as channels_route
from src.infra.channel.feishu import registration as feishu_registration
from src.infra.extensions import InMemoryPluginSettingsStorage, PluginSettingsService
from src.kernel.extensions import (
    AGENT_TEAM_PLUGIN_ID,
    FEISHU_CONNECTOR_PLUGIN_ID,
    PluginRuntime,
    build_agent_team_plugin_manifest,
    build_feishu_connector_plugin_manifest,
)
from src.kernel.extensions.manifest import PluginManifest
from src.kernel.schemas.channel import ChannelConfigCreate, ChannelConfigUpdate, ChannelType


class _FakeChannelClass:
    @staticmethod
    def get_metadata() -> dict:
        return {"config_fields": [], "capabilities": []}


class _FakeRegistry:
    def __init__(self, manager_class=None, channel_type: str = "feishu") -> None:
        self._manager_class = manager_class
        self._channel_type = channel_type

    def get_channel_class(self, channel_type: ChannelType):
        return _FakeChannelClass

    def get_manager_class(self, channel_type: ChannelType):
        return self._manager_class

    def get_channel_metadata(self):
        return [
            {
                "channel_type": self._channel_type,
                "display_name": self._channel_type.title(),
                "description": f"{self._channel_type} channel",
                "icon": self._channel_type,
                "capabilities": [],
                "config_schema": {},
                "requires_webhook": False,
                "requires_websocket": True,
                "setup_guide": [],
                "config_fields": [],
            },
        ]


class _FakeStorage:
    def __init__(self) -> None:
        self.create_calls = 0
        self.update_calls = 0
        self.last_create_kwargs = {}
        self.last_update_kwargs = {}

    async def create_config(self, **kwargs):
        self.create_calls += 1
        self.last_create_kwargs = kwargs
        return {"instance_id": "instance-1"}

    async def get_config(self, user_id: str, channel_type: ChannelType, instance_id: str):
        return {"app_id": "app-1", "enabled": True}

    async def update_config(self, **kwargs):
        self.update_calls += 1
        self.last_update_kwargs = kwargs
        return {"instance_id": "instance-1"}

    async def get_response(
        self, user_id: str, channel_type: ChannelType, instance_id: str, metadata
    ):
        return SimpleNamespace(instance_id=instance_id)

    async def get_status(self, user_id: str, channel_type: ChannelType, instance_id: str):
        return SimpleNamespace(channel_type=channel_type, enabled=True, connected=False)


class _FakeTeamPluginOptionStorage(_FakeStorage):
    async def get_config(self, user_id: str, channel_type: ChannelType, instance_id: str):
        return {
            "app_id": "app-1",
            "enabled": True,
            "agent_id": "team",
            "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-old"}},
        }


class _FakeLimitStorage(_FakeStorage):
    def __init__(self, count: int) -> None:
        super().__init__()
        self.count = count
        self.count_calls: list[str] = []
        self.list_calls = 0

    async def count_user_configs(self, user_id: str) -> int:
        self.count_calls.append(user_id)
        return self.count

    async def list_user_configs(self, user_id: str):
        self.list_calls += 1
        raise AssertionError("channel limit check should count configs without loading them")


class _FakeTypedListStorage(_FakeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.typed_calls: list[tuple[str, ChannelType]] = []
        self.typed_count_calls: list[tuple[str, ChannelType]] = []
        self.list_calls = 0

    async def list_user_configs(self, user_id: str):
        self.list_calls += 1
        raise AssertionError("typed channel list should not load every channel config")

    async def count_user_configs_by_type(self, user_id: str, channel_type: ChannelType) -> int:
        self.typed_count_calls.append((user_id, channel_type))
        return 1

    async def list_user_configs_by_type(self, user_id: str, channel_type: ChannelType):
        self.typed_calls.append((user_id, channel_type))
        return [
            {
                "channel_type": channel_type.value,
                "instance_id": "instance-1",
                "name": "Feishu",
                "enabled": True,
                "app_id": "app-1",
                "app_secret": "secret",
                "plugin_options": {},
            }
        ]


class _FakeListLimitStorage(_FakeStorage):
    def __init__(self, count: int, typed_count: int | None = None) -> None:
        super().__init__()
        self.count = count
        self.typed_count = count if typed_count is None else typed_count
        self.count_calls: list[str] = []
        self.typed_count_calls: list[tuple[str, ChannelType]] = []
        self.list_calls = 0
        self.typed_list_calls = 0

    async def count_user_configs(self, user_id: str) -> int:
        self.count_calls.append(user_id)
        return self.count

    async def count_user_configs_by_type(self, user_id: str, channel_type: ChannelType) -> int:
        self.typed_count_calls.append((user_id, channel_type))
        return self.typed_count

    async def list_user_configs(self, user_id: str):
        self.list_calls += 1
        raise AssertionError("oversized channel list should be rejected before loading configs")

    async def list_user_configs_by_type(self, user_id: str, channel_type: ChannelType):
        self.typed_list_calls += 1
        raise AssertionError(
            "oversized typed channel list should be rejected before loading configs"
        )


class _FakeRoleStorage:
    async def get_by_names(self, names):
        assert names == ["limited"]
        return [SimpleNamespace(limits=SimpleNamespace(max_channels=1))]


class _FakeSingleAgentStorage:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.checked_ids: list[str] = []

    async def is_agent_enabled(self, agent_id: str) -> bool:
        self.checked_ids.append(agent_id)
        return self.enabled

    async def get_enabled_agent_ids(self):
        raise AssertionError("agent validation should not load all enabled agent ids")


class _FakeManager:
    def __init__(self) -> None:
        self.reload_calls: list[tuple[str, str]] = []
        self.connected = False

    def is_connected(self, user_id: str, instance_id: str) -> bool:
        return self.connected

    async def reload_user(self, user_id: str, instance_id: str) -> bool:
        self.reload_calls.append((user_id, instance_id))
        self.connected = True
        return True


class _FakeDistributedManager(_FakeManager):
    def __init__(self) -> None:
        super().__init__()
        self.distributed_calls: list[tuple[str, str]] = []

    async def is_connected_distributed(self, user_id: str, instance_id: str) -> bool:
        self.distributed_calls.append((user_id, instance_id))
        return True


class _FakeProjectStorage:
    async def get_by_id(self, project_id: str, user_id: str):
        return None


class _FakePersonaManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bool]] = []

    async def get_preset(self, preset_id: str, *, user_id: str, is_admin: bool):
        self.calls.append((preset_id, user_id, is_admin))
        return SimpleNamespace(id=preset_id)


def _memory_plugin_settings(monkeypatch: pytest.MonkeyPatch) -> PluginSettingsService:
    service = PluginSettingsService(storage=InMemoryPluginSettingsStorage())
    monkeypatch.setattr(channels_route, "_get_plugin_settings_service", lambda _request=None: service)
    return service


def _disabled_feishu_runtime():
    runtime = PluginRuntime([build_feishu_connector_plugin_manifest()])
    runtime.disable_plugin(FEISHU_CONNECTOR_PLUGIN_ID)
    return runtime


def _disabled_alternate_feishu_runtime():
    manifest = PluginManifest(
        id="alternate_feishu_connector",
        name="Alternate Feishu Connector",
        version="1.0.0",
        api_version="v1",
        frontend={
            "channel_connectors": [
                {
                    "id": "alternate_feishu_connector:feishu",
                    "channel_type": "feishu",
                    "panel_renderer": "alternate_feishu_connector.FeishuPanel",
                }
            ]
        },
    )
    runtime = PluginRuntime([manifest])
    runtime.disable_plugin("alternate_feishu_connector")
    return runtime


def _disabled_agent_team_runtime():
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin(AGENT_TEAM_PLUGIN_ID)
    return runtime


@pytest.mark.asyncio
async def test_channel_types_hide_feishu_when_connector_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())

    response = await channels_route.get_channel_types(
        plugin_runtime=_disabled_feishu_runtime()
    )

    assert [channel.channel_type.value for channel in response.types] == []


@pytest.mark.asyncio
async def test_channel_types_hide_any_plugin_declared_connector_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())

    response = await channels_route.get_channel_types(
        plugin_runtime=_disabled_alternate_feishu_runtime()
    )

    assert [channel.channel_type.value for channel in response.types] == []


@pytest.mark.asyncio
async def test_feishu_channel_operations_fail_closed_when_connector_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())

    with pytest.raises(HTTPException) as exc_info:
        await channels_route.list_channel_instances(
            ChannelType.FEISHU,
            plugin_runtime=_disabled_feishu_runtime(),
            user=SimpleNamespace(sub="user-1"),
            storage=storage,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "plugin_unavailable"
    assert exc_info.value.detail["plugin_id"] == FEISHU_CONNECTOR_PLUGIN_ID


@pytest.mark.asyncio
async def test_channel_operations_report_declaring_connector_plugin_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())

    with pytest.raises(HTTPException) as exc_info:
        await channels_route.list_channel_instances(
            ChannelType.FEISHU,
            plugin_runtime=_disabled_alternate_feishu_runtime(),
            user=SimpleNamespace(sub="user-1"),
            storage=storage,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "plugin_unavailable"
    assert exc_info.value.detail["plugin_id"] == "alternate_feishu_connector"


@pytest.mark.asyncio
async def test_feishu_registration_fails_closed_when_connector_is_disabled() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await channels_route.start_feishu_registration(
            plugin_runtime=_disabled_feishu_runtime()
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "plugin_unavailable"


@pytest.mark.asyncio
async def test_validate_persona_preset_id_detects_admin_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakePersonaManager()
    monkeypatch.setattr(
        "src.infra.persona_preset.manager.PersonaPresetManager",
        lambda: manager,
    )

    await channels_route._validate_persona_preset_id(
        "persona-1",
        SimpleNamespace(
            sub="admin-1",
            permissions=["persona_preset:admin"],
        ),
    )

    assert manager.calls == [("persona-1", "admin-1", True)]


@pytest.mark.asyncio
async def test_validate_agent_id_checks_single_agent_without_loading_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_storage = _FakeSingleAgentStorage(enabled=True)
    monkeypatch.setattr(channels_route, "get_agent_config_storage", lambda: agent_storage)

    await channels_route._validate_agent_id(
        "agent-1",
        SimpleNamespace(roles=[]),
    )

    assert agent_storage.checked_ids == ["agent-1"]


@pytest.mark.asyncio
async def test_create_channel_rejects_disabled_plugin_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    from src.agents import set_plugin_runtime

    set_plugin_runtime(_disabled_agent_team_runtime())
    try:
        with pytest.raises(HTTPException) as exc_info:
            await channels_route.create_channel_instance(
                ChannelType.FEISHU,
                ChannelConfigCreate(
                    channel_type=ChannelType.FEISHU,
                    name="Feishu",
                    config={},
                    agent_id="team",
                    plugin_options={"agent_team": {"SELECTED_TEAM_ID": "team-1"}},
                ),
                user=SimpleNamespace(sub="user-1", roles=[], permissions=[]),
                storage=storage,
            )
    finally:
        set_plugin_runtime(None)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "plugin_unavailable"
    assert exc_info.value.detail["plugin_id"] == AGENT_TEAM_PLUGIN_ID
    assert storage.create_calls == 0


@pytest.mark.asyncio
async def test_create_channel_rejects_unknown_project_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: _FakeProjectStorage(),
    )
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    with pytest.raises(HTTPException) as exc_info:
        await channels_route.create_channel_instance(
            ChannelType.FEISHU,
            ChannelConfigCreate(
                channel_type=ChannelType.FEISHU,
                name="Feishu",
                config={},
                project_id="missing-project",
            ),
            user=SimpleNamespace(sub="user-1", roles=[]),
            storage=storage,
        )

    assert exc_info.value.status_code == 400
    assert storage.create_calls == 0


@pytest.mark.asyncio
async def test_update_channel_rejects_unknown_project_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: _FakeProjectStorage(),
    )
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    with pytest.raises(HTTPException) as exc_info:
        await channels_route.update_channel_instance(
            ChannelType.FEISHU,
            "instance-1",
            ChannelConfigUpdate(config={}, project_id="missing-project"),
            user=SimpleNamespace(sub="user-1", roles=[]),
            storage=storage,
        )

    assert exc_info.value.status_code == 400
    assert storage.update_calls == 0


@pytest.mark.asyncio
async def test_create_channel_persists_persona_preset_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "_validate_persona_preset_id", _async_noop)
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    await channels_route.create_channel_instance(
        ChannelType.FEISHU,
        ChannelConfigCreate(
            channel_type=ChannelType.FEISHU,
            name="Feishu",
            config={},
            persona_preset_id="persona-1",
        ),
        user=SimpleNamespace(sub="user-1", roles=[], permissions=[]),
        storage=storage,
    )

    assert storage.last_create_kwargs["persona_preset_id"] == "persona-1"


@pytest.mark.asyncio
async def test_create_channel_stores_agent_team_selection_as_plugin_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    settings_service = _memory_plugin_settings(monkeypatch)
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "_validate_agent_id", _async_noop)
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    await channels_route.create_channel_instance(
        ChannelType.FEISHU,
        ChannelConfigCreate(
            channel_type=ChannelType.FEISHU,
            name="Feishu",
            config={},
            agent_id="team",
            team_id="team-1",
            plugin_options={"agent_team": {"SELECTED_TEAM_ID": "team-1"}},
        ),
        user=SimpleNamespace(sub="user-1", roles=[], permissions=[]),
        storage=storage,
    )

    assert "team_id" not in storage.last_create_kwargs
    assert storage.last_create_kwargs["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }
    record = await settings_service.storage.get(
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
        scope="channel",
        subject_id="instance-1",
    )
    assert record is not None
    assert record.value == "team-1"


@pytest.mark.asyncio
async def test_create_channel_filters_plugin_options_by_channel_manifest_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    settings_service = _memory_plugin_settings(monkeypatch)
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "_validate_agent_id", _async_noop)
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    await channels_route.create_channel_instance(
        ChannelType.FEISHU,
        ChannelConfigCreate(
            channel_type=ChannelType.FEISHU,
            name="Feishu",
            config={},
            agent_id="team",
            plugin_options={
                "agent_team": {
                    "SELECTED_TEAM_ID": "team-1",
                    "UNDECLARED": "drop-me",
                },
                "missing_plugin": {"ANY": "drop-me"},
            },
        ),
        user=SimpleNamespace(sub="user-1", roles=[], permissions=[]),
        storage=storage,
    )

    assert storage.last_create_kwargs["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }
    assert await settings_service.storage.get(
        plugin_id="missing_plugin",
        key="ANY",
        scope="channel",
        subject_id="instance-1",
    ) is None


@pytest.mark.asyncio
async def test_create_channel_imports_legacy_team_id_to_plugin_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    settings_service = _memory_plugin_settings(monkeypatch)
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "_validate_agent_id", _async_noop)
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    await channels_route.create_channel_instance(
        ChannelType.FEISHU,
        ChannelConfigCreate(
            channel_type=ChannelType.FEISHU,
            name="Feishu",
            config={},
            agent_id="team",
            team_id="legacy-team",
        ),
        user=SimpleNamespace(sub="user-1", roles=[], permissions=[]),
        storage=storage,
    )

    assert "team_id" not in storage.last_create_kwargs
    assert storage.last_create_kwargs["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "legacy-team"}
    }
    record = await settings_service.storage.get(
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
        scope="channel",
        subject_id="instance-1",
    )
    assert record is not None
    assert record.value == "legacy-team"


@pytest.mark.asyncio
async def test_create_channel_limit_counts_configs_without_loading_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeLimitStorage(count=1)
    monkeypatch.setattr(channels_route, "RoleStorage", lambda: _FakeRoleStorage())
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    with pytest.raises(HTTPException) as exc_info:
        await channels_route.create_channel_instance(
            ChannelType.FEISHU,
            ChannelConfigCreate(
                channel_type=ChannelType.FEISHU,
                name="Feishu",
                config={},
            ),
            user=SimpleNamespace(sub="user-1", roles=["limited"]),
            storage=storage,
        )

    assert exc_info.value.status_code == 400
    assert storage.count_calls == ["user-1"]
    assert storage.list_calls == 0


@pytest.mark.asyncio
async def test_list_channel_instances_filters_in_storage() -> None:
    storage = _FakeTypedListStorage()

    response = await channels_route.list_channel_instances(
        ChannelType.FEISHU,
        user=SimpleNamespace(sub="user-1"),
        storage=storage,
    )

    assert storage.typed_calls == [("user-1", ChannelType.FEISHU)]
    assert storage.list_calls == 0
    assert [channel.id for channel in response.channels] == ["instance-1"]


@pytest.mark.asyncio
async def test_list_channel_instances_overlays_plugin_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeTypedListStorage()
    settings_service = _memory_plugin_settings(monkeypatch)
    await settings_service.set_setting(
        build_agent_team_plugin_manifest(),
        key="SELECTED_TEAM_ID",
        value="team-from-settings",
        scope="channel",
        subject_id="instance-1",
        updated_by="user-1",
    )

    response = await channels_route.list_channel_instances(
        ChannelType.FEISHU,
        user=SimpleNamespace(sub="user-1"),
        storage=storage,
    )

    assert response.channels[0].plugin_options == {
        "agent_team": {"SELECTED_TEAM_ID": "team-from-settings"}
    }


@pytest.mark.asyncio
async def test_list_user_channels_rejects_oversized_lists_before_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(channels_route, "CHANNEL_LIST_MAX_ITEMS", 2, raising=False)
    storage = _FakeListLimitStorage(count=3)

    with pytest.raises(HTTPException) as exc_info:
        await channels_route.list_user_channels(
            user=SimpleNamespace(sub="user-1"),
            storage=storage,
        )

    assert exc_info.value.status_code == 413
    assert storage.count_calls == ["user-1"]
    assert storage.list_calls == 0


@pytest.mark.asyncio
async def test_list_channel_instances_rejects_oversized_lists_before_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(channels_route, "CHANNEL_LIST_MAX_ITEMS", 2, raising=False)
    storage = _FakeListLimitStorage(count=0, typed_count=3)

    with pytest.raises(HTTPException) as exc_info:
        await channels_route.list_channel_instances(
            ChannelType.FEISHU,
            user=SimpleNamespace(sub="user-1"),
            storage=storage,
        )

    assert exc_info.value.status_code == 413
    assert storage.typed_count_calls == [("user-1", ChannelType.FEISHU)]
    assert storage.typed_list_calls == 0


@pytest.mark.asyncio
async def test_update_channel_persists_explicit_persona_preset_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "_validate_persona_preset_id", _async_noop)
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    await channels_route.update_channel_instance(
        ChannelType.FEISHU,
        "instance-1",
        ChannelConfigUpdate(config={}, persona_preset_id="persona-2"),
        user=SimpleNamespace(sub="user-1", roles=[], permissions=[]),
        storage=storage,
    )

    assert storage.last_update_kwargs["persona_preset_id"] == "persona-2"


@pytest.mark.asyncio
async def test_update_channel_stores_agent_team_selection_as_plugin_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    settings_service = _memory_plugin_settings(monkeypatch)
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    await channels_route.update_channel_instance(
        ChannelType.FEISHU,
        "instance-1",
        ChannelConfigUpdate(
            config={},
            team_id="team-2",
            plugin_options={"agent_team": {"SELECTED_TEAM_ID": "team-2"}},
        ),
        user=SimpleNamespace(sub="user-1", roles=[], permissions=[]),
        storage=storage,
    )

    assert "team_id" not in storage.last_update_kwargs
    assert storage.last_update_kwargs["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-2"}
    }
    record = await settings_service.storage.get(
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
        scope="channel",
        subject_id="instance-1",
    )
    assert record is not None
    assert record.value == "team-2"


@pytest.mark.asyncio
async def test_update_channel_imports_legacy_team_id_to_plugin_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    settings_service = _memory_plugin_settings(monkeypatch)
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    await channels_route.update_channel_instance(
        ChannelType.FEISHU,
        "instance-1",
        ChannelConfigUpdate(config={}, team_id="legacy-team"),
        user=SimpleNamespace(sub="user-1", roles=[], permissions=[]),
        storage=storage,
    )

    assert "team_id" not in storage.last_update_kwargs
    assert storage.last_update_kwargs["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "legacy-team"}
    }
    record = await settings_service.storage.get(
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
        scope="channel",
        subject_id="instance-1",
    )
    assert record is not None
    assert record.value == "legacy-team"


@pytest.mark.asyncio
async def test_update_channel_legacy_null_team_id_clears_plugin_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeTeamPluginOptionStorage()
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(channels_route, "publish_channel_config_changed", _async_noop)

    await channels_route.update_channel_instance(
        ChannelType.FEISHU,
        "instance-1",
        ChannelConfigUpdate(config={}, team_id=None),
        user=SimpleNamespace(sub="user-1", roles=[], permissions=[]),
        storage=storage,
    )

    assert "team_id" not in storage.last_update_kwargs
    assert storage.last_update_kwargs["plugin_options"] == {}


@pytest.mark.asyncio
async def test_status_reports_disconnected_without_reloading_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    manager = _FakeManager()
    manager.connected = False
    manager_class = type(
        "_StatusManagerClass",
        (),
        {"get_instance": classmethod(lambda cls: manager)},
    )
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry(manager_class))

    status = await channels_route.get_channel_instance_status(
        ChannelType.FEISHU,
        "instance-1",
        user=SimpleNamespace(sub="user-1", roles=[]),
        storage=storage,
    )

    assert manager.reload_calls == []
    assert status.connected is False


@pytest.mark.asyncio
async def test_status_uses_distributed_channel_connection_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    manager = _FakeDistributedManager()
    manager_class = type(
        "_DistributedStatusManagerClass",
        (),
        {"get_instance": classmethod(lambda cls: manager)},
    )
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry(manager_class))

    status = await channels_route.get_channel_instance_status(
        ChannelType.FEISHU,
        "instance-1",
        user=SimpleNamespace(sub="user-1", roles=[]),
        storage=storage,
    )

    assert manager.distributed_calls == [("user-1", "instance-1")]
    assert manager.reload_calls == []
    assert status.connected is True


@pytest.mark.asyncio
async def test_status_does_not_reload_disconnected_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    manager = _FakeManager()
    manager.connected = False
    manager_class = type(
        "_StatusManagerClassNoReload",
        (),
        {"get_instance": classmethod(lambda cls: manager)},
    )
    monkeypatch.setattr(channels_route, "get_registry", lambda: _FakeRegistry(manager_class))

    status = await channels_route.get_channel_instance_status(
        ChannelType.FEISHU,
        "instance-1",
        user=SimpleNamespace(sub="user-1", roles=[]),
        storage=storage,
    )

    assert manager.reload_calls == []
    assert status.connected is False


@pytest.mark.asyncio
async def test_start_feishu_registration_returns_without_polling_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = feishu_registration.FeishuRegistrationSession(id="session-1")

    async def _sleep_should_not_be_called(_delay: float) -> None:
        raise AssertionError("start_feishu_registration should return immediately")

    monkeypatch.setattr(feishu_registration, "start_registration", lambda: session)
    monkeypatch.setattr("asyncio.sleep", _sleep_should_not_be_called)

    response = await channels_route.start_feishu_registration()

    assert response["session_id"] == "session-1"
    assert response["status"] == "pending"


async def _async_noop(*args, **kwargs) -> None:
    return None
