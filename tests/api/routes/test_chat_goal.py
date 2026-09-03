from __future__ import annotations

import pytest

from src.api.routes.chat import (
    CHAT_SSE_DATA_MAX_BYTES,
    _execute_agent_stream,
    _format_sse_event,
    build_conversation_config,
    resolve_goal_for_request,
    session_stream,
)
from src.infra.chat.model_facing import (
    append_required_skills_prompt,
)  # noqa: F401
from src.kernel.schemas.agent import AgentRequest, GoalSpec


def test_build_conversation_config_does_not_persist_run_scoped_goal() -> None:
    request = AgentRequest(
        message="continue",
        goal=GoalSpec(objective="finish exports", rubric="- exports work"),
    )

    config = build_conversation_config(
        run_id="run-1",
        agent_id="search",
        request=request,
        language="en",
        session_id="session-1",
    )

    assert "active_goal" not in config


def test_build_conversation_config_persists_trace_id_for_cancellation_recovery() -> None:
    request = AgentRequest(message="continue", auto_mode=True)

    config = build_conversation_config(
        run_id="run-1",
        agent_id="search",
        request=request,
        language="en",
        session_id="session-1",
        trace_id="trace-1",
    )

    assert config["trace_id"] == "trace-1"
    assert config["auto_mode"] is True


def test_resolve_goal_for_request_uses_request_goal_without_rewriting_message() -> None:
    request = AgentRequest(
        message="continue",
        goal=GoalSpec(objective="finish docs", rubric="- docs finished"),
    )

    active_goal, agent_message = resolve_goal_for_request(request, existing_metadata={})

    assert active_goal is not None
    assert active_goal.objective == "finish docs"
    assert agent_message == "continue"
    assert request.goal == active_goal
    assert "goal_command_action" not in request.context


def test_resolve_goal_for_request_does_not_restore_session_goal_for_follow_up() -> None:
    request = AgentRequest(message="keep going")

    active_goal, agent_message = resolve_goal_for_request(
        request,
        existing_metadata={
            "active_goal": {
                "objective": "finish docs",
                "rubric": "- docs are updated",
                "max_iterations": 5,
            }
        },
    )

    assert active_goal is None
    assert agent_message == "keep going"
    assert request.goal is None


def test_append_required_skills_prompt_requires_explicit_enabled_skills() -> None:
    message = append_required_skills_prompt(
        "Write the release notes.",
        ["writer", "reviewer"],
    )

    assert "Write the release notes." in message
    assert "Required skills for this message" in message
    assert "/skills/writer/SKILL.md" in message
    assert "/skills/reviewer/SKILL.md" in message
    assert "must read and follow" in message


def test_append_required_skills_prompt_keeps_message_without_explicit_skills() -> None:
    assert append_required_skills_prompt("hello", None) == "hello"
    assert append_required_skills_prompt("hello", []) == "hello"


def test_format_sse_event_adds_timestamp_without_mutating_event_data() -> None:
    event = {
        "event_type": "message:chunk",
        "data": {"content": "hello"},
        "timestamp": "2026-06-02T00:00:00Z",
        "id": "1-0",
    }

    line = _format_sse_event(event)

    assert line == (
        "event: message:chunk\n"
        'data: {"content": "hello", "_timestamp": "2026-06-02T00:00:00Z"}\n'
        "id: 1-0\n\n"
    )
    assert event["data"] == {"content": "hello"}


def test_format_sse_event_drops_oversized_payload() -> None:
    event = {
        "event_type": "message:chunk",
        "data": {"content": "x" * (CHAT_SSE_DATA_MAX_BYTES + 1)},
        "timestamp": "2026-06-02T00:00:00Z",
        "id": "1-0",
    }

    line = _format_sse_event(event)

    assert "event: error" in line
    assert "event_payload_too_large" in line
    assert len(line.encode("utf-8")) < 1024


@pytest.mark.asyncio
async def test_session_stream_offloads_sse_event_formatting(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    class _SessionManager:
        async def get_session(self, session_id):
            return type("Session", (), {"user_id": "user-1"})()

    class _DualWriter:
        async def read_from_redis(self, session_id, *, run_id):
            yield {
                "event_type": "message:chunk",
                "data": {"content": "hello"},
                "timestamp": "2026-06-02T00:00:00Z",
                "id": "1-0",
            }

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr("src.api.routes.chat.SessionManager", lambda: _SessionManager())
    monkeypatch.setattr("src.api.routes.chat.verify_session_ownership", lambda session, user: None)
    monkeypatch.setattr("src.api.routes.chat.run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _DualWriter(),
    )

    response = await session_stream(
        "session-1",
        run_id="run-1",
        user=type("User", (), {"sub": "user-1"})(),
    )
    body_iterator = response.body_iterator
    chunk = await body_iterator.__anext__()

    assert "event: message:chunk" in chunk
    assert calls == ["_format_sse_event"]


@pytest.mark.asyncio
async def test_execute_agent_stream_runs_agent_when_active_goal_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Presenter:
        run_id = "run-1"
        trace_id = "trace-1"

        def metadata(self):
            return {"event": "metadata", "data": {"run_id": self.run_id}}

    class _Agent:
        def __init__(self) -> None:
            self.stream_kwargs = None

        async def stream(self, *args, **kwargs):
            self.stream_kwargs = kwargs
            yield {"event": "message:chunk", "data": {"content": "ok"}}

    agent = _Agent()

    async def _get(_agent_id: str):
        return agent

    monkeypatch.setattr("src.api.routes.chat.AgentFactory.get", _get)

    async def _no_memory(session_id, *, exclude_run_id=None):
        return False

    monkeypatch.setattr("src.api.routes.chat._should_inject_session_memory", _no_memory)

    events = [
        event
        async for event in _execute_agent_stream(
            session_id="session-1",
            agent_id="search",
            message="hi",
            user_id="user-1",
            presenter=_Presenter(),
            active_goal={"objective": "hi", "rubric": "- say hi"},
        )
    ]

    assert [event["event"] for event in events] == [
        "goal:start",
        "message:chunk",
        "goal:end",
    ]
    assert events[0]["data"]["goal"] == {"objective": "hi", "rubric": "- say hi"}
    assert events[0]["data"]["started_at"]
    assert events[2]["data"]["goal"] == {"objective": "hi", "rubric": "- say hi"}
    assert events[2]["data"]["ended_at"]
    assert agent.stream_kwargs["active_goal"] == {"objective": "hi", "rubric": "- say hi"}


@pytest.mark.asyncio
async def test_execute_agent_stream_passes_auto_mode_to_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Agent:
        def __init__(self) -> None:
            self.stream_kwargs = None

        async def stream(self, *args, **kwargs):
            self.stream_kwargs = kwargs
            yield {"event": "message:chunk", "data": {"content": "ok"}}

    agent = _Agent()

    async def _get(_agent_id: str):
        return agent

    monkeypatch.setattr("src.api.routes.chat.AgentFactory.get", _get)

    async def _no_memory(session_id, *, exclude_run_id=None):
        return False

    monkeypatch.setattr("src.api.routes.chat._should_inject_session_memory", _no_memory)

    events = [
        event
        async for event in _execute_agent_stream(
            session_id="session-1",
            agent_id="search",
            message="hi",
            user_id="user-1",
            auto_mode=True,
        )
    ]

    assert events == [{"event": "message:chunk", "data": {"content": "ok"}}]
    assert agent.stream_kwargs["auto_mode"] is True
