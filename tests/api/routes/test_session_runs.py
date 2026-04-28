import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeSessionManager:
    async def get_session(self, session_id: str):
        return SimpleNamespace(user_id="user-1", session_id=session_id)


class _FakeDualWriter:
    def __init__(self, trace):
        self.trace = trace

    async def get_trace(self, trace_id: str):
        if self.trace and self.trace.get("trace_id") == trace_id:
            return self.trace
        return None

    async def list_traces(self, **kwargs):
        raise AssertionError("list_traces should not be used for trace_id lookups")


class _FakeTraceStorage:
    async def get_trace_events(self, trace_id: str):
        assert trace_id == "trace-2"
        return [{"event_type": "user:message", "data": {"content": "hello world"}}]


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
        SimpleNamespace(get_current_user_required=lambda: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.logging",
        SimpleNamespace(get_logger=lambda _name: _Logger()),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.manager",
        SimpleNamespace(SessionManager=_FakeSessionManager),
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
        SimpleNamespace(
            TokenPayload=object,
            User=object,
            UserCreate=object,
            UserInDB=object,
            UserUpdate=object,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.dual_writer",
        SimpleNamespace(DualEventWriter=object, get_dual_writer=lambda: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.trace_storage",
        SimpleNamespace(get_trace_storage=lambda: None),
    )

    path = Path(__file__).parents[3] / "src/api/routes/session.py"
    spec = importlib.util.spec_from_file_location("session_routes_under_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_get_session_runs_can_filter_by_trace_id(monkeypatch: pytest.MonkeyPatch) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    dual_writer_module = sys.modules["src.infra.session.dual_writer"]
    trace_storage_module = sys.modules["src.infra.session.trace_storage"]

    monkeypatch.setattr(session_routes, "SessionManager", lambda: _FakeSessionManager())
    monkeypatch.setattr(
        dual_writer_module,
        "get_dual_writer",
        lambda: _FakeDualWriter(
            {
                "session_id": "session-1",
                "run_id": "run-2",
                "trace_id": "trace-2",
                "agent_id": "agent-1",
                "started_at": "2026-04-25T00:00:00Z",
                "completed_at": "2026-04-25T00:01:00Z",
                "status": "completed",
                "event_count": 3,
            }
        ),
    )
    monkeypatch.setattr(
        trace_storage_module,
        "get_trace_storage",
        lambda: _FakeTraceStorage(),
    )

    response = await session_routes.get_session_runs(
        "session-1",
        trace_id="trace-2",
        user=SimpleNamespace(sub="user-1"),
    )

    assert response["count"] == 1
    assert response["runs"][0]["run_id"] == "run-2"
    assert response["runs"][0]["trace_id"] == "trace-2"
