import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeSessionManager:
    def __init__(self) -> None:
        self.fork_calls = []
        self.checkpoint_calls = []
        self._session = SimpleNamespace(user_id="user-1", id="session-1", metadata={})

    async def get_session(self, session_id: str):
        return self._session if session_id == "session-1" else None

    async def fork_session_from_message(self, session_id: str, message_id: str, user_id: str):
        self.fork_calls.append((session_id, message_id, user_id))
        return {
            "source_session_id": session_id,
            "session": SimpleNamespace(id="forked-1"),
        }

    async def create_message_checkpoint(
        self,
        session_id: str,
        message_id: str,
        *,
        user_id: str,
        name: str | None = None,
    ):
        self.checkpoint_calls.append((session_id, message_id, user_id, name))
        return {
            "checkpoint": {
                "id": "cp-1",
                "message_id": message_id,
                "name": name or "Checkpoint",
            }
        }

    async def fork_session_from_checkpoint(
        self,
        session_id: str,
        checkpoint_id: str,
        *,
        user_id: str,
    ):
        self.fork_calls.append((session_id, checkpoint_id, user_id, "checkpoint"))
        return {
            "source_session_id": session_id,
            "checkpoint_id": checkpoint_id,
            "session": SimpleNamespace(id="forked-from-checkpoint"),
        }


def _load_session_routes_module(monkeypatch: pytest.MonkeyPatch):
    class _Logger:
        def debug(self, *args, **kwargs):
            return None

        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    monkeypatch.setitem(
        sys.modules,
        "src.api.deps",
        SimpleNamespace(require_permissions=lambda *_permissions: lambda: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.logging",
        SimpleNamespace(get_logger=lambda _name: _Logger()),
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
        "src.infra.folder.storage",
        SimpleNamespace(get_project_storage=lambda: SimpleNamespace()),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.favorites",
        SimpleNamespace(
            is_session_favorite=lambda *_args, **_kwargs: False,
            normalize_session_metadata=lambda metadata, *_args, **_kwargs: metadata or {},
        ),
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
            SessionUpdate=object,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.kernel.schemas.user",
        SimpleNamespace(TokenPayload=object),
    )

    path = Path(__file__).parents[3] / "src/api/routes/session.py"
    spec = importlib.util.spec_from_file_location("session_routes_fork_under_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_fork_session_from_message_routes_to_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    manager = _FakeSessionManager()
    monkeypatch.setattr(session_routes, "SessionManager", lambda: manager)

    response = await session_routes.fork_session_from_message(
        "session-1",
        "message-1",
        user=SimpleNamespace(sub="user-1"),
    )

    assert manager.fork_calls == [("session-1", "message-1", "user-1")]
    assert response["session"].id == "forked-1"


@pytest.mark.asyncio
async def test_create_message_checkpoint_routes_to_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    manager = _FakeSessionManager()
    monkeypatch.setattr(session_routes, "SessionManager", lambda: manager)

    response = await session_routes.create_message_checkpoint(
        "session-1",
        "message-1",
        payload=SimpleNamespace(name="Milestone"),
        user=SimpleNamespace(sub="user-1"),
    )

    assert manager.checkpoint_calls == [("session-1", "message-1", "user-1", "Milestone")]
    assert response["checkpoint"]["id"] == "cp-1"


@pytest.mark.asyncio
async def test_fork_session_from_checkpoint_routes_to_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    manager = _FakeSessionManager()
    monkeypatch.setattr(session_routes, "SessionManager", lambda: manager)

    response = await session_routes.fork_session_from_checkpoint(
        "session-1",
        "cp-1",
        user=SimpleNamespace(sub="user-1"),
    )

    assert manager.fork_calls == [("session-1", "cp-1", "user-1", "checkpoint")]
    assert response["session"].id == "forked-from-checkpoint"
