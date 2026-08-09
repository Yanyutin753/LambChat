import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeSessionManager:
    async def get_session(self, session_id: str):
        return SimpleNamespace(user_id="user-1", session_id=session_id, metadata={})


class _FakeDualWriter:
    def __init__(self, trace):
        self.trace = trace

    async def get_trace(self, trace_id: str):
        if self.trace and self.trace.get("trace_id") == trace_id:
            return self.trace
        return None

    async def list_traces(self, **kwargs):
        raise AssertionError("list_traces should not be used for trace_id lookups")


class _FakeSessionEventsDualWriter:
    def __init__(self):
        self.calls = []

    async def read_session_events(self, session_id: str, event_types=None, **kwargs):
        self.calls.append(
            {
                "session_id": session_id,
                "event_types": event_types,
                **kwargs,
            }
        )
        return [
            {"event_type": "user:message", "data": {"content": "one"}},
            {"event_type": "message:chunk", "data": {"content": "two"}},
            {"event_type": "done", "data": {}},
        ]


class _FakeSessionSnapshotDualWriter:
    def __init__(self):
        self.calls = []

    async def read_session_events_snapshot(self, session_id: str, event_types=None, **kwargs):
        self.calls.append(
            {
                "session_id": session_id,
                "event_types": event_types,
                **kwargs,
            }
        )
        return SimpleNamespace(
            events=[{"event_type": "user:message", "data": {"content": "active"}}],
            history_mode="active_user_only",
            stream_run_id="run-active",
        )


class _FakeTraceStorage:
    def __init__(self):
        self.calls = []

    async def get_trace_events(self, trace_id: str):
        raise AssertionError("trace_id run summary should not load all trace events")

    async def get_first_trace_event(self, trace_id: str, event_types=None):
        self.calls.append({"trace_id": trace_id, "event_types": event_types})
        assert trace_id == "trace-2"
        return {"event_type": "user:message", "data": {"content": "hello world"}}


class _FakeListDualWriter:
    async def get_trace(self, trace_id: str):
        raise AssertionError("get_trace should not be used when listing runs")

    async def list_traces(self, **kwargs):
        return [
            {
                "session_id": "session-1",
                "run_id": "run-1",
                "trace_id": "trace-1",
                "agent_id": "agent-1",
                "started_at": "2026-04-25T00:00:00Z",
                "completed_at": "2026-04-25T00:01:00Z",
                "status": "completed",
                "event_count": 3,
            },
            {
                "session_id": "session-1",
                "run_id": "run-2",
                "trace_id": "trace-2",
                "agent_id": "agent-1",
                "started_at": "2026-04-25T00:02:00Z",
                "completed_at": "2026-04-25T00:03:00Z",
                "status": "completed",
                "event_count": 4,
            },
        ]


class _FakeRunSummaryTraceStorage:
    def __init__(self):
        self.calls = []

    async def get_trace_events(self, trace_id: str):
        raise AssertionError("get_trace_events should not be used when listing runs")

    async def list_run_summaries(self, **kwargs):
        self.calls.append(kwargs)
        return [
            {
                "run_id": "run-1",
                "trace_id": "trace-1",
                "agent_id": "agent-1",
                "started_at": "2026-04-25T00:00:00Z",
                "completed_at": "2026-04-25T00:01:00Z",
                "status": "completed",
                "event_count": 3,
                "user_message": "hello one",
            },
            {
                "run_id": "run-2",
                "trace_id": "trace-2",
                "agent_id": "agent-1",
                "started_at": "2026-04-25T00:02:00Z",
                "completed_at": "2026-04-25T00:03:00Z",
                "status": "completed",
                "event_count": 4,
                "user_message": "hello two",
            },
        ]


class _FakeRawTraceCursor:
    def __init__(self, docs):
        self.docs = docs
        self.sort_args = None
        self.limit_value = None
        self.to_list_length = None

    def sort(self, *args):
        self.sort_args = args
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def to_list(self, length=None):
        self.to_list_length = length
        return self.docs[: length or None]


class _FakeRawTraceCollection:
    def __init__(self):
        self.find_args = None
        self.cursor = _FakeRawTraceCursor(
            [
                {
                    "trace_id": "trace-1",
                    "session_id": "session-1",
                    "events": [{"event_type": "done"}],
                }
            ]
        )

    def find(self, *args):
        self.find_args = args
        return self.cursor


class _FakeRawTraceStorage:
    def __init__(self):
        self.collection = _FakeRawTraceCollection()


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
        SimpleNamespace(TokenPayload=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.session.dual_writer",
        SimpleNamespace(get_dual_writer=lambda: None),
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
    trace_storage = _FakeTraceStorage()

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
                "recommend_questions": ["下一步做什么？"],
            }
        ),
    )
    monkeypatch.setattr(
        trace_storage_module,
        "get_trace_storage",
        lambda: trace_storage,
    )

    response = await session_routes.get_session_runs(
        "session-1",
        trace_id="trace-2",
        user=SimpleNamespace(sub="user-1"),
    )

    assert response["count"] == 1
    assert response["runs"][0]["run_id"] == "run-2"
    assert response["runs"][0]["trace_id"] == "trace-2"
    assert response["runs"][0]["user_message"] == "hello world"
    assert response["runs"][0]["recommend_questions"] == ["下一步做什么？"]
    assert trace_storage.calls == [
        {"trace_id": "trace-2", "event_types": ["user:message"]},
    ]


@pytest.mark.asyncio
async def test_get_session_runs_uses_batch_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    dual_writer_module = sys.modules["src.infra.session.dual_writer"]
    trace_storage_module = sys.modules["src.infra.session.trace_storage"]
    trace_storage = _FakeRunSummaryTraceStorage()

    monkeypatch.setattr(session_routes, "SessionManager", lambda: _FakeSessionManager())
    monkeypatch.setattr(dual_writer_module, "get_dual_writer", lambda: _FakeListDualWriter())
    monkeypatch.setattr(trace_storage_module, "get_trace_storage", lambda: trace_storage)

    response = await session_routes.get_session_runs(
        "session-1",
        limit=2,
        trace_id=None,
        user=SimpleNamespace(sub="user-1"),
    )

    assert response["count"] == 2
    assert response["runs"][0]["user_message"] == "hello one"
    assert trace_storage.calls == [{"session_id": "session-1", "limit": 2, "trace_id": None}]


def test_get_session_runs_limit_is_capped_by_route_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)

    route = next(route for route in session_routes.router.routes if route.path.endswith("/runs"))
    limit_param = next(param for param in route.dependant.query_params if param.name == "limit")
    constraints = {
        type(item).__name__: getattr(item, "ge", getattr(item, "le", None))
        for item in limit_param.field_info.metadata
    }

    assert constraints["Ge"] == 1
    assert constraints["Le"] == 100


def test_get_session_events_limit_is_capped_by_route_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)

    route = next(route for route in session_routes.router.routes if route.path.endswith("/events"))
    limit_param = next(param for param in route.dependant.query_params if param.name == "limit")
    constraints = {
        type(item).__name__: getattr(item, "ge", getattr(item, "le", None))
        for item in limit_param.field_info.metadata
    }

    assert constraints["Ge"] == 1
    assert constraints["Le"] == session_routes.SESSION_EVENT_RESPONSE_LIMIT_MAX


def test_get_session_raw_traces_limits_are_capped_by_route_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)

    route = next(
        route for route in session_routes.router.routes if route.path.endswith("/raw-traces")
    )
    params = {param.name: param for param in route.dependant.query_params}
    limit_constraints = {
        type(item).__name__: getattr(item, "ge", getattr(item, "le", None))
        for item in params["limit"].field_info.metadata
    }
    events_limit_constraints = {
        type(item).__name__: getattr(item, "ge", getattr(item, "le", None))
        for item in params["events_limit"].field_info.metadata
    }

    assert limit_constraints["Ge"] == 1
    assert limit_constraints["Le"] == session_routes.SESSION_RAW_TRACE_RESPONSE_LIMIT_MAX
    assert events_limit_constraints["Ge"] == 1
    assert events_limit_constraints["Le"] == session_routes.SESSION_RAW_TRACE_EVENTS_LIMIT_MAX


@pytest.mark.asyncio
async def test_get_session_events_uses_bounded_history_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    dual_writer_module = sys.modules["src.infra.session.dual_writer"]
    dual_writer = _FakeSessionEventsDualWriter()

    monkeypatch.setattr(session_routes, "SessionManager", lambda: _FakeSessionManager())
    monkeypatch.setattr(dual_writer_module, "get_dual_writer", lambda: dual_writer)

    response = await session_routes.get_session_events(
        "session-1",
        event_types="user:message,done",
        run_id="run-1",
        exclude_run_id=None,
        limit=2,
        include_active_user_message=False,
        user=SimpleNamespace(sub="user-1"),
    )

    assert response == {
        "events": [
            {"event_type": "user:message", "data": {"content": "one"}},
            {"event_type": "message:chunk", "data": {"content": "two"}},
        ],
        "session_id": "session-1",
        "run_id": "run-1",
        "events_limited": True,
        "events_limit": 2,
    }
    assert dual_writer.calls == [
        {
            "session_id": "session-1",
            "event_types": ["user:message", "done"],
            "run_id": "run-1",
            "exclude_run_id": None,
            "completed_only": True,
            "max_events": 3,
        }
    ]


@pytest.mark.asyncio
async def test_get_session_events_opt_in_returns_race_safe_snapshot_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    dual_writer_module = sys.modules["src.infra.session.dual_writer"]
    dual_writer = _FakeSessionSnapshotDualWriter()

    class _ActiveSessionManager:
        async def get_session(self, session_id: str):
            return SimpleNamespace(
                user_id="user-1",
                session_id=session_id,
                metadata={"current_run_id": "run-active"},
            )

    monkeypatch.setattr(session_routes, "SessionManager", _ActiveSessionManager)
    monkeypatch.setattr(dual_writer_module, "get_dual_writer", lambda: dual_writer)

    response = await session_routes.get_session_events(
        "session-1",
        event_types="user:message,message:chunk,done",
        run_id=None,
        exclude_run_id=None,
        limit=None,
        include_active_user_message=True,
        user=SimpleNamespace(sub="user-1"),
    )

    assert response == {
        "events": [{"event_type": "user:message", "data": {"content": "active"}}],
        "session_id": "session-1",
        "run_id": "run-active",
        "events_limited": False,
        "events_limit": None,
        "history_mode": "active_user_only",
        "stream_run_id": "run-active",
    }
    assert dual_writer.calls == [
        {
            "session_id": "session-1",
            "event_types": ["user:message", "message:chunk", "done"],
            "run_id": None,
            "exclude_run_id": None,
            "completed_only": True,
            "max_events": None,
            "active_run_id": "run-active",
        }
    ]


@pytest.mark.asyncio
async def test_get_session_events_bounds_event_type_query_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    dual_writer_module = sys.modules["src.infra.session.dual_writer"]
    dual_writer = _FakeSessionEventsDualWriter()

    monkeypatch.setattr(session_routes, "SESSION_EVENT_TYPE_FILTER_LIMIT", 2, raising=False)
    monkeypatch.setattr(session_routes, "SessionManager", lambda: _FakeSessionManager())
    monkeypatch.setattr(dual_writer_module, "get_dual_writer", lambda: dual_writer)

    await session_routes.get_session_events(
        "session-1",
        event_types="user:message,done,thinking,done",
        run_id="run-1",
        exclude_run_id=None,
        limit=2,
        include_active_user_message=False,
        user=SimpleNamespace(sub="user-1"),
    )

    assert dual_writer.calls[0]["event_types"] == ["user:message", "done"]


@pytest.mark.asyncio
async def test_get_session_raw_traces_slices_events_in_mongo_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_routes = _load_session_routes_module(monkeypatch)
    trace_storage_module = sys.modules["src.infra.session.trace_storage"]
    trace_storage = _FakeRawTraceStorage()

    monkeypatch.setattr(session_routes, "SessionManager", lambda: _FakeSessionManager())
    monkeypatch.setattr(trace_storage_module, "get_trace_storage", lambda: trace_storage)

    response = await session_routes.get_session_raw_traces(
        "session-1",
        limit=2,
        events_limit=3,
        user=SimpleNamespace(sub="user-1"),
    )

    query, projection = trace_storage.collection.find_args
    assert query == {"session_id": "session-1"}
    assert projection == {"_id": 0, "events": {"$slice": -3}}
    assert trace_storage.collection.cursor.sort_args == ("started_at", -1)
    assert trace_storage.collection.cursor.limit_value == 2
    assert trace_storage.collection.cursor.to_list_length == 2
    assert response == {
        "session_id": "session-1",
        "traces": trace_storage.collection.cursor.docs,
        "count": 1,
        "limit": 2,
        "events_limit": 3,
    }
