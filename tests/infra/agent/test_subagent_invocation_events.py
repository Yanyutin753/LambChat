from unittest.mock import AsyncMock

from src.infra.agent.events.processor import AgentEventProcessor
from src.infra.writer.present import Presenter


async def test_persistent_lifecycle_preserves_invocation_identity():
    presenter = Presenter()
    presenter.emit = AsyncMock()
    processor = AgentEventProcessor(presenter)
    for phase in ("queued", "started", "completed"):
        await processor.process_event(
            {
                "event": "on_custom_event",
                "name": "lambchat_subagent",
                "data": {
                    "subagent_id": "worker",
                    "agent_call_id": "execution-1",
                    "phase": phase,
                    "status": "completed" if phase == "completed" else "running",
                },
            }
        )
    identities = [
        call.args[0]["data"].get("agent_call_id") for call in presenter.emit.call_args_list
    ]
    assert identities == ["execution-1", "execution-1", "execution-1"]


async def test_parallel_legacy_tasks_keep_distinct_invocations_on_the_same_checkpoint():
    presenter = Presenter()
    presenter.emit = AsyncMock()
    processor = AgentEventProcessor(presenter)
    for phase, call_id in (("start", "one"), ("start", "two"), ("end", "one"), ("end", "two")):
        await processor.process_event(
            {
                "event": f"on_tool_{phase}",
                "name": "task",
                "run_id": call_id,
                "metadata": {"checkpoint_ns": "tools:shared"},
                "data": {"input": {"subagent_type": "worker"}, "output": "done"},
            }
        )
    events = [call.args[0] for call in presenter.emit.call_args_list]
    assert [event["data"].get("agent_call_id") for event in events] == ["one", "two", "one", "two"]
    assert all(event["data"]["agent_id"] == events[0]["data"]["agent_id"] for event in events)


async def test_session_continuation_renews_invocation_but_resume_keeps_it(monkeypatch):
    from langchain.agents import create_agent
    from langchain_core.messages import AIMessage
    from langgraph.checkpoint.memory import InMemorySaver

    from src.infra.agent.subagent_sessions import SubagentSessions
    from tests.agents.core.test_fork_subagent_contract import _ScriptedChatModel

    dispatch = AsyncMock()
    monkeypatch.setattr("src.infra.agent.subagent_sessions.adispatch_custom_event", dispatch)
    saver = InMemorySaver()

    async def build(role, inbox):
        return create_agent(
            _ScriptedChatModel(script=[AIMessage(content="done")]),
            middleware=[inbox],
            checkpointer=saver,
        )

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    first = await sessions.start("worker", "one", call_id="assignment", config={})
    child = first["subagent_id"]
    initial = [call.args[1].get("agent_call_id") for call in dispatch.call_args_list]
    assert initial and set(initial) == {"assignment"}
    saved = sessions.snapshot()
    assert saved[child]["agent_call_id"] == "assignment"
    dispatch.reset_mock()
    await sessions.send(child, "two", config={}, message_id="continuation")
    continued = [call.args[1].get("agent_call_id") for call in dispatch.call_args_list]
    assert continued and len(set(continued)) == 1
    assert continued[0] and continued[0] != "assignment"
    sessions.records[child]["status"] = "waiting_human"
    invocation = sessions.records[child]["agent_call_id"]
    await sessions._emit(child, "waiting_human")
    sessions.records[child]["status"] = "running"
    await sessions._emit(child, "started")
    assert dispatch.call_args.args[1]["agent_call_id"] == invocation
