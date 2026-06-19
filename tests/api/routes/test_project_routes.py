from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.routes import project as project_route
from src.infra.extensions import InMemoryPluginSettingsStorage, PluginSettingsService
from src.kernel.extensions.builtin_plugins import build_agent_team_plugin_manifest


class _FakeProjectStorage:
    def __init__(self, project) -> None:
        self.project = project
        self.deleted: list[tuple[str, str]] = []
        self.delete_result = True
        self.update_calls = []

    async def get_by_id(self, project_id: str, user_id: str):
        if self.project and self.project.id == project_id and self.project.user_id == user_id:
            return self.project
        return None

    async def delete(self, project_id: str, user_id: str) -> bool:
        self.deleted.append((project_id, user_id))
        return self.delete_result

    async def update(self, project_id: str, user_id: str, project_data):
        self.update_calls.append((project_id, user_id, project_data))
        if not self.project or self.project.id != project_id or self.project.user_id != user_id:
            return None
        metadata = dict(getattr(self.project, "metadata", {}) or {})
        metadata.update(getattr(project_data, "metadata", {}) or {})
        self.project = SimpleNamespace(
            **{
                **self.project.__dict__,
                "metadata": metadata,
            }
        )
        return self.project


class _FakeSessionStorage:
    def __init__(self) -> None:
        self.clear_calls: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []
        self.project_session_ids: list[str] = []

    async def clear_project_id(self, project_id: str, user_id: str) -> int:
        self.clear_calls.append((project_id, user_id))
        return 1

    async def delete_by_project(self, project_id: str, user_id: str) -> int:
        self.delete_calls.append((project_id, user_id))
        return 1

    async def list_ids_by_project(self, project_id: str, user_id: str) -> list[str]:
        self.delete_calls.append((project_id, user_id))
        return self.project_session_ids


class _FakeSessionManager:
    def __init__(self) -> None:
        self.deleted_sessions: list[str] = []
        self.delete_results: dict[str, bool] = {}

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return self.delete_results.get(session_id, True)


class _FakeChannelStorage:
    def __init__(self) -> None:
        self.clear_calls: list[tuple[str, str]] = []

    async def clear_project_id(self, project_id: str, user_id: str) -> int:
        self.clear_calls.append((project_id, user_id))
        return 1


class _FakeRevealedStorage:
    async def clear_project_id(self, project_id: str) -> int:
        return 1


class _FakeDeferredTools:
    def __init__(self) -> None:
        self.cleared_sessions: list[str] = []

    async def clear_discovered_tools(self, session_id: str) -> None:
        self.cleared_sessions.append(session_id)


@pytest.mark.asyncio
async def test_project_plugin_options_are_returned_from_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(
        id="project-1",
        user_id="user-1",
        type="custom",
        metadata={"plugin_options": {"agent_team": {"DEFAULT_TEAM_ID": "team-1"}}},
    )
    project_storage = _FakeProjectStorage(project)
    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)

    response = await project_route.get_project_plugin_options(
        "project-1",
        request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    plugin_runtime=SimpleNamespace(states=lambda: []),
                )
            )
        ),
        user=SimpleNamespace(sub="user-1"),
    )

    assert response == {
        "project_id": "project-1",
        "plugin_options": {"agent_team": {"DEFAULT_TEAM_ID": "team-1"}},
    }


@pytest.mark.asyncio
async def test_project_plugin_options_filter_undeclared_metadata_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = build_agent_team_plugin_manifest()
    project = SimpleNamespace(
        id="project-1",
        user_id="user-1",
        type="custom",
        metadata={
            "plugin_options": {
                "agent_team": {
                    "DEFAULT_TEAM_ID": "team-1",
                    "UNDECLARED": "drop-me",
                },
                "missing_plugin": {"ANY": "drop-me"},
            }
        },
    )
    project_storage = _FakeProjectStorage(project)
    fake_runtime = SimpleNamespace(
        get_state=lambda plugin_id: SimpleNamespace(manifest=manifest)
        if plugin_id == "agent_team"
        else None,
        states=lambda: [SimpleNamespace(manifest=manifest)],
    )
    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "_get_plugin_runtime", lambda _request: fake_runtime)

    response = await project_route.get_project_plugin_options(
        "project-1",
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
        user=SimpleNamespace(sub="user-1"),
    )

    assert response == {
        "project_id": "project-1",
        "plugin_options": {"agent_team": {"DEFAULT_TEAM_ID": "team-1"}},
    }


@pytest.mark.asyncio
async def test_project_plugin_options_include_project_scoped_plugin_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = build_agent_team_plugin_manifest()
    project = SimpleNamespace(id="project-1", user_id="user-1", type="custom", metadata={})
    project_storage = _FakeProjectStorage(project)
    settings_service = PluginSettingsService(storage=InMemoryPluginSettingsStorage())
    await settings_service.set_setting(
        manifest,
        key="DEFAULT_TEAM_ID",
        value="team-from-settings",
        scope="project",
        subject_id="project-1",
        updated_by="user-1",
    )
    fake_runtime = SimpleNamespace(
        states=lambda: [SimpleNamespace(manifest=manifest)],
    )
    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)

    response = await project_route.get_project_plugin_options(
        "project-1",
        request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    plugin_runtime=fake_runtime,
                    plugin_settings_service=settings_service,
                )
            )
        ),
        user=SimpleNamespace(sub="user-1"),
    )

    assert response["plugin_options"] == {
        "agent_team": {"DEFAULT_TEAM_ID": "team-from-settings"}
    }


@pytest.mark.asyncio
async def test_project_plugin_options_keep_false_and_zero_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.kernel.extensions.manifest import PluginManifest

    manifest = PluginManifest(
        id="project_flags",
        name="Project Flags",
        version="1.0.0",
        api_version="v1",
        settings=[
            {
                "key": "SHOW_BADGE",
                "type": "boolean",
                "scope": "project",
                "default": True,
            },
            {
                "key": "LIMIT",
                "type": "number",
                "scope": "project",
                "default": 5,
            },
        ],
    )
    project = SimpleNamespace(id="project-1", user_id="user-1", type="custom", metadata={})
    project_storage = _FakeProjectStorage(project)
    settings_service = PluginSettingsService(storage=InMemoryPluginSettingsStorage())
    await settings_service.set_setting(
        manifest,
        key="SHOW_BADGE",
        value=False,
        scope="project",
        subject_id="project-1",
        updated_by="user-1",
    )
    await settings_service.set_setting(
        manifest,
        key="LIMIT",
        value=0,
        scope="project",
        subject_id="project-1",
        updated_by="user-1",
    )
    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "_get_plugin_runtime", lambda _request: SimpleNamespace(
        states=lambda: [SimpleNamespace(manifest=manifest)]
    ))

    response = await project_route.get_project_plugin_options(
        "project-1",
        request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    plugin_settings_service=settings_service,
                )
            )
        ),
        user=SimpleNamespace(sub="user-1"),
    )

    assert response["plugin_options"] == {
        "project_flags": {"LIMIT": 0, "SHOW_BADGE": False}
    }


@pytest.mark.asyncio
async def test_project_plugin_option_update_keeps_disabled_plugin_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(id="project-1", user_id="user-1", type="custom", metadata={})
    project_storage = _FakeProjectStorage(project)
    manifest = build_agent_team_plugin_manifest()
    settings_service = PluginSettingsService(storage=InMemoryPluginSettingsStorage())
    fake_runtime = SimpleNamespace(
        get_state=lambda _plugin_id: SimpleNamespace(executable=False, manifest=manifest)
    )
    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "_get_plugin_runtime", lambda _request: fake_runtime)
    monkeypatch.setattr(
        project_route,
        "_get_plugin_settings_service",
        lambda _request: settings_service,
    )
    monkeypatch.setattr(
        project_route,
        "_project_option_definition",
        lambda _runtime, plugin_id, key: SimpleNamespace(type="string", options=None),
    )

    response = await project_route.update_project_plugin_option(
        "project-1",
        "agent_team",
        "DEFAULT_TEAM_ID",
        project_route.ProjectPluginOptionUpdatePayload(value="team-1"),
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
        user=SimpleNamespace(sub="user-1"),
    )

    assert response["qualified_key"] == "agent_team.DEFAULT_TEAM_ID"
    assert response["value"] == "team-1"
    assert response["plugin_enabled"] is False
    assert response["effective"] is False
    assert response["plugin_options"] == {"agent_team": {"DEFAULT_TEAM_ID": "team-1"}}
    assert project_storage.update_calls[0][2].metadata == {
        "plugin_options": {"agent_team": {"DEFAULT_TEAM_ID": "team-1"}}
    }
    stored = await settings_service.storage.get(
        plugin_id="agent_team",
        key="DEFAULT_TEAM_ID",
        scope="project",
        subject_id="project-1",
    )
    assert stored is not None
    assert stored.value == "team-1"


@pytest.mark.asyncio
async def test_project_plugin_option_update_drops_undeclared_metadata_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = build_agent_team_plugin_manifest()
    project = SimpleNamespace(
        id="project-1",
        user_id="user-1",
        type="custom",
        metadata={
            "plugin_options": {
                "agent_team": {
                    "DEFAULT_TEAM_ID": "old-team",
                    "UNDECLARED": "drop-me",
                },
                "missing_plugin": {"ANY": "drop-me"},
            }
        },
    )
    project_storage = _FakeProjectStorage(project)
    settings_service = PluginSettingsService(storage=InMemoryPluginSettingsStorage())
    fake_runtime = SimpleNamespace(
        get_state=lambda plugin_id: SimpleNamespace(executable=True, manifest=manifest)
        if plugin_id == "agent_team"
        else None,
        states=lambda: [SimpleNamespace(manifest=manifest)],
    )
    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "_get_plugin_runtime", lambda _request: fake_runtime)
    monkeypatch.setattr(
        project_route,
        "_get_plugin_settings_service",
        lambda _request: settings_service,
    )

    response = await project_route.update_project_plugin_option(
        "project-1",
        "agent_team",
        "DEFAULT_TEAM_ID",
        project_route.ProjectPluginOptionUpdatePayload(value="team-2"),
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
        user=SimpleNamespace(sub="user-1"),
    )

    expected_options = {"agent_team": {"DEFAULT_TEAM_ID": "team-2"}}
    assert response["plugin_options"] == expected_options
    assert project_storage.update_calls[0][2].metadata == {"plugin_options": expected_options}


@pytest.mark.asyncio
async def test_project_plugin_option_update_rejects_undeclared_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(id="project-1", user_id="user-1", type="custom", metadata={})
    project_storage = _FakeProjectStorage(project)
    fake_runtime = SimpleNamespace(get_state=lambda _plugin_id: SimpleNamespace(executable=True))
    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "_get_plugin_runtime", lambda _request: fake_runtime)
    monkeypatch.setattr(
        project_route,
        "_project_option_definition",
        lambda _runtime, plugin_id, key: (_ for _ in ()).throw(
            project_route.HTTPException(status_code=404, detail="not declared")
        ),
    )

    with pytest.raises(project_route.HTTPException) as exc_info:
        await project_route.update_project_plugin_option(
            "project-1",
            "agent_team",
            "MISSING",
            project_route.ProjectPluginOptionUpdatePayload(value="team-1"),
            request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
            user=SimpleNamespace(sub="user-1"),
        )

    assert exc_info.value.status_code == 404
    assert project_storage.update_calls == []


@pytest.mark.asyncio
async def test_delete_project_clears_channel_config_project_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(id="project-1", user_id="user-1", type="channel")
    project_storage = _FakeProjectStorage(project)
    session_storage = _FakeSessionStorage()
    channel_storage = _FakeChannelStorage()

    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "SessionStorage", lambda: session_storage)
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: _FakeRevealedStorage(),
    )
    monkeypatch.setattr(
        "src.infra.channel.channel_storage.ChannelStorage",
        lambda: channel_storage,
    )

    response = await project_route.delete_project(
        "project-1",
        delete_sessions=False,
        user=SimpleNamespace(sub="user-1"),
    )

    assert response == {"status": "deleted"}
    assert session_storage.clear_calls == [("project-1", "user-1")]
    assert channel_storage.clear_calls == [("project-1", "user-1")]


@pytest.mark.asyncio
async def test_delete_project_with_delete_sessions_uses_full_session_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(id="project-1", user_id="user-1", type="channel")
    project_storage = _FakeProjectStorage(project)
    session_storage = _FakeSessionStorage()
    session_storage.project_session_ids = ["session-a", "session-b"]
    session_manager = _FakeSessionManager()
    deferred_tools = _FakeDeferredTools()

    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "SessionStorage", lambda: session_storage)
    monkeypatch.setattr(project_route, "SessionManager", lambda: session_manager)
    monkeypatch.setattr(
        "src.infra.tool.deferred_manager.clear_discovered_tools",
        deferred_tools.clear_discovered_tools,
    )
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: _FakeRevealedStorage(),
    )
    monkeypatch.setattr(
        "src.infra.channel.channel_storage.ChannelStorage",
        lambda: _FakeChannelStorage(),
    )

    response = await project_route.delete_project(
        "project-1",
        delete_sessions=True,
        user=SimpleNamespace(sub="user-1"),
    )

    assert response == {"status": "deleted"}
    assert session_storage.delete_calls == [("project-1", "user-1")]
    assert session_manager.deleted_sessions == ["session-a", "session-b"]
    assert deferred_tools.cleared_sessions == ["session-a", "session-b"]


@pytest.mark.asyncio
async def test_delete_project_with_delete_sessions_stops_when_session_delete_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = SimpleNamespace(id="project-1", user_id="user-1", type="channel")
    project_storage = _FakeProjectStorage(project)
    session_storage = _FakeSessionStorage()
    session_storage.project_session_ids = ["session-a", "session-b"]
    session_manager = _FakeSessionManager()
    session_manager.delete_results = {"session-a": False}

    monkeypatch.setattr(project_route, "get_project_storage", lambda: project_storage)
    monkeypatch.setattr(project_route, "SessionStorage", lambda: session_storage)
    monkeypatch.setattr(project_route, "SessionManager", lambda: session_manager)

    with pytest.raises(project_route.HTTPException) as exc_info:
        await project_route.delete_project(
            "project-1",
            delete_sessions=True,
            user=SimpleNamespace(sub="user-1"),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "删除项目内会话失败"
    assert session_manager.deleted_sessions == ["session-a"]
    assert project_storage.deleted == []
