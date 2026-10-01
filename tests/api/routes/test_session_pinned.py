"""GET /sessions?pinned_only=1 参数透传测试（镜像 test_session_favorites）。"""

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
    def __init__(self, list_response=None):
        self._list_response = list_response or ([], 0)
        self.last_list_kwargs = None

    async def list_sessions(self, **kwargs):
        self.last_list_kwargs = kwargs
        return self._list_response


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
    spec = importlib.util.spec_from_file_location("session_routes_pinned_under_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_list_sessions_passes_pinned_only_to_manager(
    monkeypatch: pytest.MonkeyPatch,
):
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
        favorites_only=False,
        pinned_only=True,
        user=SimpleNamespace(sub="user-1"),
    )

    assert fake_manager.last_list_kwargs is not None
    assert fake_manager.last_list_kwargs["pinned_only"] is True


@pytest.mark.asyncio
async def test_list_sessions_pinned_only_defaults_to_false(
    monkeypatch: pytest.MonkeyPatch,
):
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
        favorites_only=False,
        pinned_only=False,
        user=SimpleNamespace(sub="user-1"),
    )

    assert fake_manager.last_list_kwargs is not None
    assert fake_manager.last_list_kwargs["pinned_only"] is False
