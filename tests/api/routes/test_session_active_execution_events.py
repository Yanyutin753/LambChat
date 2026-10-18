"""Active scheduled catch-up uses the real route and trace status/run filters."""

import sys

import httpx
import pytest
from fastapi import FastAPI

from src.api.error_handlers import register_error_handlers
from tests.api.routes.test_session_events_contract import (
    _load_contract_routes_module,
    _real_dual_writer_with,
    _rich_traces,
)


def _active_events_app(monkeypatch, *, owner="user-1", status="running"):
    routes = _load_contract_routes_module(monkeypatch)
    traces = _rich_traces()
    active = traces[-1]
    active["status"] = status
    active["events"] = [
        {"event_type": "thinking", "data": {"content": "Checking"}, "seq": 1},
        {"event_type": "tool:start", "data": {"tool": "execute"}, "seq": 2},
    ]
    # Even an identical run ID in another session must stay inaccessible.
    traces.append({**active, "trace_id": "foreign", "session_id": "other-session"})
    writer = _real_dual_writer_with(traces)
    monkeypatch.setattr(
        sys.modules["src.infra.session.dual_writer"], "get_dual_writer", lambda: writer
    )
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/sessions")
    app.dependency_overrides[routes.get_current_user_required] = lambda: type(
        "User", (), {"sub": owner}
    )()
    register_error_handlers(app)
    return app


@pytest.mark.parametrize("trace_limit", [None, 20])
@pytest.mark.parametrize("status", ["running", "completed"])
async def test_active_execution_catchup_is_opt_in_and_exact_run_scoped(
    monkeypatch, trace_limit, status
):
    app = _active_events_app(monkeypatch, status=status)
    params = {"run_id": "run-active"}
    if trace_limit is not None:
        params["trace_limit"] = trace_limit
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        history = await client.get("/api/sessions/session-1/events", params=params)
        catchup = await client.get(
            "/api/sessions/session-1/events", params={**params, "include_active_events": "true"}
        )
    assert history.status_code == catchup.status_code == 200
    if status == "running":
        assert history.json()["events"] == []
    events = catchup.json()["events"]
    assert [event["event_type"] for event in events] == ["thinking", "tool:start"]
    assert {event["run_id"] for event in events} == {"run-active"}
    assert {event["trace_id"] for event in events} == {"trace-26"}


@pytest.mark.parametrize(
    "params",
    [
        {"include_active_events": "true"},
        {"include_active_events": "true", "run_id": "run-active", "exclude_run_id": "other"},
    ],
)
async def test_active_execution_catchup_requires_an_unambiguous_run(monkeypatch, params):
    app = _active_events_app(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/sessions/session-1/events", params=params)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "bad_request"


async def test_active_execution_catchup_rechecks_session_ownership(monkeypatch):
    app = _active_events_app(monkeypatch, owner="other-user")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/sessions/session-1/events",
            params={
                "run_id": "run-active",
                "include_active_events": "true",
            },
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "session_access_denied"
