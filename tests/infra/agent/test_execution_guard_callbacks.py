"""Execution guards survive graph isolation without importing parent task state."""

import asyncio
from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.runnables import ensure_config
from langchain_core.runnables.config import var_child_runnable_config
from langgraph.checkpoint.memory import InMemorySaver

from src.agents.core.node_utils import isolated_nested_graph_run
from src.infra.goal_runtime import GOAL_RUN_LEASE, GoalRunMetrics, GoalUsageCallback
from src.infra.task.exceptions import TaskInterruptedError
from tests.agents.core.test_fork_subagent_contract import _ScriptedChatModel


async def test_isolated_graph_carries_guards_but_not_parent_checkpoint_or_callbacks():
    metrics = GoalRunMetrics()
    unrelated = object()
    parent = {"configurable": {"checkpoint_ns": "parent-task"}, "callbacks": [unrelated]}
    token = var_child_runnable_config.set(parent)
    try:
        async with isolated_nested_graph_run(
            presenter=SimpleNamespace(persistent_goal_metrics=metrics)
        ):
            config = ensure_config()
            assert "checkpoint_ns" not in config.get("configurable", {})
            assert unrelated not in config["callbacks"]
            assert len(config["callbacks"]) == 1
            assert isinstance(config["callbacks"][0], GoalUsageCallback)
            assert config["callbacks"][0].metrics is metrics
        assert var_child_runnable_config.get() is parent
    finally:
        var_child_runnable_config.reset(token)


async def test_isolated_graph_refuses_model_work_after_background_lease_loss():
    model = _ScriptedChatModel(script=[AIMessage(content="must not run")])
    graph = create_agent(model, tools=[])
    lease = {
        "kind": "background",
        "failure": "ownership lost",
        "expires_at": asyncio.get_running_loop().time() + 60,
    }
    token = GOAL_RUN_LEASE.set(lease)
    try:
        with pytest.raises(TaskInterruptedError, match="lease"):
            async with isolated_nested_graph_run(presenter=SimpleNamespace()):
                await graph.ainvoke({"messages": [{"role": "user", "content": "work"}]})
    finally:
        GOAL_RUN_LEASE.reset(token)
    assert not model.calls


async def test_persistent_child_keeps_goal_usage_callback_exactly_once():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    metrics = GoalRunMetrics()
    callback = GoalUsageCallback(metrics)
    model = _ScriptedChatModel(
        script=[
            AIMessage(
                content="child done",
                usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            )
        ]
    )

    async def build(role, inbox):
        return create_agent(model, tools=[], middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    try:
        result = await sessions.start(
            "reviewer", "Review", call_id="guard-child", config={"callbacks": [callback]}
        )
        assert result["status"] == "completed"
        assert metrics.model_tokens == 5
        assert len(metrics.seen_models) == 1
        assert not metrics.pending_models
    finally:
        await sessions.close()
