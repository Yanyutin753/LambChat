import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes.chat_agent_execution import _execute_agent_stream


@pytest.fixture
def handoff_runtime(monkeypatch):
    from src.agents.team_agent import member_config
    from src.infra.session.storage import SessionStorage

    monkeypatch.setattr(
        member_config, "resolve_team_member_agent_id", AsyncMock(return_value="search")
    )
    monkeypatch.setattr("src.infra.task.manager.BackgroundTaskManager.check_interrupt", AsyncMock())
    persist = AsyncMock(return_value=True)
    monkeypatch.setattr(SessionStorage, "update_metadata_for_run", persist)
    presenter = SimpleNamespace(run_id="run-1", trace_id="trace-1", hitl_suspended=False)
    return presenter, persist


async def test_same_run_handoff_forwards_context_and_only_search_finishes(
    monkeypatch, handoff_runtime
):
    presenter, persist = handoff_runtime
    calls = []

    class Agent:
        def __init__(self, agent_id):
            self.agent_id = agent_id

        async def stream(self, message, session_id, **kwargs):
            calls.append((self.agent_id, message, session_id, kwargs))
            if self.agent_id == "quick":
                yield {
                    "event": "agent:handoff",
                    "data": {
                        "agent_id": "search",
                        "prior_usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
                        "run_started_at": 123.0,
                    },
                }
            else:
                yield {"event": "message:chunk", "data": {"content": "查证结果"}}
                yield {"event": "done", "data": {"status": "completed"}}

    monkeypatch.setattr(
        "src.api.routes.chat_agent_execution.AgentFactory.get",
        AsyncMock(side_effect=lambda key: Agent(key)),
    )
    events = [
        event
        async for event in _execute_agent_stream(
            "session-1",
            "quick",
            "按前面的预算查",
            "user-1",
            presenter=presenter,
            attachments=[{"key": "owned-file"}],
            persona_system_prompt="按原角色处理",
            agent_options={"model_id": "model-1"},
            disabled_tools=["execute"],
            disabled_skills=["secret"],
            enabled_mcp_servers=["allowed"],
            base_url="https://example.test",
        )
    ]
    assert [call[0] for call in calls] == ["quick", "search"]
    forwarded = calls[-1][3]
    assert forwarded["presenter"] is presenter
    assert calls[-1][1:3] == ("按前面的预算查", "session-1")
    assert forwarded["attachments"] == [{"key": "owned-file"}]
    assert forwarded["disabled_tools"] == ["execute"]
    assert forwarded["disabled_skills"] == ["secret"]
    assert forwarded["enabled_mcp_servers"] == ["allowed"]
    assert forwarded["persona_system_prompt"] == "按原角色处理"
    from src.infra.logging.context import TraceContext

    assert TraceContext.get_request_context().trace_id == "trace-1"
    assert forwarded["agent_options"]["_handoff_usage"]["prior_usage"]["total_tokens"] == 12
    assert [event["event"] for event in events] == ["status", "message:chunk", "done"]
    assert persist.await_args.args[:2] == ("session-1", "run-1")


async def test_superseded_run_never_starts_search(monkeypatch, handoff_runtime):
    from src.infra.task.exceptions import TaskInterruptedError

    presenter, persist = handoff_runtime
    persist.return_value = False

    async def stream(*args, **kwargs):
        yield {"event": "agent:handoff", "data": {"agent_id": "search", "prior_usage": {}}}

    agent = SimpleNamespace(stream=stream, close=AsyncMock())
    get = AsyncMock(return_value=agent)
    monkeypatch.setattr("src.api.routes.chat_agent_execution.AgentFactory.get", get)
    with pytest.raises(TaskInterruptedError):
        async for _ in _execute_agent_stream(
            "session-1", "quick", "查资料", "user-1", presenter=presenter
        ):
            pass
    assert get.await_count == 1


async def test_cancellation_closes_the_effective_search_agent(monkeypatch, handoff_runtime):
    presenter, _ = handoff_runtime
    quick_close, search_close = AsyncMock(), AsyncMock()

    async def quick_stream(*args, **kwargs):
        yield {"event": "agent:handoff", "data": {"agent_id": "search", "prior_usage": {}}}

    async def search_stream(*args, **kwargs):
        raise asyncio.CancelledError
        yield

    agents = {
        "quick": SimpleNamespace(stream=quick_stream, close=quick_close),
        "search": SimpleNamespace(stream=search_stream, close=search_close),
    }
    monkeypatch.setattr(
        "src.api.routes.chat_agent_execution.AgentFactory.get",
        AsyncMock(side_effect=agents.__getitem__),
    )
    with pytest.raises(asyncio.CancelledError):
        async for _ in _execute_agent_stream(
            "session-1", "quick", "查资料", "user-1", presenter=presenter
        ):
            pass
    search_close.assert_awaited_once()


async def test_cancel_before_handoff_prevents_search(monkeypatch, handoff_runtime):
    from src.infra.task.exceptions import TaskInterruptedError

    presenter, persist = handoff_runtime

    async def stream(*args, **kwargs):
        yield {"event": "agent:handoff", "data": {"agent_id": "search", "prior_usage": {}}}

    get = AsyncMock(return_value=SimpleNamespace(stream=stream, close=AsyncMock()))
    monkeypatch.setattr("src.api.routes.chat_agent_execution.AgentFactory.get", get)
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt",
        AsyncMock(side_effect=TaskInterruptedError("cancelled")),
    )
    with pytest.raises(TaskInterruptedError):
        async for _ in _execute_agent_stream(
            "session-1", "quick", "查资料", "user-1", presenter=presenter
        ):
            pass
    assert get.await_count == 1
    persist.assert_not_awaited()


async def test_revoked_search_access_cannot_escalate_after_quick_finishes(
    monkeypatch, handoff_runtime
):
    from src.kernel.errors import AppError, ErrorCode

    presenter, persist = handoff_runtime

    async def stream(*args, **kwargs):
        yield {"event": "agent:handoff", "data": {"agent_id": "search", "prior_usage": {}}}

    get = AsyncMock(return_value=SimpleNamespace(stream=stream, close=AsyncMock()))
    monkeypatch.setattr("src.api.routes.chat_agent_execution.AgentFactory.get", get)
    monkeypatch.setattr(
        "src.agents.team_agent.member_config.resolve_team_member_agent_id",
        AsyncMock(side_effect=["search", ValueError("team_member_agent_not_allowed")]),
    )
    with pytest.raises(AppError) as error:
        async for _ in _execute_agent_stream(
            "session-1", "quick", "查资料", "user-1", presenter=presenter
        ):
            pass
    assert error.value.error_code is ErrorCode.FORBIDDEN
    assert get.await_count == 1
    persist.assert_not_awaited()


async def test_handoff_requires_a_persistable_run_id(monkeypatch, handoff_runtime):
    from src.kernel.errors import AppError

    presenter, persist = handoff_runtime
    presenter.run_id = None

    async def quick_stream(*args, **kwargs):
        yield {"event": "agent:handoff", "data": {"agent_id": "search", "prior_usage": {}}}

    async def search_stream(*args, **kwargs):
        yield {"event": "done", "data": {}}

    agents = {
        "quick": SimpleNamespace(stream=quick_stream),
        "search": SimpleNamespace(stream=search_stream),
    }
    monkeypatch.setattr(
        "src.api.routes.chat_agent_execution.AgentFactory.get",
        AsyncMock(side_effect=agents.__getitem__),
    )
    with pytest.raises(AppError):
        async for _ in _execute_agent_stream(
            "session-1", "quick", "查资料", "user-1", presenter=presenter
        ):
            pass
    persist.assert_not_awaited()


@pytest.mark.parametrize(
    "resume", [{"hitl_resume": {}}, {"agent_options": {"_handoff_usage": {"prior_usage": {}}}}]
)
@pytest.mark.parametrize("allowed", [False, True])
async def test_resumed_search_rechecks_access_before_starting(
    monkeypatch, handoff_runtime, resume, allowed
):
    from src.kernel.errors import AppError, ErrorCode

    presenter, _ = handoff_runtime

    async def stream(*args, **kwargs):
        yield {"event": "done", "data": {"status": "completed"}}

    get = AsyncMock(return_value=SimpleNamespace(stream=stream))
    monkeypatch.setattr("src.api.routes.chat_agent_execution.AgentFactory.get", get)
    resolve = AsyncMock(return_value="search")
    if not allowed:
        resolve.side_effect = ValueError("team_member_agent_not_allowed")
    monkeypatch.setattr("src.agents.team_agent.member_config.resolve_team_member_agent_id", resolve)

    async def execute():
        return [
            event
            async for event in _execute_agent_stream(
                "session-1", "search", "", "user-1", presenter=presenter, **resume
            )
        ]

    if allowed:
        assert (await execute())[0]["event"] == "done"
        get.assert_awaited_once_with("search")
    else:
        with pytest.raises(AppError) as error:
            await execute()
        assert error.value.error_code is ErrorCode.FORBIDDEN
        get.assert_not_awaited()
    resolve.assert_awaited_once_with("search", user_id="user-1")
