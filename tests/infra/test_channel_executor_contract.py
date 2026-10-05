"""Channel executors accept the full invocation contract of TaskExecutor.run_task."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.infra.channel.chat_handler import execute_chat_agent
from src.infra.channel.feishu import handler as feishu_handler
from src.infra.channel.weixin import handler as weixin_handler


@pytest.fixture
def executor_kwargs():
    # TaskExecutor.run_task supplies all of these even when their values are None.
    return {
        "presenter": SimpleNamespace(run_id="run-1"),
        "disabled_tools": ["blocked-tool"],
        "agent_options": {"model_id": "model-1", "sandbox_env": {"LANG": "en_US.UTF-8"}},
        "attachments": [{"name": "notes.txt"}],
        "disabled_skills": ["blocked-skill"],
        "enabled_skills": ["planning"],
        "persona_system_prompt": "Persona instructions",
        "disabled_mcp_tools": ["mcp.blocked"],
        "enabled_mcp_servers": ["mcp-1"],
        "recommendation_input": "original input",
        "team_id": "team-1",
        "active_goal": None,
        "auto_mode": True,
        "hitl_resume": {"approval_id": "approval-1"},
        "base_url": "https://lambchat.example",
    }


@pytest.fixture
def agent(monkeypatch):
    async def stream(*args, **kwargs):
        yield {"event": "message:chunk", "data": {"content": "reply"}}

    agent = SimpleNamespace(stream=Mock(side_effect=stream))
    monkeypatch.setattr("src.agents.core.base.AgentFactory.get", AsyncMock(return_value=agent))
    return agent


async def assert_executor_contract(executor, agent, executor_kwargs):
    events = [
        event
        async for event in executor("session-1", "agent-1", "hello", "owner-1", **executor_kwargs)
    ]
    assert events == [{"event": "message:chunk", "data": {"content": "reply"}}]
    agent.stream.assert_called_once()
    assert agent.stream.call_args.args == ("hello", "session-1")
    forwarded = agent.stream.call_args.kwargs
    assert forwarded["user_id"] == "owner-1"
    for key, value in executor_kwargs.items():
        assert forwarded[key] == value, f"channel executor did not forward {key}"


@pytest.mark.parametrize(
    "executor",
    [execute_chat_agent, feishu_handler.execute_feishu_agent, weixin_handler.execute_weixin_agent],
    ids=["generic", "feishu", "weixin"],
)
async def test_exported_executor_accepts_and_forwards_task_runtime_options(
    executor, agent, executor_kwargs
):
    await assert_executor_contract(executor, agent, executor_kwargs)


@pytest.mark.parametrize("provider", ["feishu", "weixin"])
async def test_submitted_executor_accepts_and_forwards_task_runtime_options(
    provider, monkeypatch, agent, executor_kwargs
):
    module = feishu_handler if provider == "feishu" else weixin_handler
    captured = {}

    class SubmissionCaptured(BaseException):
        """Stop after capturing submission, before real persistence or delivery."""

    async def submit(**kwargs):
        captured.update(kwargs)
        raise SubmissionCaptured

    monkeypatch.setattr(
        "src.infra.task.manager.get_task_manager", lambda: SimpleNamespace(submit=submit)
    )
    monkeypatch.setattr(module, f"_get_{provider}_session_id", AsyncMock(return_value="session-1"))
    manager = SimpleNamespace(send_message=AsyncMock())
    create_handler = getattr(module, f"create_{provider}_message_handler")
    handler = create_handler(manager, "agent-1")
    with pytest.raises(SubmissionCaptured):
        await handler("owner-1", "sender-1", "chat-1", "hello", {})

    await assert_executor_contract(captured["executor"], agent, executor_kwargs)
