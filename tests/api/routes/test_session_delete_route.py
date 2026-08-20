"""DELETE /sessions/{session_id} 路由的 SessionError 映射测试。"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.kernel.exceptions import SessionError


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


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
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.dual_writer",
        SimpleNamespace(get_dual_writer=lambda: None, DualEventWriter=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.trace_storage",
        SimpleNamespace(get_trace_storage=lambda: None),
    )
    history_path = Path(__file__).parents[3] / "src/infra/session/history_compaction.py"
    history_spec = importlib.util.spec_from_file_location(
        "session_history_compaction_under_test",
        history_path,
    )
    assert history_spec is not None
    history_module = importlib.util.module_from_spec(history_spec)
    assert history_spec.loader is not None
    history_spec.loader.exec_module(history_module)
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.history_compaction",
        history_module,
    )

    path = Path(__file__).parents[3] / "src/api/routes/session.py"
    spec = importlib.util.spec_from_file_location("session_routes_under_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _ManagerRaisingOnDelete:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def get_session(self, session_id: str):
        return SimpleNamespace(user_id="user-1", session_id=session_id, metadata={})

    async def delete_session(self, _session_id: str) -> bool:
        raise self._error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    [
        ("session_delete_in_progress", 409),
        ("session_delete_has_trace_survivors", 500),
        ("session_delete_fence_unavailable", 500),
    ],
)
async def test_delete_session_maps_session_error_to_status_code(
    monkeypatch: pytest.MonkeyPatch, error_code: str, expected_status: int
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    manager = _ManagerRaisingOnDelete(SessionError(error_code))
    monkeypatch.setattr(session_routes, "SessionManager", lambda: manager)
    user = SimpleNamespace(sub="user-1", role="user")

    with pytest.raises(HTTPException) as exc_info:
        await session_routes.delete_session("session-1", user=user)

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == error_code


@pytest.mark.asyncio
async def test_delete_session_returns_deleted_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)

    class _Manager:
        async def get_session(self, session_id: str):
            return SimpleNamespace(user_id="user-1", session_id=session_id, metadata={})

        async def delete_session(self, _session_id: str) -> bool:
            return True

    manager = _Manager()
    monkeypatch.setattr(session_routes, "SessionManager", lambda: manager)
    user = SimpleNamespace(sub="user-1", role="user")

    result = await session_routes.delete_session("session-1", user=user)

    assert result == {"status": "deleted"}
