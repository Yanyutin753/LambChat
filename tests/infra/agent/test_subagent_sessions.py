"""Persistent subagent conversations use one writer and survive parent turns."""

import asyncio

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from tests.agents.core.test_fork_subagent_contract import _ScriptedChatModel


async def test_child_quota_failure_reaches_wait_without_losing_checkpoint_or_failing_job():
    from src.infra.agent.subagent_sessions import SubagentSessions
    from src.kernel.errors import AppError, ErrorCode

    saver = InMemorySaver()
    denied = True

    class DeniedModel(_ScriptedChatModel):
        async def _agenerate(self, messages, **kwargs):
            if denied:
                raise AppError(ErrorCode.USAGE_QUOTA_EXCEEDED, args={"reset_at": "tomorrow"})
            return await super()._agenerate(messages, **kwargs)

    async def build(role, inbox):
        return create_agent(
            DeniedModel(script=[AIMessage(content="unused")]),
            middleware=[inbox],
            checkpointer=saver,
        )

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    started = await sessions.start(
        "reviewer", "Keep this assignment", call_id="quota", config={}, background=True
    )
    child_id = started["subagent_id"]
    await sessions.jobs[child_id]
    assert sessions.result(child_id)["error_code"] == "usage_quota_exceeded"
    with pytest.raises(AppError) as rejected:
        await sessions.wait(child_id, config={})
    assert rejected.value.error_code is ErrorCode.USAGE_QUOTA_EXCEEDED
    assert rejected.value.args_data == {"reset_at": "tomorrow"}
    snapshot = await sessions.graphs[child_id].aget_state(sessions.configs[child_id])
    assert snapshot.values["messages"][0].content == "Keep this assignment"
    assert snapshot.next
    denied = False
    continued = await sessions.send(child_id, "Continue after reset", config={})
    assert continued["status"] == "completed"
    assert "error_code" not in continued


@pytest.mark.parametrize("background", [False, True])
async def test_parent_propagates_child_quota_through_tools_and_final_collection(background):
    from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
    from src.infra.agent.subagent_sessions import SubagentSessions
    from src.kernel.errors import AppError, ErrorCode

    saver = InMemorySaver()

    class DeniedModel(_ScriptedChatModel):
        async def _agenerate(self, messages, **kwargs):
            raise AppError(ErrorCode.USAGE_QUOTA_EXCEEDED)

    async def build(role, inbox):
        return create_agent(
            DeniedModel(script=[AIMessage(content="unused")]),
            middleware=[inbox],
            checkpointer=saver,
        )

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    parent = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Review",
                            "subagent_type": "reviewer",
                            "background": background,
                        },
                        "id": "quota-task",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Do not treat the child refusal as success"),
        ]
    )
    graph = create_agent(
        parent, middleware=[SubagentSessionMiddleware(sessions)], checkpointer=saver
    )
    try:
        with pytest.raises(AppError) as rejected:
            await graph.ainvoke(
                {"messages": [HumanMessage(content="Review")]},
                {"configurable": {"thread_id": "parent"}},
            )
        assert rejected.value.error_code is ErrorCode.USAGE_QUOTA_EXCEEDED
        assert all(job.done() and job.exception() is None for job in sessions.jobs.values())
    finally:
        await sessions.close()


async def test_child_can_message_parent_and_wake_wait_without_finishing():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    release = asyncio.Event()

    @tool
    async def hold_for_parent() -> str:
        """Wait for the parent's response in the test."""
        await release.wait()
        return "Continue"

    child = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "send_parent_message",
                        "args": {"message": "Need scope clarification"},
                        "id": "parent-note-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "hold_for_parent", "args": {}, "id": "hold-1", "type": "tool_call"}
                ],
            ),
            AIMessage(content="Child finished"),
        ]
    )

    async def build(role, inbox):
        return create_agent(child, tools=[hold_for_parent], middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    try:
        started = await sessions.start(
            "reviewer", "Review", call_id="task-1", config={}, background=True
        )
        received = await asyncio.wait_for(sessions.wait(started["subagent_id"], config={}), 2)
        assert received["status"] == "running"
        assert received["messages_pending"] is True
        messages = sessions.drain_parent([])
        assert len(messages) == 1
        assert "Need scope clarification" in messages[0].content
        assert messages[0].additional_kwargs["lambchat_subagent_id"] == started["subagent_id"]
        release.set()
        final = await asyncio.wait_for(sessions.wait(started["subagent_id"], config={}), 2)
        assert final["status"] == "completed"
    finally:
        release.set()
        await sessions.close()


async def test_parent_mailbox_is_scoped_deduplicated_and_retained_after_rebuild():
    from src.infra.agent.subagent_sessions import SubagentSessions

    async def build(*args):
        raise AssertionError("Messages must not load or start an idle agent")

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=InMemorySaver()
    )
    sessions.records["child"] = {
        "subagent_type": "reviewer",
        "status": "completed",
        "collected": True,
    }
    for _ in range(2):
        receipt = await sessions.send_parent(
            "child", "Saved progress", message_id="note-1", config={}
        )
        assert receipt["status"] == "queued"
    rejected = await sessions.send_parent(
        "foreign-child", "Wrong parent", message_id="bad", config={}
    )
    assert rejected["status"] == "error"
    rebuilt = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=sessions.checkpointer
    )
    rebuilt.restore(sessions.snapshot())
    delivered = rebuilt.drain_parent([])
    assert len(delivered) == 1
    assert delivered[0].id == "note-1"
    assert rebuilt.drain_parent(delivered) == []
    assert sessions.jobs == rebuilt.jobs == {}
    restored = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=sessions.checkpointer
    )
    restored.restore(rebuilt.snapshot())
    assert restored.drain_parent(delivered) == []


async def test_two_children_with_the_same_provider_tool_id_deliver_both_messages():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()

    async def build(role, inbox):
        child = _ScriptedChatModel(
            script=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "send_parent_message",
                            "args": {"message": role},
                            "id": "shared-provider-id",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Done"),
            ]
        )
        return create_agent(child, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    try:
        for role in ("reviewer", "researcher"):
            await sessions.start(role, "Review", call_id=role, config={}, background=True)
        await asyncio.gather(*sessions.jobs.values())
        messages = sessions.drain_parent([])
        assert len(messages) == 2
        assert len({message.id for message in messages}) == 2
        assert {message.additional_kwargs["lambchat_subagent_id"] for message in messages} == set(
            sessions.records
        )
    finally:
        await sessions.close()


async def test_parent_receives_child_mail_at_its_next_model_call():
    from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
    from src.infra.agent.subagent_sessions import SubagentSessions

    async def build(*args):
        raise AssertionError("A queued message must not start a child")

    saver = InMemorySaver()
    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    sessions.records["child"] = {
        "subagent_type": "reviewer",
        "status": "completed",
        "collected": True,
    }
    await sessions.send_parent("child", "Only permissions", message_id="note-1", config={})
    parent = _ScriptedChatModel(script=[AIMessage(content="Message received")])
    graph = create_agent(
        parent, middleware=[SubagentSessionMiddleware(sessions)], checkpointer=saver
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Continue")]}, {"configurable": {"thread_id": "parent"}}
    )
    assert result["messages"][-1].content == "Message received"
    incoming = next(message for message in parent.calls[0] if message.id == "note-1")
    assert "Only permissions" in incoming.content
    assert incoming.additional_kwargs["lambchat_subagent_id"] == "child"


async def test_child_mail_arriving_during_parent_final_answer_gets_processed():
    from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
    from src.infra.agent.subagent_sessions import SubagentSessions

    async def build(*args):
        raise AssertionError("No child execution needed")

    saver = InMemorySaver()
    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    sessions.records["child"] = {
        "subagent_type": "reviewer",
        "status": "completed",
        "collected": True,
    }

    class ArrivingModel(_ScriptedChatModel):
        async def _agenerate(self, messages, **kwargs):
            if self.i == 0:
                await sessions.send_parent("child", "Late progress", message_id="late-1", config={})
            return self._generate(messages)

    parent = ArrivingModel(
        script=[AIMessage(content="Outdated answer"), AIMessage(content="Updated answer")]
    )
    graph = create_agent(
        parent, middleware=[SubagentSessionMiddleware(sessions)], checkpointer=saver
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Continue")]}, {"configurable": {"thread_id": "parent"}}
    )
    assert result["messages"][-1].content == "Updated answer"
    assert not any(message.content == "Outdated answer" for message in result["messages"])
    assert any("Late progress" in str(message.content) for message in parent.calls[-1])


async def test_completed_subagent_continues_history_after_coordinator_rebuild():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    model = _ScriptedChatModel(script=[AIMessage(content="first"), AIMessage(content="second")])

    async def build(role, inbox):
        assert role == "reviewer"
        return create_agent(model, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    result = await sessions.start("reviewer", "Remember TOKEN_7331", call_id="call_1", config={})
    rebuilt = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    rebuilt.restore(sessions.records)
    continued = await rebuilt.send(result["subagent_id"], "Recall the token", config={})

    assert continued["subagent_id"] == result["subagent_id"]
    assert continued["status"] == "completed"
    assert [m.content for m in model.calls[-1] if isinstance(m, HumanMessage)] == [
        "Remember TOKEN_7331",
        "Recall the token",
    ]


async def test_running_message_arriving_during_final_generation_is_consumed():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    entered, release = asyncio.Event(), asyncio.Event()

    class GatedModel(_ScriptedChatModel):
        async def _agenerate(self, messages, **kwargs):
            if self.i == 0:
                entered.set()
                await release.wait()
            return self._generate(messages)

    model = GatedModel(script=[AIMessage(content="initial"), AIMessage(content="revised")])

    async def build(role, inbox):
        return create_agent(model, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    result = await sessions.start(
        "reviewer", "First task", call_id="call_1", config={}, background=True
    )
    await asyncio.wait_for(entered.wait(), 3)
    sent = await sessions.send(result["subagent_id"], "Also use JSON", config={})
    assert sent["status"] == "running"
    release.set()
    final = await sessions.wait(result["subagent_id"], config={})
    assert final["status"] == "completed"
    assert model.i == 2
    assert any(m.content == "Also use JSON" for m in model.calls[-1])


async def test_unknown_subagent_cannot_open_another_sessions_checkpoint():
    from src.infra.agent.subagent_sessions import SubagentSessions

    async def build(*args):
        raise AssertionError("unknown IDs must not load graphs")

    sessions = SubagentSessions(
        session_id="other", user_id="owner", build_graph=build, checkpointer=InMemorySaver()
    )
    result = await sessions.send("subagent-from-another-chat", "continue", config={})
    assert result["status"] == "error"


async def test_parent_cancellation_stops_background_subagent():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    entered, cancelled = asyncio.Event(), asyncio.Event()

    @tool
    async def hold() -> str:
        """Wait for a test signal."""
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return "done"

    model = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[{"name": "hold", "args": {}, "id": "hold-1", "type": "tool_call"}],
            )
        ]
    )

    async def build(role, inbox):
        return create_agent(model, tools=[hold], middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    await sessions.start("reviewer", "work", call_id="call_1", config={}, background=True)
    await asyncio.wait_for(entered.wait(), 3)
    await sessions.close()
    assert cancelled.is_set()


async def test_child_approval_resumes_through_parent_with_same_history():
    from langgraph.types import Command, interrupt

    from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()

    @tool
    def approve() -> str:
        """Ask permission before proceeding."""
        return str(interrupt({"type": "test_approval", "question": "Proceed?"}))

    child = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "approve", "args": {}, "id": "approval-1", "type": "tool_call"}
                ],
            ),
            AIMessage(content="approved child done"),
        ]
    )
    parent = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {"subagent_type": "reviewer", "description": "work"},
                        "id": "task-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="parent done"),
        ]
    )

    async def build(role, inbox):
        return create_agent(child, tools=[approve], middleware=[inbox], checkpointer=saver)

    def main():
        sessions = SubagentSessions(
            session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
        )
        return create_agent(
            parent, middleware=[SubagentSessionMiddleware(sessions)], checkpointer=saver
        )

    config = {"configurable": {"thread_id": "parent"}}
    first = await main().ainvoke({"messages": [HumanMessage(content="go")]}, config)
    assert first["__interrupt__"]
    second = await main().ainvoke(Command(resume="yes"), config)
    assert second["messages"][-1].content == "parent done"
    assert child.i == 2
    assert sum(isinstance(m, HumanMessage) for m in child.calls[-1]) == 1


async def test_wait_recovers_completed_child_from_stale_parent_metadata():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    child = _ScriptedChatModel(script=[AIMessage(content="finished result")])

    async def build(role, inbox):
        return create_agent(child, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    started = await sessions.start("reviewer", "work", call_id="task-1", config={}, background=True)
    stale = sessions.snapshot()
    await sessions.wait(started["subagent_id"], config={})
    restored = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    restored.restore(stale)
    result = await restored.wait(started["subagent_id"], config={})
    assert result["status"] == "completed"
    assert result["result"] == "finished result"
    assert child.i == 1


async def test_completed_background_continuation_requires_collection_again():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    model = _ScriptedChatModel(script=[AIMessage(content="first"), AIMessage(content="second")])

    async def build(role, inbox):
        return create_agent(model, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    first = await sessions.start("reviewer", "work", call_id="task-1", config={})
    sessions.records[first["subagent_id"]]["collected"] = True
    await sessions.send(first["subagent_id"], "more work", config={}, background=True)
    assert not sessions.records[first["subagent_id"]].get("collected")
    await sessions.close()


async def test_forked_session_inherits_parent_history_without_copying_other_roles():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    model = _ScriptedChatModel(script=[AIMessage(content="done")])

    async def build(role, inbox):
        return create_agent(model, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent",
        user_id="owner",
        build_graph=build,
        checkpointer=saver,
        fork_types=frozenset({"context-worker"}),
    )
    await sessions.start(
        "context-worker",
        "continue",
        call_id="fork-1",
        config={},
        initial_state={"messages": [HumanMessage(content="FORK_TOKEN_7331")]},
    )
    assert any(m.content == "FORK_TOKEN_7331" for m in model.calls[-1])


async def test_sdk_main_graph_exposes_background_task_schema():
    from deepagents import create_deep_agent

    from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    bound_schemas = []

    class SchemaRecordingModel(_ScriptedChatModel):
        def bind_tools(self, tools, **kwargs):
            bound_schemas.extend(
                t.tool_call_schema.model_json_schema() for t in tools if t.name == "task"
            )
            return self

    model = SchemaRecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "work",
                            "subagent_type": "reviewer",
                            "background": True,
                        },
                        "id": "task-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    child = _ScriptedChatModel(script=[AIMessage(content="child done")])

    async def build(role, inbox):
        return create_agent(child, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    middleware = SubagentSessionMiddleware(sessions)
    graph = create_deep_agent(
        model,
        subagents=[{"name": "reviewer", "description": "review"}],
        middleware=[middleware],
        checkpointer=saver,
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")]}, {"configurable": {"thread_id": "parent"}}
    )
    assert child.i == 1
    assert result["messages"][-1].content == "done"
    assert bound_schemas and all("background" in s["properties"] for s in bound_schemas)


async def test_unstarted_background_task_recovers_original_instructions():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    child = _ScriptedChatModel(script=[AIMessage(content="done")])

    async def build(role, inbox):
        return create_agent(child, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    started = await sessions.start(
        "reviewer", "ORIGINAL_TOKEN_7331", call_id="task-1", config={}, background=True
    )
    saved = sessions.snapshot()
    await sessions.close()
    restored = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    restored.restore(saved)
    result = await restored.wait(started["subagent_id"], config={})
    assert result["status"] == "completed"
    assert child.i == 1
    assert any(m.content == "ORIGINAL_TOKEN_7331" for m in child.calls[-1])


async def test_replayed_task_and_message_do_not_repeat_model_or_tool_side_effects():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    child = _ScriptedChatModel(script=[AIMessage(content="first"), AIMessage(content="second")])

    async def build(role, inbox):
        return create_agent(child, middleware=[inbox], checkpointer=saver)

    def coordinator():
        return SubagentSessions(
            session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
        )

    sessions = coordinator()
    first = await sessions.start("reviewer", "work", call_id="task-1", config={})
    stale = sessions.snapshot()
    completed_replay = coordinator()
    completed_replay.restore(stale)
    completed = await completed_replay.start(
        "reviewer", "work", call_id="task-1", config={}, background=True
    )
    assert completed["result"] == "first"
    replayed = await coordinator().start("reviewer", "work", call_id="task-1", config={})
    assert replayed["result"] == "first"
    assert child.i == 1
    await sessions.send(first["subagent_id"], "more", config={}, message_id="message-1")
    replay = coordinator()
    replay.restore(stale)
    replayed_message = await replay.send(
        first["subagent_id"], "more", config={}, message_id="message-1"
    )
    assert replayed_message["result"] == "second"
    assert child.i == 2


async def test_background_approval_survives_parent_after_model_hook_replay():
    from langgraph.types import Command, interrupt

    from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()

    @tool
    def approve() -> str:
        """Ask permission before proceeding."""
        return str(interrupt("Proceed?"))

    child = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "approve", "args": {}, "id": "approve-1", "type": "tool_call"}
                ],
            ),
            AIMessage(content="approved child done"),
        ]
    )
    parent = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "subagent_type": "reviewer",
                            "description": "work",
                            "background": True,
                        },
                        "id": "task-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="premature final"),
            AIMessage(content="parent synthesis"),
        ]
    )

    async def build(role, inbox):
        return create_agent(child, tools=[approve], middleware=[inbox], checkpointer=saver)

    def main():
        sessions = SubagentSessions(
            session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
        )
        return create_agent(
            parent, middleware=[SubagentSessionMiddleware(sessions)], checkpointer=saver
        )

    config = {"configurable": {"thread_id": "parent"}}
    first = await main().ainvoke({"messages": [HumanMessage(content="go")]}, config)
    assert first["__interrupt__"]
    second = await main().ainvoke(Command(resume="yes"), config)
    assert second["messages"][-1].content == "parent synthesis"
    assert "approved child done" in str(parent.calls[-1])
    assert sum(isinstance(m, HumanMessage) for m in child.calls[-1]) == 1


async def test_failed_child_with_pending_message_returns_without_automatic_retry():
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    entered, release = asyncio.Event(), asyncio.Event()

    class FailingModel(_ScriptedChatModel):
        async def _agenerate(self, messages, **kwargs):
            entered.set()
            await release.wait()
            raise ValueError("permanent provider failure")

    child = FailingModel(script=[AIMessage(content="unused")])

    async def build(role, inbox):
        return create_agent(child, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    started = await sessions.start("reviewer", "work", call_id="task-1", config={}, background=True)
    await asyncio.wait_for(entered.wait(), 3)
    await sessions.send(started["subagent_id"], "pending work", config={})
    release.set()
    result = await asyncio.wait_for(sessions.wait(started["subagent_id"], config={}), 3)
    assert result["status"] == "failed"


async def test_role_access_is_rechecked_before_completed_agent_continues():
    import pytest

    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    allowed = True
    child = _ScriptedChatModel(script=[AIMessage(content="done")])

    async def build(role, inbox):
        if not allowed:
            raise PermissionError("role access revoked")
        return create_agent(child, middleware=[inbox], checkpointer=saver)

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
    )
    first = await sessions.start("reviewer", "work", call_id="task-1", config={})
    allowed = False
    with pytest.raises(PermissionError):
        await sessions.send(first["subagent_id"], "rejected work", config={})
    assert child.i == 1
    allowed = True
    await sessions.send(first["subagent_id"], "allowed work", config={})
    assert [m.content for m in child.calls[-1] if isinstance(m, HumanMessage)] == [
        "work",
        "allowed work",
    ]


async def test_parallel_waits_for_same_child_surface_one_approval():
    import hashlib

    from langgraph.types import Command, interrupt

    from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
    from src.infra.agent.subagent_sessions import SubagentSessions

    saver = InMemorySaver()
    subagent_id = "subagent-" + hashlib.sha256(b"task-1").hexdigest()[:24]

    @tool
    def approve() -> str:
        """Ask permission before proceeding."""
        return str(interrupt("Proceed once?"))

    child = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "approve", "args": {}, "id": "approve-1", "type": "tool_call"}
                ],
            ),
            AIMessage(content="approved child done"),
        ]
    )
    parent = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "subagent_type": "reviewer",
                            "description": "work",
                            "background": True,
                        },
                        "id": "task-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "wait_subagent",
                        "args": {"subagent_id": subagent_id},
                        "id": f"wait-{index}",
                        "type": "tool_call",
                    }
                    for index in range(2)
                ],
            ),
            AIMessage(content="parent done"),
        ]
    )

    async def build(role, inbox):
        return create_agent(child, tools=[approve], middleware=[inbox], checkpointer=saver)

    def main():
        sessions = SubagentSessions(
            session_id="parent", user_id="owner", build_graph=build, checkpointer=saver
        )
        return create_agent(
            parent, middleware=[SubagentSessionMiddleware(sessions)], checkpointer=saver
        )

    config = {"configurable": {"thread_id": "parent"}}
    first = await main().ainvoke({"messages": [HumanMessage(content="go")]}, config)
    assert len(first["__interrupt__"]) == 1
    second = await main().ainvoke(Command(resume="yes"), config)
    assert second["messages"][-1].content == "parent done"
    assert child.i == 2


async def test_real_child_checkpoint_retains_terminal_timeout_and_parallel_tool_result(monkeypatch):
    from src.infra.agent.subagent_sessions import SubagentSessions

    monkeypatch.setattr("src.infra.agent.subagent_sessions.SUBAGENT_EXECUTION_TIMEOUT_SECONDS", 0.2)
    saver = InMemorySaver()
    entered = asyncio.Event()
    calls = []

    @tool
    async def read_probe() -> str:
        """Return a completed observation."""
        calls.append("read")
        return "checkpoint batch observation"

    @tool
    async def hold_probe() -> str:
        """Hold the other member of the tool batch."""
        calls.append("hold")
        entered.set()
        await asyncio.Event().wait()
        return "unreachable"

    child = _ScriptedChatModel(
        script=[
            AIMessage(
                content="Checking",
                tool_calls=[
                    {"id": "read", "name": "read_probe", "args": {}, "type": "tool_call"},
                    {"id": "hold", "name": "hold_probe", "args": {}, "type": "tool_call"},
                ],
            )
        ]
    )

    async def build(role, inbox):
        return create_agent(
            child, tools=[read_probe, hold_probe], middleware=[inbox], checkpointer=saver
        )

    sessions = SubagentSessions(
        session_id="durable", user_id="owner", build_graph=build, checkpointer=saver
    )
    try:
        started = await sessions.start(
            "reviewer", "Inspect", call_id="durable", config={}, background=True
        )
        key = started["subagent_id"]
        await asyncio.wait_for(entered.wait(), 1)
        old_parent = sessions.snapshot()
        await sessions.jobs[key]
        other = SubagentSessions(
            session_id="durable", user_id="owner", build_graph=build, checkpointer=saver
        )
        other.restore(old_parent)
        result = await other.wait(key, config={})
        assert result["status"] == "timed_out"
        assert "checkpoint batch observation" in result["result"]
        assert sorted(calls) == ["hold", "read"]
        assert not other.jobs
    finally:
        await sessions.close()


async def test_subagent_status_changes_keep_system_prefix_and_append_checkpoint_context():
    from types import SimpleNamespace

    from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
    from src.infra.agent.subagent_sessions import SubagentSessions

    class Request(SimpleNamespace):
        def override(self, **updates):
            return Request(**(vars(self) | updates))

    async def handler(request):
        return request

    sessions = SubagentSessions(
        session_id="parent", user_id="owner", build_graph=None, checkpointer=InMemorySaver()
    )
    middleware = SubagentSessionMiddleware(sessions)
    state = {"messages": [HumanMessage(content="Review")], "subagent_sessions": {}}
    request = Request(state=state, system_message=None)
    first = await middleware.awrap_model_call(request, handler)
    state["subagent_sessions"] = {"child": {"subagent_type": "reviewer", "status": "completed"}}
    update = await middleware.abefore_model(state, None)
    state["messages"].extend(update["messages"])
    state["subagent_sessions"] = update["subagent_sessions"]
    second = await middleware.awrap_model_call(request, handler)
    assert first.system_message == second.system_message
    assert '"subagent_id": "child"' in state["messages"][-1].content
    assert '"status": "completed"' in state["messages"][-1].content
    assert await middleware.abefore_model(state, None) is None
