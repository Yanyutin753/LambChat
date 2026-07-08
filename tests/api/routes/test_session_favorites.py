import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _FakeSessionManager:
    def __init__(self, sessions=None, list_response=None):
        self._sessions = sessions or {}
        self._list_response = list_response or ([], 0)
        self.last_list_kwargs = None
        self.update_calls = []

    async def get_session(self, session_id: str):
        return self._sessions.get(session_id)

    async def list_sessions(self, **kwargs):
        self.last_list_kwargs = kwargs
        return self._list_response

    async def update_session(self, session_id: str, session_update):
        self.update_calls.append((session_id, session_update))
        session = self._sessions.get(session_id)
        if not session:
            return None
        metadata = dict(getattr(session, "metadata", {}) or {})
        metadata.update(getattr(session_update, "metadata", {}) or {})
        updated = SimpleNamespace(
            user_id=session.user_id,
            metadata=metadata,
            model_copy=lambda update: SimpleNamespace(
                user_id=session.user_id,
                metadata=update["metadata"],
            ),
        )
        self._sessions[session_id] = updated
        return updated


class _FakeSessionStorage:
    def __init__(self, toggled_session=None):
        self.toggled_session = toggled_session
        self.toggle_calls = []

    async def toggle_favorite(self, session_id, user_id, favorites_project_id=None):
        self.toggle_calls.append((session_id, user_id, favorites_project_id))
        return self.toggled_session


async def _fake_favorites_project_id(_user_id: str) -> str:
    return "favorites-project"


def _agent_team_session_manifest():
    from src.kernel.extensions.manifest import PluginManifest

    return PluginManifest(
        id="agent_team",
        name="Agent Team",
        version="1.0.0",
        api_version="v1",
        settings=[
            {
                "key": "SELECTED_TEAM_ID",
                "type": "string",
                "scope": "session",
                "default": "",
            }
        ],
        frontend={
            "session_options": [
                {
                    "key": "SELECTED_TEAM_ID",
                    "type": "string",
                    "label": "agentTeam.session.selectedTeam",
                }
            ]
        },
    )


def _load_session_routes_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(
        sys.modules,
        "src.api.deps",
        SimpleNamespace(get_current_user_required=lambda: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.logging",
        SimpleNamespace(get_logger=lambda _name: _Logger()),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.folder.storage",
        SimpleNamespace(get_project_storage=lambda: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.manager",
        SimpleNamespace(SessionManager=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.storage",
        SimpleNamespace(SessionStorage=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.favorites",
        __import__("src.infra.session.favorites", fromlist=["dummy"]),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.kernel.config",
        SimpleNamespace(
            settings=SimpleNamespace(LLM_MAX_RETRIES=3, LLM_RETRY_DELAY=1),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.kernel.extensions",
        SimpleNamespace(BUILTIN_PLUGIN_MANIFESTS=[]),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.kernel.extensions.plugin_options",
        __import__("src.kernel.extensions.plugin_options", fromlist=["dummy"]),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.kernel.extensions.runtime",
        SimpleNamespace(PluginRuntime=lambda *args, **kwargs: SimpleNamespace(get_state=lambda _plugin_id: None)),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.kernel.schemas.session",
        SimpleNamespace(
            Session=object,
            SessionCreate=object,
            SessionUpdate=lambda **kwargs: SimpleNamespace(**kwargs),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.kernel.schemas.user",
        SimpleNamespace(TokenPayload=object),
    )

    path = Path(__file__).parents[3] / "src/api/routes/session.py"
    spec = importlib.util.spec_from_file_location("session_routes_favorites_under_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_list_sessions_passes_favorites_only_to_manager(monkeypatch: pytest.MonkeyPatch):
    session_routes = _load_session_routes_module(monkeypatch)
    fake_manager = _FakeSessionManager(list_response=([], 0))
    monkeypatch.setattr(session_routes, "SessionManager", lambda: fake_manager)
    monkeypatch.setattr(
        session_routes,
        "_get_favorites_project_id",
        _fake_favorites_project_id,
    )

    await session_routes.list_sessions(
        skip=0,
        limit=20,
        status=None,
        project_id=None,
        search=None,
        favorites_only=True,
        user=SimpleNamespace(sub="user-1"),
    )

    assert fake_manager.last_list_kwargs is not None
    assert fake_manager.last_list_kwargs["favorites_only"] is True
    assert fake_manager.last_list_kwargs["favorites_project_id"] == "favorites-project"


@pytest.mark.asyncio
async def test_toggle_session_favorite_returns_normalized_state(monkeypatch: pytest.MonkeyPatch):
    session_routes = _load_session_routes_module(monkeypatch)
    base_session = SimpleNamespace(
        user_id="user-1",
        metadata={"project_id": "project-1"},
        model_copy=lambda update: SimpleNamespace(
            user_id="user-1",
            metadata=update["metadata"],
        ),
    )
    toggled_session = SimpleNamespace(
        user_id="user-1",
        metadata={"project_id": "project-1", "is_favorite": True},
        model_copy=lambda update: SimpleNamespace(
            user_id="user-1",
            metadata=update["metadata"],
        ),
    )
    fake_manager = _FakeSessionManager(sessions={"session-1": base_session})
    fake_storage = _FakeSessionStorage(toggled_session=toggled_session)

    monkeypatch.setattr(session_routes, "SessionManager", lambda: fake_manager)
    monkeypatch.setattr(session_routes, "SessionStorage", lambda: fake_storage)
    monkeypatch.setattr(
        session_routes,
        "_get_favorites_project_id",
        _fake_favorites_project_id,
    )

    response = await session_routes.toggle_session_favorite(
        "session-1",
        user=SimpleNamespace(sub="user-1"),
    )

    assert fake_storage.toggle_calls == [("session-1", "user-1", "favorites-project")]
    assert response["is_favorite"] is True
    assert response["session"].metadata["is_favorite"] is True


@pytest.mark.asyncio
async def test_session_plugin_options_are_returned_from_metadata(monkeypatch: pytest.MonkeyPatch):
    session_routes = _load_session_routes_module(monkeypatch)
    session = SimpleNamespace(
        user_id="user-1",
        metadata={"plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-1"}}},
    )
    fake_manager = _FakeSessionManager(sessions={"session-1": session})
    monkeypatch.setattr(session_routes, "SessionManager", lambda: fake_manager)
    monkeypatch.setattr(
        session_routes,
        "_get_plugin_runtime",
        lambda _request: SimpleNamespace(states=lambda: []),
    )

    response = await session_routes.get_session_plugin_options(
        "session-1",
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
        "session_id": "session-1",
        "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-1"}},
        "storage": "session_metadata",
        "source": "session_metadata.plugin_options+plugin_settings",
    }


@pytest.mark.asyncio
async def test_session_plugin_options_include_session_scoped_plugin_settings(
    monkeypatch: pytest.MonkeyPatch,
):
    session_routes = _load_session_routes_module(monkeypatch)
    from src.infra.extensions import InMemoryPluginSettingsStorage, PluginSettingsService

    manifest = _agent_team_session_manifest()
    session = SimpleNamespace(user_id="user-1", metadata={})
    fake_manager = _FakeSessionManager(sessions={"session-1": session})
    settings_service = PluginSettingsService(storage=InMemoryPluginSettingsStorage())
    await settings_service.set_setting(
        manifest,
        key="SELECTED_TEAM_ID",
        value="team-from-settings",
        scope="session",
        subject_id="session-1",
        updated_by="user-1",
    )
    fake_runtime = SimpleNamespace(
        states=lambda: [SimpleNamespace(manifest=manifest)],
    )
    monkeypatch.setattr(session_routes, "SessionManager", lambda: fake_manager)
    monkeypatch.setattr(session_routes, "_get_plugin_runtime", lambda _request: fake_runtime)

    response = await session_routes.get_session_plugin_options(
        "session-1",
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
        "agent_team": {"SELECTED_TEAM_ID": "team-from-settings"}
    }


@pytest.mark.asyncio
async def test_session_plugin_option_update_keeps_disabled_plugin_value(monkeypatch: pytest.MonkeyPatch):
    session_routes = _load_session_routes_module(monkeypatch)
    from src.infra.extensions import InMemoryPluginSettingsStorage, PluginSettingsService

    session = SimpleNamespace(user_id="user-1", metadata={})
    fake_manager = _FakeSessionManager(sessions={"session-1": session})
    manifest = _agent_team_session_manifest()
    settings_service = PluginSettingsService(storage=InMemoryPluginSettingsStorage())
    fake_runtime = SimpleNamespace(
        get_state=lambda plugin_id: SimpleNamespace(executable=False, manifest=manifest),
    )
    monkeypatch.setattr(session_routes, "SessionManager", lambda: fake_manager)
    monkeypatch.setattr(session_routes, "_get_plugin_runtime", lambda _request: fake_runtime)
    monkeypatch.setattr(
        session_routes,
        "_session_option_definition",
        lambda _runtime, plugin_id, key: SimpleNamespace(type="string", options=None),
    )
    monkeypatch.setattr(
        session_routes,
        "_get_plugin_settings_service",
        lambda _request: settings_service,
    )

    response = await session_routes.update_session_plugin_option(
        "session-1",
        "agent_team",
        "SELECTED_TEAM_ID",
        session_routes.SessionPluginOptionUpdatePayload(value="team-1"),
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
        user=SimpleNamespace(sub="user-1"),
    )

    assert response["qualified_key"] == "agent_team.SELECTED_TEAM_ID"
    assert response["value"] == "team-1"
    assert response["plugin_enabled"] is False
    assert response["effective"] is False
    assert response["plugin_options"] == {"agent_team": {"SELECTED_TEAM_ID": "team-1"}}
    assert response["storage"] == "session_metadata"
    assert response["source"] == "session_metadata.plugin_options+plugin_settings"
    assert fake_manager.update_calls[0][1].metadata == {
        "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-1"}},
    }
    stored = await settings_service.storage.get(
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
        scope="session",
        subject_id="session-1",
    )
    assert stored is not None
    assert stored.value == "team-1"
