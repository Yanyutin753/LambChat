import asyncio
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

    async def get_session(self, session_id: str):
        return self._sessions.get(session_id)

    async def list_sessions(self, **kwargs):
        self.last_list_kwargs = kwargs
        return self._list_response


class _FakeSessionStorage:
    def __init__(self, toggled_session=None):
        self.toggled_session = toggled_session
        self.toggle_calls = []

    async def toggle_favorite(self, session_id, user_id, favorites_project_id=None):
        self.toggle_calls.append((session_id, user_id, favorites_project_id))
        return self.toggled_session


async def _fake_favorites_project_id(_user_id: str) -> str:
    return "favorites-project"


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
async def test_list_sessions_overlaps_favorites_lookup_with_ordinary_list(
    monkeypatch: pytest.MonkeyPatch,
):
    session_routes = _load_session_routes_module(monkeypatch)
    state = {"favorites_started": False, "list_started": False}
    observations = {"favorites_saw_list": False, "list_saw_favorites": False}

    class _ConcurrentManager(_FakeSessionManager):
        async def list_sessions(self, **kwargs):
            self.last_list_kwargs = kwargs
            state["list_started"] = True
            for _ in range(10):
                if state["favorites_started"]:
                    break
                await asyncio.sleep(0)
            observations["list_saw_favorites"] = state["favorites_started"]
            return [], 0

    async def _concurrent_favorites(_user_id: str) -> str:
        state["favorites_started"] = True
        for _ in range(10):
            if state["list_started"]:
                break
            await asyncio.sleep(0)
        observations["favorites_saw_list"] = state["list_started"]
        return "favorites-project"

    fake_manager = _ConcurrentManager()
    monkeypatch.setattr(session_routes, "SessionManager", lambda: fake_manager)
    monkeypatch.setattr(session_routes, "_get_favorites_project_id", _concurrent_favorites)

    await session_routes.list_sessions(
        skip=0,
        limit=20,
        status=None,
        project_id=None,
        search=None,
        favorites_only=False,
        user=SimpleNamespace(sub="user-1"),
    )

    assert observations == {"favorites_saw_list": True, "list_saw_favorites": True}
    assert fake_manager.last_list_kwargs["favorites_project_id"] is None


@pytest.mark.asyncio
async def test_get_session_overlaps_session_and_favorites_reads(
    monkeypatch: pytest.MonkeyPatch,
):
    session_routes = _load_session_routes_module(monkeypatch)
    state = {"favorites_started": False, "session_started": False}
    observations = {"favorites_saw_session": False, "session_saw_favorites": False}
    session = SimpleNamespace(
        user_id="user-1",
        metadata={},
        model_copy=lambda update: SimpleNamespace(
            user_id="user-1",
            metadata=update["metadata"],
        ),
    )

    class _ConcurrentManager(_FakeSessionManager):
        async def get_session(self, session_id: str):
            state["session_started"] = True
            for _ in range(10):
                if state["favorites_started"]:
                    break
                await asyncio.sleep(0)
            observations["session_saw_favorites"] = state["favorites_started"]
            return session

    async def _concurrent_favorites(_user_id: str) -> str:
        state["favorites_started"] = True
        for _ in range(10):
            if state["session_started"]:
                break
            await asyncio.sleep(0)
        observations["favorites_saw_session"] = state["session_started"]
        return "favorites-project"

    monkeypatch.setattr(session_routes, "SessionManager", lambda: _ConcurrentManager())
    monkeypatch.setattr(session_routes, "_get_favorites_project_id", _concurrent_favorites)

    response = await session_routes.get_session(
        "session-1",
        user=SimpleNamespace(sub="user-1"),
    )

    assert response.metadata == {}
    assert observations == {"favorites_saw_session": True, "session_saw_favorites": True}


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
