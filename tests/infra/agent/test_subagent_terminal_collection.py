"""Collect finished work before synthesis, keeping streamed replies in history."""

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
from src.infra.agent.subagent_sessions import SubagentSessions
from tests.agents.core.test_fork_subagent_contract import _ScriptedChatModel


@pytest.mark.parametrize("restore", [False, True])
async def test_completed_child_is_collected_before_parent_synthesis(restore):
    saver = InMemorySaver()

    async def build(role, inbox):
        return create_agent(
            _ScriptedChatModel(script=[AIMessage(content="Checked: S2 has value 46")]),
            middleware=[inbox],
            checkpointer=saver,
        )

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    try:
        child = await sessions.start(
            "reviewer", "Check the result", call_id="review", config={}, background=True
        )
        await sessions.jobs[child["subagent_id"]]
        if restore:
            snapshot = sessions.snapshot()
            await sessions.close()
            sessions = SubagentSessions(
                session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
            )
            sessions.restore(snapshot)
        parent = _ScriptedChatModel(
            script=[AIMessage(content="S2 is recommended"), AIMessage(content="Repeated synthesis")]
        )
        graph = create_agent(
            parent, middleware=[SubagentSessionMiddleware(sessions)], checkpointer=saver
        )
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Deliver the checked result")]},
            {"configurable": {"thread_id": "parent"}},
        )
        assert len(parent.calls) == 1
        assert any("Checked: S2 has value 46" in str(m.content) for m in parent.calls[0])
        assert result["messages"][-1].content == "S2 is recommended"
        assert sessions.records[child["subagent_id"]]["collected"] is True
    finally:
        await sessions.close()
