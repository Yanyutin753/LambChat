"""Recovery must not repeat a tool whose external outcome is unknown."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Interrupt

from src.infra.agent.recovery_guard import guard_graph_recovery
from src.kernel.errors import AppError, ErrorCode


def call(name="external_write", identity="write-1"):
    return AIMessage(content="", tool_calls=[{"name": name, "id": identity, "args": {}}])


def graph(messages, *, tasks=(), writes=(), tools=None, next_nodes=("tools",)):
    snapshot = SimpleNamespace(
        values={"messages": messages},
        next=next_nodes,
        tasks=tasks,
        config={"configurable": {"checkpoint_id": "saved"}},
    )
    return SimpleNamespace(
        aget_state=AsyncMock(return_value=snapshot),
        checkpointer=SimpleNamespace(
            aget_tuple=AsyncMock(return_value=SimpleNamespace(pending_writes=writes))
        ),
        builder=SimpleNamespace(
            nodes={"tools": SimpleNamespace(runnable=SimpleNamespace(tools_by_name=tools or {}))}
        ),
    )


async def test_unknown_write_stops_before_replay():
    with pytest.raises(AppError) as caught:
        await guard_graph_recovery(graph([call()]), {})
    assert caught.value.error_code is ErrorCode.TASK_RECOVERY_UNCERTAIN_EFFECT
    assert caught.value.args_data["tool_calls"] == [{"id": "write-1", "name": "external_write"}]


async def test_readonly_call_with_missing_identity_is_not_replay_authority():
    from src.infra.tool.web_fetch_tool import web_fetch

    with pytest.raises(AppError):
        await guard_graph_recovery(
            graph([call(name="web_fetch", identity=None)], tools={"web_fetch": web_fetch}), {}
        )


async def test_unrecognized_checkpoint_message_cannot_authorize_replay():
    with pytest.raises(AppError):
        await guard_graph_recovery(
            graph([{"type": "ai", "tool_calls": [{"name": "external_write", "id": "write-1"}]}]),
            {},
        )


async def test_all_messages_are_checked_not_just_last_ai():
    with pytest.raises(AppError):
        await guard_graph_recovery(
            graph([call(), HumanMessage(content="continue"), AIMessage(content="thinking")]), {}
        )


@pytest.mark.parametrize("location", ["messages", "task_result", "pending_write"])
async def test_durable_matching_tool_result_allows_continuation(location):
    result = ToolMessage(content="committed", tool_call_id="write-1")
    messages = [call(), result] if location == "messages" else [call()]
    tasks = (
        [SimpleNamespace(id="t", result={"messages": [result]}, interrupts=())]
        if location == "task_result"
        else [SimpleNamespace(id="t", result=None, interrupts=())]
        if location == "pending_write"
        else []
    )
    writes = [("t", "messages", [result])] if location == "pending_write" else []
    await guard_graph_recovery(graph(messages, tasks=tasks, writes=writes), {})


async def test_actual_builtin_readonly_fetch_can_resume():
    from src.infra.tool.web_fetch_tool import web_fetch

    await guard_graph_recovery(graph([call("web_fetch")], tools={"web_fetch": web_fetch}), {})


async def test_same_name_external_fetch_is_not_trusted_readonly():
    from langchain_core.tools import tool

    @tool("web_fetch")
    async def imposter() -> str:
        """A write disguised as a read."""
        return "wrote"

    with pytest.raises(AppError):
        await guard_graph_recovery(graph([call("web_fetch")], tools={"web_fetch": imposter}), {})


@pytest.mark.parametrize("resolved", [False, True])
async def test_fresh_approval_allowed_but_persisted_resume_cannot_authorize_replay(resolved):
    task = SimpleNamespace(
        id="task-1",
        result=None,
        interrupts=(Interrupt(value={"tool_call_id": "write-1"}, id="approval-1"),),
    )
    value = graph(
        [call()],
        tasks=[task],
        writes=[("task-1", "__resume__", [{"approved": True}])] if resolved else [],
    )
    if resolved:
        with pytest.raises(AppError):
            await guard_graph_recovery(value, {})
    else:
        await guard_graph_recovery(value, {})


async def test_other_fresh_approval_does_not_hide_unknown_parallel_write():
    task = SimpleNamespace(
        id="task-2",
        result=None,
        interrupts=(Interrupt(value={"tool_call_id": "ask-2"}, id="approval-2"),),
    )
    with pytest.raises(AppError):
        await guard_graph_recovery(graph([call(), call("ask_human", "ask-2")], tasks=[task]), {})


@pytest.mark.parametrize("reader", ["state", "pending_writes"])
async def test_checkpoint_read_failure_is_closed(reader):
    value = graph([call()])
    target = value.aget_state if reader == "state" else value.checkpointer.aget_tuple
    target.side_effect = RuntimeError("private connection details")
    with pytest.raises(AppError) as caught:
        await guard_graph_recovery(value, {})
    assert "private" not in str(caught.value)


async def test_no_pending_graph_work_allows_new_run():
    await guard_graph_recovery(graph([call()], next_nodes=()), {})


@pytest.mark.parametrize("name", ["ls", "read_file", "glob", "grep"])
async def test_actual_filesystem_read_tool_can_resume(name):
    from deepagents.middleware.filesystem import FilesystemMiddleware

    tools = {tool.name: tool for tool in FilesystemMiddleware().tools}
    await guard_graph_recovery(graph([call(name)], tools=tools), {})


@pytest.mark.parametrize("bounded", [False, True])
async def test_actual_readonly_eval_can_resume(bounded):
    from langchain_quickjs import CodeInterpreterMiddleware

    from src.infra.agent.middleware.ptc_adapter import create_bounded_interpreter

    factory = create_bounded_interpreter if bounded else CodeInterpreterMiddleware
    middleware = factory(subagents=False, ptc=[])
    tools = {tool.name: tool for tool in middleware.tools}
    await guard_graph_recovery(graph([call("eval")], tools=tools), {})


async def test_eval_with_subagent_host_is_not_readonly():
    from langchain_quickjs import CodeInterpreterMiddleware

    middleware = CodeInterpreterMiddleware(subagents=True, ptc=[])
    tools = {tool.name: tool for tool in middleware.tools}
    with pytest.raises(AppError):
        await guard_graph_recovery(graph([call("eval")], tools=tools), {})


async def test_real_checkpoint_after_approved_effect_stops_second_execution():
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.types import Command, interrupt

    effects = []

    async def external_write(_state):
        interrupt({"tool_call_id": "write-1", "message": "Approve write"})
        effects.append("committed")
        raise RuntimeError("lost process before durable tool result")

    builder = StateGraph(MessagesState)
    builder.add_node("tools", external_write)
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    compiled = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "approved-write"}}
    await compiled.ainvoke({"messages": [call()]}, config)
    await guard_graph_recovery(compiled, config)
    with pytest.raises(RuntimeError, match="lost process"):
        await compiled.ainvoke(Command(resume={"approved": True}), config)
    with pytest.raises(AppError) as caught:
        await guard_graph_recovery(compiled, config)
    assert caught.value.error_code is ErrorCode.TASK_RECOVERY_UNCERTAIN_EFFECT
    assert effects == ["committed"]


async def test_old_result_does_not_resolve_reused_id_in_later_round():
    messages = [
        call(identity="same"),
        ToolMessage(content="old commit", tool_call_id="same"),
        call(identity="same"),
    ]
    with pytest.raises(AppError):
        await guard_graph_recovery(graph(messages), {})


async def test_duplicate_unresolved_id_cannot_be_disambiguated_by_one_result():
    messages = [
        call(identity="same"),
        call(identity="same"),
        ToolMessage(content="one result", tool_call_id="same"),
    ]
    with pytest.raises(AppError):
        await guard_graph_recovery(
            graph(
                messages,
                writes=[("t", "messages", ToolMessage(content="one result", tool_call_id="same"))],
            ),
            {},
        )


async def test_multiple_ai_batches_keep_only_unpaired_calls():
    messages = [
        call(identity="a"),
        call(identity="b"),
        ToolMessage(content="a done", tool_call_id="a"),
        call(identity="c"),
        ToolMessage(content="c done", tool_call_id="c"),
    ]
    with pytest.raises(AppError) as caught:
        await guard_graph_recovery(graph(messages), {})
    assert caught.value.args_data["tool_calls"] == [{"id": "b", "name": "external_write"}]


async def test_global_legacy_resume_cannot_reuse_approval():
    task = SimpleNamespace(
        id="task-1",
        result=None,
        interrupts=(Interrupt(value={"tool_call_id": "write-1"}, id="approval-1"),),
    )
    with pytest.raises(AppError):
        await guard_graph_recovery(
            graph([call()], tasks=[task], writes=[("global", "__resume__", {"approved": True})]), {}
        )


@pytest.mark.parametrize("provenance", ["orphan_task", "non_message_channel"])
async def test_real_checkpoint_untrusted_pending_write_does_not_resolve_effect(provenance):
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, MessagesState, StateGraph

    class State(MessagesState):
        observation: dict

    effects = []

    async def external_write(_state):
        effects.append("committed")
        raise RuntimeError("lost process before durable tool result")

    builder = StateGraph(State)
    builder.add_node("tools", external_write)
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    saver = InMemorySaver()
    compiled = builder.compile(checkpointer=saver)
    config = {"configurable": {"thread_id": f"untrusted-result-{provenance}"}}
    with pytest.raises(RuntimeError, match="lost process"):
        await compiled.ainvoke({"messages": [call()]}, config)
    snapshot = await compiled.aget_state(config)
    assert len(snapshot.tasks) == 1
    old_result = ToolMessage(content="historical observation", tool_call_id="write-1")
    if provenance == "orphan_task":
        # Saved writes can exist for a task no longer in this checkpoint's frontier.
        # LangGraph ignores them when preparing the authoritative current state.
        await saver.aput_writes(snapshot.config, [("messages", [old_result])], "unrelated-old-task")
    else:
        # Even a current task can emit diagnostic/state data containing messages;
        # only an actual messages-channel result can settle its external operation.
        await saver.aput_writes(
            snapshot.config, [("observation", {"previous": old_result})], snapshot.tasks[0].id
        )

    current = await compiled.aget_state(config)
    assert not any(isinstance(message, ToolMessage) for message in current.values["messages"])
    with pytest.raises(AppError) as caught:
        await guard_graph_recovery(compiled, config)
    assert caught.value.error_code is ErrorCode.TASK_RECOVERY_UNCERTAIN_EFFECT
    assert effects == ["committed"]


async def test_real_checkpoint_current_task_messages_result_allows_recovery():
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, MessagesState, StateGraph

    wrote = asyncio.Event()
    effects = []

    async def external_write(_state):
        effects.append("committed")
        wrote.set()
        return {"messages": [ToolMessage(content="committed", tool_call_id="write-1")]}

    async def interrupted_sibling(_state):
        await wrote.wait()
        raise RuntimeError("sibling interrupted")

    builder = StateGraph(MessagesState)
    builder.add_node("tools", external_write)
    builder.add_node("sibling", interrupted_sibling)
    builder.add_edge(START, "tools")
    builder.add_edge(START, "sibling")
    builder.add_edge("tools", END)
    builder.add_edge("sibling", END)
    compiled = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "known-durable-result"}}
    with pytest.raises(RuntimeError, match="sibling interrupted"):
        await compiled.ainvoke({"messages": [call()]}, config)
    snapshot = await compiled.aget_state(config)
    # Request the exact checkpoint, before pending writes are folded into values.
    pinned = await compiled.aget_state(snapshot.config)
    assert not any(isinstance(message, ToolMessage) for message in pinned.values["messages"])
    assert any(
        task.name == "tools" and isinstance(task.result, dict) and task.result.get("messages")
        for task in pinned.tasks
    )
    await guard_graph_recovery(compiled, snapshot.config)
    assert effects == ["committed"]


async def test_task_messages_history_does_not_settle_a_later_reused_id():
    old = ToolMessage(content="old commit", tool_call_id="same")
    history = [call(identity="same"), old, call(identity="same")]
    task = SimpleNamespace(id="t", result={"messages": history}, interrupts=())
    with pytest.raises(AppError):
        await guard_graph_recovery(
            graph(history, tasks=[task], writes=[("t", "messages", history)]), {}
        )


async def test_real_fresh_input_after_cancelled_write_starts_without_replaying_effect():
    import asyncio

    from deepagents import create_deep_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.tools import tool
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.errors import NodeCancelledError

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, _tools, **_kwargs):
            return self

    effects = []

    @tool
    async def external_write() -> str:
        """Perform an external write."""
        effects.append("committed")
        raise asyncio.CancelledError

    compiled = create_deep_agent(
        model=Model(responses=[call(), AIMessage(content="fresh answer")]),
        tools=[external_write],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "cancelled-write-new-input"}}
    with pytest.raises(NodeCancelledError):
        await compiled.ainvoke({"messages": [HumanMessage(content="old task")]}, config)
    with pytest.raises(AppError) as caught:
        await guard_graph_recovery(compiled, config)
    assert caught.value.error_code is ErrorCode.TASK_RECOVERY_UNCERTAIN_EFFECT

    result = await compiled.ainvoke({"messages": [HumanMessage(content="new task")]}, config)
    assert effects == ["committed"]
    assert result["messages"][-1].content == "fresh answer"
    assert [
        message.content for message in result["messages"] if isinstance(message, HumanMessage)
    ] == [
        "old task",
        "new task",
    ]
    missing_result = next(
        message for message in result["messages"] if isinstance(message, ToolMessage)
    )
    assert missing_result.tool_call_id == "write-1"
    assert missing_result.status == "error"
    assert "no result was recorded" in missing_result.content
