from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command, Interrupt

from src.infra.agent import AgentEventProcessor
from src.infra.agent.events.buffers import TextChunkBuffer
from src.infra.agent.events.tool_events import _TOOL_RESULT_DISPLAY_MAX_CHARS
from src.infra.agent.events.tool_outputs import (
    TOOL_OUTPUT_SERIALIZE_MAX_STRING_CHARS,
    _compact_serializable_value,
    detect_tool_error,
    process_messages,
)
from src.infra.agent.first_event_timing import FirstEventTiming


class FakePresenter:
    def __init__(self) -> None:
        self.emitted: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.emitted.append(event)

    def present_text(
        self,
        content: str,
        text_id: str | None = None,
        depth: int = 0,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "message:chunk",
            "data": {
                "content": content,
                "text_id": text_id,
                "depth": depth,
                "agent_id": agent_id,
            },
        }

    def present_summary(
        self,
        content: str,
        summary_id: str | None = None,
        depth: int = 0,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "summary",
            "data": {
                "content": content,
                "summary_id": summary_id,
                "depth": depth,
                "agent_id": agent_id,
            },
        }

    def present_thinking(
        self,
        content: str,
        thinking_id: str | None = None,
        depth: int = 0,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "thinking",
            "data": {
                "content": content,
                "thinking_id": thinking_id,
                "depth": depth,
                "agent_id": agent_id,
            },
        }

    def present_agent_call(
        self,
        agent_id: str,
        agent_name: str,
        input_message: str,
        depth: int = 1,
        agent_avatar: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "agent:call",
            "data": {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_avatar": agent_avatar,
                "input": input_message,
                "depth": depth,
            },
        }

    def present_agent_result(
        self,
        agent_id: str,
        result: str,
        success: bool = True,
        depth: int = 1,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "agent:result",
            "data": {
                "agent_id": agent_id,
                "result": result,
                "success": success,
                "depth": depth,
                "error": error,
            },
        }

    def present_token_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        duration: float = 0.0,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        model_id: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "duration": duration,
        }
        if cache_creation_tokens:
            data["cache_creation_tokens"] = cache_creation_tokens
        if cache_read_tokens:
            data["cache_read_tokens"] = cache_read_tokens
        if model_id:
            data["model_id"] = model_id
        if model:
            data["model"] = model
        return {"event": "token:usage", "data": data}

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
            "data": {
                "tool": tool_name,
                "args": tool_input if isinstance(tool_input, dict) else {"input": tool_input},
                "tool_call_id": tool_call_id,
                "depth": depth,
                "agent_id": agent_id,
            },
        }

    def present_tool_result(
        self,
        tool_name: str,
        result: Any,
        tool_call_id: str | None = None,
        success: bool = True,
        error: str | None = None,
        depth: int = 0,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "tool:result",
            "data": {
                "tool": tool_name,
                "result": result,
                "tool_call_id": tool_call_id,
                "success": success,
                "error": error,
                "depth": depth,
                "agent_id": agent_id,
            },
        }


def chat_stream(content: str, chunk_id: str = "chunk-1", metadata: dict[str, Any] | None = None):
    return {
        "event": "on_chat_model_stream",
        "name": "chat_model",
        "data": {"chunk": SimpleNamespace(content=content, id=chunk_id)},
        "metadata": metadata or {},
    }


def reasoning_stream(
    content: str,
    chunk_id: str = "chunk-r",
    metadata: dict[str, Any] | None = None,
):
    return {
        "event": "on_chat_model_stream",
        "name": "chat_model",
        "data": {
            "chunk": SimpleNamespace(
                content="",
                id=chunk_id,
                additional_kwargs={"reasoning_content": content},
            )
        },
        "metadata": metadata or {},
    }


@pytest.mark.asyncio
async def test_finalize_flushes_pending_summary_chunk() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        chat_stream("summarized intent", "summary-1", {"lc_source": "summarization"})
    )

    # First chunk flushes immediately (first-chunk optimization).
    assert presenter.emitted == [
        {
            "event": "summary",
            "data": {
                "content": "summarized intent",
                "summary_id": "summary-1",
                "depth": 0,
                "agent_id": None,
            },
        }
    ]

    # finalize is idempotent when buffer is already empty.
    await processor.finalize()
    assert len(presenter.emitted) == 1


@pytest.mark.asyncio
async def test_image_analysis_internal_llm_stream_is_not_emitted_to_main_agent() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        chat_stream(
            "internal vision answer",
            "vision-chunk",
            {"lc_source": "image_analysis_tool"},
        )
    )
    await processor.process_event({"event": "on_chat_model_end", "data": {"output": None}})

    assert presenter.emitted == []
    assert processor.output_text == ""


@pytest.mark.asyncio
async def test_text_chunk_key_change_flushes_previous_chunk_without_dropping_current() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(chat_stream("hello", "chunk-1"))
    await processor.process_event(chat_stream("world", "chunk-2"))
    await processor.process_event({"event": "on_chat_model_end", "data": {"output": None}})

    assert [event["data"]["content"] for event in presenter.emitted] == ["hello", "world"]


@pytest.mark.asyncio
async def test_output_text_keeps_bounded_copy_while_streaming_all_chunks() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    chunk = "x" * 300
    for index in range(40):
        await processor.process_event(chat_stream(chunk, f"chunk-{index}"))
    await processor.flush()

    assert sum(len(event["data"]["content"]) for event in presenter.emitted) == 12_000
    assert len(processor.output_text) <= 8_000
    assert processor.output_text == "x" * 8_000


@pytest.mark.asyncio
async def test_reasoning_content_chunk_flushes_as_thinking_event() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(reasoning_stream("step by step"))

    # First chunk flushes immediately (first-chunk optimization).
    assert presenter.emitted == [
        {
            "event": "thinking",
            "data": {
                "content": "step by step",
                "thinking_id": "chunk-r",
                "depth": 0,
                "agent_id": None,
            },
        }
    ]

    # flush is idempotent when buffer is already empty.
    await processor.flush()
    assert len(presenter.emitted) == 1


@pytest.mark.asyncio
async def test_reasoning_content_chunks_are_grouped_until_threshold() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    # First chunk flushes immediately (first-chunk optimization).
    await processor.process_event(reasoning_stream("a" * 100))
    assert len(presenter.emitted) == 1
    assert presenter.emitted[0]["data"]["content"] == "a" * 100

    # Second chunk hasn't reached threshold yet (99 < 200).
    await processor.process_event(reasoning_stream("b" * 99))
    # Still only the first flush emitted.
    assert len(presenter.emitted) == 1

    # Third chunk pushes past the 200-char threshold (99 + 101 = 200).
    await processor.process_event(reasoning_stream("c" * 101))

    assert len(presenter.emitted) == 2
    # Second flush contains the buffered "b"*99 + "c"*101.
    assert presenter.emitted[1] == {
        "event": "thinking",
        "data": {
            "content": ("b" * 99) + ("c" * 101),
            "thinking_id": "chunk-r",
            "depth": 0,
            "agent_id": None,
        },
    }


@pytest.mark.asyncio
async def test_text_chunk_flushes_pending_thinking_first() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(reasoning_stream("thinking first"))
    await processor.process_event(chat_stream("final answer", "chunk-text"))
    await processor.flush()

    assert [event["event"] for event in presenter.emitted] == ["thinking", "message:chunk"]
    assert [event["data"]["content"] for event in presenter.emitted] == [
        "thinking first",
        "final answer",
    ]


@pytest.mark.asyncio
async def test_first_provider_milestones_are_recorded_without_delaying_thinking() -> None:
    phases: list[str] = []

    class _RecordingTiming(FirstEventTiming):
        def start_model(self) -> None:
            super().start_model()

        def record_once(self, phase) -> None:
            if phase not in self._seen:
                phases.append(phase)
            super().record_once(phase)

    presenter = FakePresenter()
    processor = AgentEventProcessor(
        presenter,
        first_event_timing=_RecordingTiming(clock=lambda: 0.0),
    )

    await processor.process_event(
        {"event": "on_chat_model_start", "name": "chat_model", "metadata": {}}
    )
    await processor.process_event(chat_stream(""))
    await processor.process_event(reasoning_stream("thinking first"))
    await processor.process_event(chat_stream("final answer", "chunk-text"))

    assert phases == [
        "provider_first_delta",
        "provider_first_reasoning",
        "provider_first_text",
    ]
    assert [event["event"] for event in presenter.emitted] == ["thinking", "message:chunk"]


@pytest.mark.asyncio
async def test_task_start_reads_langgraph_checkpoint_ns_not_empty_checkpoint_ns() -> None:
    """LangGraph v2 sets metadata.checkpoint_ns='' and puts the real namespace in
    metadata.langgraph_checkpoint_ns.  _handle_task_start must read the latter so
    that subsequent sub-agent events can be matched via first_segment lookup."""
    presenter = FakePresenter()
    processor = AgentEventProcessor(
        presenter,
        subagent_display_names={"team-m-1-role": "健身教练"},
    )

    # Simulate a real LangGraph v2 task tool_start event:
    #   checkpoint_ns=""          (empty – legacy field)
    #   langgraph_checkpoint_ns="tools:9864e6bc-...|model:45d3..."  (actual ns)
    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run-1",
            "data": {
                "input": {
                    "subagent_type": "team-m-1-role",
                    "description": "健身计划",
                },
            },
            "metadata": {
                "checkpoint_ns": "",
                "langgraph_checkpoint_ns": "tools:9864e6bc-f1bf-94cf-adc4-0ed5c6f59cd1",
            },
        }
    )

    # The key in checkpoint_to_agent must be the langgraph_checkpoint_ns value,
    # NOT the empty string.
    assert "" not in processor.checkpoint_to_agent
    ns_key = "tools:9864e6bc-f1bf-94cf-adc4-0ed5c6f59cd1"
    assert ns_key in processor.checkpoint_to_agent
    instance_id, subagent_type = processor.checkpoint_to_agent[ns_key]
    assert subagent_type == "team-m-1-role"
    assert instance_id.startswith("team-m-1-role_")

    # agent:call event must have been emitted with the correct display name.
    call_event = presenter.emitted[0]
    assert call_event["event"] == "agent:call"
    assert call_event["data"]["agent_name"] == "健身教练"
    assert call_event["data"]["agent_id"] == instance_id


@pytest.mark.asyncio
async def test_subagent_call_input_hides_internal_main_context_snapshot() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run-context",
            "data": {
                "input": {
                    "subagent_type": "general-purpose",
                    "description": (
                        "Inspect auth.\n\n"
                        "## Main-Agent Context Snapshot\n"
                        "Read it when the assignment depends on prior user/main-agent context: "
                        "/workflow/session/subagent_context/main_agent_messages_ctx.md\n"
                        "Treat this file as context only; the explicit task above remains your objective."
                    ),
                },
            },
            "metadata": {
                "langgraph_checkpoint_ns": "tools:context",
            },
        }
    )

    call_event = presenter.emitted[0]

    assert call_event["event"] == "agent:call"
    assert call_event["data"]["input"] == "Inspect auth."
    assert "Main-Agent Context Snapshot" not in call_event["data"]["input"]
    assert "/workflow/" not in call_event["data"]["input"]


@pytest.mark.asyncio
async def test_subagent_stream_resolved_via_langgraph_checkpoint_ns() -> None:
    """After a task tool_start registers with langgraph_checkpoint_ns, a
    sub-agent's on_chat_model_stream whose langgraph_checkpoint_ns is
    '<tools_ns>|model:...' must be resolved to the correct (agent_id, 1)."""
    presenter = FakePresenter()
    processor = AgentEventProcessor(
        presenter,
        subagent_display_names={"team-m-2-role": "营养师"},
    )

    tools_ns = "tools:b0ffa46f-0647-782d-bb28-eb64b79cfc35"

    # 1. task start – registers checkpoint_to_agent[tools_ns]
    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run-2",
            "data": {
                "input": {
                    "subagent_type": "team-m-2-role",
                    "description": "食谱推荐",
                },
            },
            "metadata": {
                "checkpoint_ns": "",
                "langgraph_checkpoint_ns": tools_ns,
            },
        }
    )

    # 2. Sub-agent model stream – langgraph_checkpoint_ns is nested
    model_ns = f"{tools_ns}|model:753eb9c0-959b-0158-2fca-9f83673a8598"
    presenter.emitted.clear()

    await processor.process_event(
        {
            "event": "on_chat_model_stream",
            "name": "chat_model",
            "data": {
                "chunk": SimpleNamespace(content="你好", id="sub-chunk-1"),
            },
            "metadata": {
                "checkpoint_ns": "",
                "langgraph_checkpoint_ns": model_ns,
                "lc_agent_name": "team-m-2-role",
            },
        }
    )

    # Flush the chunk buffer via model_end
    await processor.process_event(
        {
            "event": "on_chat_model_end",
            "name": "chat_model",
            "data": {"output": None},
            "metadata": {
                "checkpoint_ns": "",
                "langgraph_checkpoint_ns": model_ns,
            },
        }
    )

    # The text chunk must carry the correct agent_id (not None)
    assert len(presenter.emitted) >= 1
    text_event = next(e for e in presenter.emitted if e["event"] == "message:chunk")
    assert text_event["event"] == "message:chunk"
    assert text_event["data"]["depth"] == 1
    assert text_event["data"]["agent_id"] is not None
    assert text_event["data"]["agent_id"].startswith("team-m-2-role_")


@pytest.mark.asyncio
async def test_task_end_resolves_agent_info_via_langgraph_checkpoint_ns() -> None:
    """When a task tool_end arrives, _resolve_agent_info must read
    langgraph_checkpoint_ns to pop the correct entry from checkpoint_to_agent."""
    presenter = FakePresenter()
    processor = AgentEventProcessor(
        presenter,
        subagent_display_names={"team-m-1-role": "健身教练"},
    )

    tools_ns = "tools:9864e6bc-f1bf-94cf-adc4-0ed5c6f59cd1"

    # 1. task start
    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run-3",
            "data": {
                "input": {
                    "subagent_type": "team-m-1-role",
                    "description": "健身",
                },
            },
            "metadata": {
                "checkpoint_ns": "",
                "langgraph_checkpoint_ns": tools_ns,
            },
        }
    )

    instance_id = list(processor.checkpoint_to_agent.values())[0][0]

    # 2. task end
    presenter.emitted.clear()
    await processor.process_event(
        {
            "event": "on_tool_end",
            "name": "task",
            "run_id": "task-run-3",
            "data": {"output": "Done"},
            "metadata": {
                "checkpoint_ns": "",
                "langgraph_checkpoint_ns": tools_ns,
            },
        }
    )

    result_event = presenter.emitted[0]
    assert result_event["event"] == "agent:result"
    assert result_event["data"]["agent_id"] == instance_id
    assert result_event["data"]["success"] is True
    # checkpoint_to_agent entry must have been popped
    assert tools_ns not in processor.checkpoint_to_agent


@pytest.mark.asyncio
async def test_task_end_prefers_original_subagent_content_for_visible_result() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)
    tools_ns = "tools:original-result"

    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run-original",
            "data": {
                "input": {
                    "subagent_type": "general-purpose",
                    "description": "Investigate",
                },
            },
            "metadata": {"langgraph_checkpoint_ns": tools_ns},
        }
    )

    presenter.emitted.clear()
    await processor.process_event(
        {
            "event": "on_tool_end",
            "name": "task",
            "run_id": "task-run-original",
            "data": {
                "output": Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "Subagent report saved to: /subagent_reports/report.md",
                                tool_call_id="call-1",
                                additional_kwargs={
                                    "lambchat_original_content": "Original final report"
                                },
                            )
                        ]
                    }
                )
            },
            "metadata": {"langgraph_checkpoint_ns": tools_ns},
        }
    )

    result_event = presenter.emitted[0]
    assert result_event["event"] == "agent:result"
    assert result_event["data"]["result"] == "Original final report"


@pytest.mark.asyncio
async def test_subagent_context_cache_is_invalidated_by_task_lifecycle() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)
    processor.checkpoint_to_agent["parent"] = ("agent-1", "worker")

    assert processor._get_agent_context("parent|child") == ("agent-1", 1)
    assert processor._agent_context_cache["parent|child"] == ("agent-1", 1)

    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run",
            "data": {"input": {"subagent_type": "worker", "description": "do work"}},
            "metadata": {"checkpoint_ns": "parent"},
        }
    )

    assert processor._agent_context_cache == {}


@pytest.mark.asyncio
async def test_task_start_uses_registered_subagent_display_name() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(
        presenter,
        subagent_display_names={
            "team-m-1-researcher": "Researcher",
        },
    )

    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run",
            "data": {
                "input": {
                    "subagent_type": "team-m-1-researcher",
                    "description": "Find the facts",
                }
            },
            "metadata": {"checkpoint_ns": "task:abc"},
        }
    )

    assert presenter.emitted[0]["data"]["agent_name"] == "Researcher"


@pytest.mark.asyncio
async def test_task_start_uses_registered_subagent_avatar() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(
        presenter,
        subagent_display_names={
            "team-m-1-designer": "Designer",
        },
        subagent_avatars={
            "team-m-1-designer": "https://cdn.example.com/designer.png",
        },
    )

    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run",
            "data": {
                "input": {
                    "subagent_type": "team-m-1-designer",
                    "description": "Design the flow",
                }
            },
            "metadata": {"checkpoint_ns": "task:abc"},
        }
    )

    assert presenter.emitted[0]["data"]["agent_avatar"] == ("https://cdn.example.com/designer.png")


def test_text_chunk_buffer_consume_ready_flushes_previous_key_without_losing_current() -> None:
    buffer = TextChunkBuffer(flush_size=10)

    # First chunk flushes immediately (first-chunk optimization).
    assert buffer.append("hello", (0, None, "chunk-1")) is True
    flushed = buffer.consume()
    assert flushed == ("hello", (0, None, "chunk-1"))
    # Buffer is now empty; consume_ready on a different key returns None.
    assert buffer.consume_ready((0, None, "chunk-2")) is None
    # Second chunk: has_flushed is still True, length 5 < flush_size 10 → no flush.
    assert buffer.append("world", (0, None, "chunk-2")) is False
    assert buffer.consume() == ("world", (0, None, "chunk-2"))


def test_detect_tool_error_detects_string_error_prefix() -> None:
    assert detect_tool_error(None, "Error: failed to run") == (True, "Error: failed to run")


def test_process_messages_compacts_large_artifact_before_serializing() -> None:
    large_value = "x" * 120_000
    result = process_messages(
        [
            SimpleNamespace(
                content="",
                artifact={
                    "rows": [
                        {"body": large_value},
                        {"body": large_value},
                    ],
                },
            )
        ]
    )

    assert isinstance(result, str)
    assert len(result) < 210_000
    assert large_value not in result
    assert "truncated from 120000 chars" in result


def test_process_messages_compacts_large_text_content_before_joining() -> None:
    large_value = "x" * 120_000

    result = process_messages([SimpleNamespace(content=large_value)])

    assert isinstance(result, str)
    assert len(result) > 95_000
    assert len(result) < 102_000
    assert large_value not in result
    assert "truncated from 120000 chars" in result


def test_tool_output_string_limits_are_large_enough_for_rich_results() -> None:
    assert TOOL_OUTPUT_SERIALIZE_MAX_STRING_CHARS == 100_000
    assert _TOOL_RESULT_DISPLAY_MAX_CHARS == 100_000


def test_compact_serializable_value_does_not_materialize_large_dict_items() -> None:
    class GuardedLargeDict(dict):
        def __len__(self) -> int:
            return 1_000_000

        def items(self):
            raise AssertionError("large dict compaction must not materialize all items")

        def __iter__(self):
            yield from (f"key-{index}" for index in range(101))

        def __getitem__(self, key):
            return f"value-{key}"

    compacted = _compact_serializable_value(GuardedLargeDict())

    assert len(compacted) == 101
    assert compacted["key-0"] == "value-key-0"
    assert compacted["_truncated_keys"] == 999_900


@pytest.mark.asyncio
async def test_tool_error_emits_start_and_failed_result_when_start_was_missing() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        {
            "event": "on_tool_error",
            "name": "mcp_search",
            "run_id": "tool-run-1",
            "data": {
                "input": {"query": "hello"},
                "error": ValueError("invalid query argument"),
            },
            "metadata": {},
        }
    )

    assert presenter.emitted == [
        {
            "event": "tool:start",
            "data": {
                "tool": "mcp_search",
                "args": {"query": "hello"},
                "tool_call_id": "tool-run-1",
                "depth": 0,
                "agent_id": None,
            },
        },
        {
            "event": "tool:result",
            "data": {
                "tool": "mcp_search",
                "result": "[MCP Tool Error] mcp_search failed: [ValueError] invalid query argument",
                "tool_call_id": "tool-run-1",
                "success": False,
                "error": "[MCP Tool Error] mcp_search failed: [ValueError] invalid query argument",
                "depth": 0,
                "agent_id": None,
            },
        },
    ]


@pytest.mark.asyncio
async def test_tool_error_does_not_emit_duplicate_start_after_start_event() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "mcp_search",
            "run_id": "tool-run-1",
            "data": {"input": {"query": "hello"}},
            "metadata": {},
        }
    )
    await processor.process_event(
        {
            "event": "on_tool_error",
            "name": "mcp_search",
            "run_id": "tool-run-1",
            "data": {
                "input": {"query": "hello"},
                "error": TypeError("missing required parameter"),
            },
            "metadata": {},
        }
    )

    assert [event["event"] for event in presenter.emitted] == ["tool:start", "tool:result"]
    assert presenter.emitted[1]["data"]["success"] is False
    assert presenter.emitted[1]["data"]["tool_call_id"] == "tool-run-1"


@pytest.mark.asyncio
async def test_ask_human_stream_events_are_not_rendered_as_generic_tool_events() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "ask_human",
            "run_id": "tool-run-1",
            "data": {"input": {"question": "continue?"}},
            "metadata": {},
        }
    )
    await processor.process_event(
        {
            "event": "on_tool_error",
            "name": "ask_human",
            "run_id": "tool-run-1",
            "data": {
                "input": {"question": "continue?"},
                "error": GraphInterrupt((Interrupt(value={"kind": "ask_human"}),)),
            },
            "metadata": {},
        }
    )
    await processor.process_event(
        {
            "event": "on_tool_start",
            "name": "ask_human",
            "run_id": "tool-run-2",
            "data": {"input": {"question": "continue?"}},
            "metadata": {},
        }
    )
    await processor.process_event(
        {
            "event": "on_tool_end",
            "name": "ask_human",
            "run_id": "tool-run-2",
            "data": {"output": '{"status":"success"}'},
            "metadata": {},
        }
    )

    assert presenter.emitted == []


@pytest.mark.asyncio
async def test_tool_result_large_json_string_is_not_parsed_and_is_clipped() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)
    large_json = '{"rows": ["' + ("x" * 120_000) + '"]}'

    await processor.process_event(
        {
            "event": "on_tool_end",
            "name": "large_tool",
            "run_id": "tool-run-large",
            "data": {"output": large_json},
            "metadata": {},
        }
    )

    result = presenter.emitted[0]["data"]["result"]

    assert isinstance(result, str)
    assert len(result) < len(large_json)
    assert "[truncated from" in result
    assert presenter.emitted[0]["data"]["tool_call_id"] == "tool-run-large"


@pytest.mark.asyncio
async def test_tool_end_offloads_output_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.agent.events import tool_events

    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)
    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(tool_events, "run_blocking_io", fake_run_blocking_io, raising=False)

    await processor.process_event(
        {
            "event": "on_tool_end",
            "name": "large_tool",
            "run_id": "tool-run-large",
            "data": {
                "output": SimpleNamespace(
                    content=[
                        {"type": "text", "text": "x" * 20_000},
                    ]
                )
            },
            "metadata": {},
        }
    )

    assert tool_events.extract_tool_output in calls
    assert presenter.emitted[0]["data"]["tool_call_id"] == "tool-run-large"


@pytest.mark.asyncio
async def test_tool_end_offloads_result_json_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.agent.events import tool_events

    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)
    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(tool_events, "run_blocking_io", fake_run_blocking_io, raising=False)

    await processor.process_event(
        {
            "event": "on_tool_end",
            "name": "json_tool",
            "run_id": "tool-run-json",
            "data": {"output": '{"ok": true, "items": [1, 2]}'},
            "metadata": {},
        }
    )

    assert tool_events._parse_tool_result_json in calls
    assert presenter.emitted[0]["data"]["result"] == {"ok": True, "items": [1, 2]}


@pytest.mark.asyncio
async def test_emit_token_usage_flushes_accumulated_totals_once() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)
    processor.total_input_tokens = 7
    processor.total_output_tokens = 3
    processor.total_cache_creation_tokens = 2
    processor.total_cache_read_tokens = 5

    emitted = await processor.emit_token_usage(
        duration=1.5,
        model_id="model-config-1",
        model="openai/gpt-4.1",
    )
    emitted_again = await processor.emit_token_usage(duration=2.0)

    assert emitted is True
    assert emitted_again is False
    assert presenter.emitted == [
        {
            "event": "token:usage",
            "data": {
                "input_tokens": 7,
                "output_tokens": 3,
                "total_tokens": 10,
                "duration": 1.5,
                "cache_creation_tokens": 2,
                "cache_read_tokens": 5,
                "model_id": "model-config-1",
                "model": "openai/gpt-4.1",
            },
        }
    ]


def test_text_chunk_buffer_time_based_flush_surfaces_small_tail() -> None:
    buffer = TextChunkBuffer(flush_size=100, flush_interval=1.0)

    # First chunk flushes immediately.
    assert buffer.append("hello", (0, None, "k")) is True
    buffer.consume()

    # Below size threshold and within the interval: keep buffering.
    assert buffer.append("world", (0, None, "k")) is False

    # Once the interval elapsed, the same small tail must flush on next append.
    buffer._last_flush_at = buffer._last_flush_at - 2.0
    assert buffer.append("!", (0, None, "k")) is True
    assert buffer.consume() == ("world!", (0, None, "k"))


def test_text_chunk_buffer_no_time_flush_when_interval_disabled() -> None:
    buffer = TextChunkBuffer(flush_size=100)

    assert buffer.append("hello", (0, None, "k")) is True
    buffer.consume()

    buffer._last_flush_at = buffer._last_flush_at - 3600.0
    assert buffer.append("tail", (0, None, "k")) is False
