"""Tool-call argument streaming: on_chat_model_stream tool_call_chunks → tool:args:chunk."""

from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.agent import AgentEventProcessor


class FakePresenter:
    def __init__(self) -> None:
        self.emitted: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.emitted.append(event)

    def present_agent_call(
        self,
        agent_id: str,
        agent_name: str,
        input_message: str,
        depth: int = 1,
        agent_avatar: str | None = None,
    ) -> dict[str, Any]:
        return {"event": "agent:call", "data": {"agent_id": agent_id}}

    def present_tool_start(
        self,
        tool_name: str,
        tool_input: Any,
        tool_call_id: str | None = None,
        depth: int = 0,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "tool:start",
            "data": {"tool": tool_name, "args": tool_input, "tool_call_id": tool_call_id},
        }

    def present_tool_args_delta(
        self,
        tool_name: str,
        tool_call_id: str | None,
        content: str,
        depth: int = 0,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "tool:args:chunk",
            "data": {
                "tool": tool_name,
                "tool_call_id": tool_call_id,
                "content": content,
                "depth": depth,
                "agent_id": agent_id,
            },
        }


def args_stream(
    tool_call_chunks: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
):
    chunk = SimpleNamespace(content="", id="chunk-t", tool_call_chunks=tool_call_chunks)
    return {
        "event": "on_chat_model_stream",
        "name": "chat_model",
        "data": {"chunk": chunk},
        "metadata": metadata or {},
    }


def model_end(metadata: dict[str, Any] | None = None):
    return {
        "event": "on_chat_model_end",
        "name": "chat_model",
        "data": {"output": None},
        "metadata": metadata or {},
    }


@pytest.mark.asyncio
async def test_first_args_delta_flushes_immediately_and_rest_flushes_on_model_end() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    # First chunk carries name + id but no args yet.
    await processor.process_event(
        args_stream([{"name": "write_file", "id": "call_1", "index": 0, "args": ""}])
    )
    assert presenter.emitted == []

    # First non-empty delta flushes immediately (first-chunk optimization).
    await processor.process_event(args_stream([{"index": 0, "args": '{"con'}]))
    assert presenter.emitted == [
        {
            "event": "tool:args:chunk",
            "data": {
                "tool": "write_file",
                "tool_call_id": "call_1",
                "content": '{"con',
                "depth": 0,
                "agent_id": None,
            },
        }
    ]

    # Below-threshold delta stays buffered until the model stream ends.
    await processor.process_event(args_stream([{"index": 0, "args": 'tent":"abc"}'}]))
    assert len(presenter.emitted) == 1

    await processor.process_event(model_end())
    assert presenter.emitted[1] == {
        "event": "tool:args:chunk",
        "data": {
            "tool": "write_file",
            "tool_call_id": "call_1",
            "content": 'tent":"abc"}',
            "depth": 0,
            "agent_id": None,
        },
    }


@pytest.mark.asyncio
async def test_buffered_args_delta_flushes_at_threshold() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        args_stream([{"name": "write_file", "id": "call_1", "index": 0, "args": ""}])
    )
    await processor.process_event(args_stream([{"index": 0, "args": "x" * 100}]))
    assert len(presenter.emitted) == 1

    # Below-threshold delta stays buffered (99 < 200).
    await processor.process_event(args_stream([{"index": 0, "args": "b" * 99}]))
    assert len(presenter.emitted) == 1

    # Crossing the 200-char threshold flushes the joined buffer.
    await processor.process_event(args_stream([{"index": 0, "args": "c" * 101}]))
    assert len(presenter.emitted) == 2
    assert presenter.emitted[1]["data"]["content"] == ("b" * 99) + ("c" * 101)


@pytest.mark.asyncio
async def test_parallel_tool_calls_stream_by_index() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        args_stream(
            [
                {"name": "grep", "id": "call_a", "index": 0, "args": ""},
                {"name": "read_file", "id": "call_b", "index": 1, "args": ""},
            ]
        )
    )
    await processor.process_event(args_stream([{"index": 0, "args": '{"q"'}]))
    await processor.process_event(args_stream([{"index": 1, "args": '{"file_path"'}]))
    await processor.process_event(model_end())

    by_tool = {e["data"]["tool"]: e["data"]["content"] for e in presenter.emitted}
    assert by_tool == {"grep": '{"q"', "read_file": '{"file_path"'}
    ids = {e["data"]["tool_call_id"] for e in presenter.emitted}
    assert ids == {"call_a", "call_b"}


@pytest.mark.asyncio
async def test_special_tools_do_not_stream_args() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    for tool in ("ask_human", "task", "write_todos"):
        await processor.process_event(
            args_stream([{"name": tool, "id": f"call_{tool}", "index": 0, "args": ""}])
        )
    await processor.process_event(args_stream([{"index": 0, "args": '{"a"'}]))
    await processor.process_event(args_stream([{"index": 1, "args": '{"b"'}]))
    await processor.process_event(args_stream([{"index": 2, "args": '{"c"'}]))
    await processor.process_event(model_end())

    assert presenter.emitted == []


@pytest.mark.asyncio
async def test_args_without_known_name_are_ignored_until_named() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    # Delta arriving with no name registered for the index is dropped.
    await processor.process_event(args_stream([{"index": 3, "args": '{"orphan"'}]))
    assert presenter.emitted == []


@pytest.mark.asyncio
async def test_subagent_tool_args_stream_carries_depth_and_agent() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    tools_ns = "tools:b0ffa46f-0647-782d-bb28-eb64b79cfc35"
    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run-9",
            "data": {
                "input": {
                    "subagent_type": "team-m-2-role",
                    "description": "子任务",
                }
            },
            "metadata": {
                "checkpoint_ns": "",
                "langgraph_checkpoint_ns": tools_ns,
            },
        }
    )

    model_ns = f"{tools_ns}|model:753eb9c0-959b-0158-2fca-9f83673a8598"
    await processor.process_event(
        args_stream(
            [{"name": "read_file", "id": "call_sub", "index": 0, "args": ""}],
            metadata={
                "checkpoint_ns": "",
                "langgraph_checkpoint_ns": model_ns,
                "lc_agent_name": "team-m-2-role",
            },
        )
    )
    await processor.process_event(
        args_stream(
            [{"index": 0, "args": '{"file_path":"/a"}'}],
            metadata={
                "checkpoint_ns": "",
                "langgraph_checkpoint_ns": model_ns,
                "lc_agent_name": "team-m-2-role",
            },
        )
    )

    args_events = [e for e in presenter.emitted if e["event"] == "tool:args:chunk"]
    assert len(args_events) == 1
    data = args_events[0]["data"]
    assert data["depth"] == 1
    assert data["agent_id"] is not None
    assert data["agent_id"].startswith("team-m-2-role_")
    assert data["tool_call_id"] == "call_sub"


@pytest.mark.asyncio
async def test_new_model_run_clears_stale_args_buffers() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        args_stream([{"name": "write_file", "id": "call_1", "index": 0, "args": ""}])
    )
    await processor.process_event(args_stream([{"index": 0, "args": '{"partial"'}]))

    # A new model run (next agent step) starts without flushing leftovers.
    await processor.process_event(
        {
            "event": "on_chat_model_start",
            "name": "chat_model",
            "data": {},
            "metadata": {},
        }
    )
    await processor.process_event(model_end())
    assert presenter.emitted == [
        {
            "event": "tool:args:chunk",
            "data": {
                "tool": "write_file",
                "tool_call_id": "call_1",
                "content": '{"partial"',
                "depth": 0,
                "agent_id": None,
            },
        }
    ]


@pytest.mark.asyncio
async def test_clear_releases_tool_args_buffers() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        args_stream([{"name": "ls", "id": "call_1", "index": 0, "args": ""}])
    )
    await processor.process_event(args_stream([{"index": 0, "args": '{"path"'}]))

    processor.clear()

    assert processor._tool_args_buffers == {}
