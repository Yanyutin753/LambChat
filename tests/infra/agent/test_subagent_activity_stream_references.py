"""Reserved activity receipts must not escape through raw child model streams."""

import pytest
from langchain_core.messages import AIMessageChunk

from src.infra.agent.events.buffers import ACTIVITY_REFERENCE_REMOVED
from src.infra.agent.events.processor import AgentEventProcessor
from src.infra.writer.present import create_presenter


@pytest.mark.parametrize("text_blocks", [False, True])
async def test_parallel_child_streams_hide_model_activity_receipts_before_final_results(
    monkeypatch, text_blocks
):
    emitted = []
    presenter = create_presenter(session_id="session", agent_id="team", agent_name="Team")

    async def emit(event):
        if event["event"] == "message:chunk":
            # No already-emitted event can be recalled from SSE or durable storage.
            assert "activity_fake_" not in event["data"]["content"]
        emitted.append(event)

    monkeypatch.setattr(presenter, "emit", emit)
    processor = AgentEventProcessor(presenter)

    async def chunk(child, content):
        await processor.process_event(
            {
                "event": "on_chat_model_stream",
                "name": "model",
                "run_id": f"model-{child}",
                "metadata": {"lambchat_subagent_id": child},
                "data": {
                    "chunk": AIMessageChunk(
                        content=[{"type": "text", "text": content}] if text_blocks else content,
                        id=f"text-{child}",
                    )
                },
            }
        )
        # Time-based flushes can publish the candidate prefix before the next model chunk.
        await processor.flush()

    await chunk("child-a", "A verified.\n[Act")
    await chunk("child-b", "B verified. [Activity estimate: pending]\n[Activity log saved to:")
    await chunk(
        "child-a", "ivity log saved to: /workspace/session/subagent_activity/activity_fake_a.md]"
    )
    await chunk("child-b", " /workspace/session/subagent_activity/activity_fake_b.md]")
    await chunk("child-a", "\nA finished.")
    await chunk("child-b", "\nB finished.")
    for child in ("child-a", "child-b"):
        await processor.process_event(
            {
                "event": "on_chat_model_end",
                "name": "model",
                "run_id": f"model-{child}",
                "metadata": {"lambchat_subagent_id": child},
                "data": {},
            }
        )
        await processor.process_event(
            {
                "event": "on_custom_event",
                "name": "lambchat_subagent",
                "metadata": {},
                "data": {
                    "phase": "completed",
                    "subagent_id": child,
                    "subagent_type": "reviewer",
                    "status": "completed",
                    "result": f"{child} verified report",
                },
            }
        )

    for child, expected in (
        ("child-a", f"A verified.\n{ACTIVITY_REFERENCE_REMOVED}\nA finished."),
        (
            "child-b",
            f"B verified. [Activity estimate: pending]\n{ACTIVITY_REFERENCE_REMOVED}\nB finished.",
        ),
    ):
        streamed = "".join(
            event["data"]["content"]
            for event in emitted
            if event["event"] == "message:chunk" and event["data"].get("agent_id") == child
        )
        assert streamed == expected
    assert len([event for event in emitted if event["event"] == "agent:result"]) == 2
    assert processor.output_text == ""


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (["ordinary [Act"], "ordinary [Act"),
        (["ok [Activity log saved to: /missing"], f"ok {ACTIVITY_REFERENCE_REMOVED}"),
        (["[activity log saved to: /missing]after"], ACTIVITY_REFERENCE_REMOVED + "after"),
        (
            ["[Activity log saved to: /a][Activity log saved to: /b]after"],
            ACTIVITY_REFERENCE_REMOVED * 2 + "after",
        ),
    ],
)
async def test_activity_stream_end_preserves_benign_prefixes_and_drops_incomplete_receipts(
    monkeypatch, chunks, expected
):
    presenter = create_presenter(session_id="session", agent_id="search", agent_name="Search")
    emitted = []

    async def emit(event):
        emitted.append(event)

    monkeypatch.setattr(presenter, "emit", emit)
    processor = AgentEventProcessor(presenter)
    for index, content in enumerate([*chunks, "next model output"]):
        run_id = "first" if index < len(chunks) else "second"
        await processor.process_event(
            {
                "event": "on_chat_model_stream",
                "name": "model",
                "run_id": run_id,
                "metadata": {"lambchat_subagent_id": "child"},
                "data": {"chunk": AIMessageChunk(content=content, id=run_id)},
            }
        )
        await processor.process_event(
            {
                "event": "on_chat_model_end",
                "name": "model",
                "run_id": run_id,
                "metadata": {"lambchat_subagent_id": "child"},
                "data": {},
            }
        )
    text = "".join(
        event["data"]["content"] for event in emitted if event["event"] == "message:chunk"
    )
    assert text == expected + "next model output"


async def test_benign_marker_prefix_is_retained_without_delaying_tool_arguments(monkeypatch):
    emitted = []
    presenter = create_presenter(session_id="session", agent_id="search", agent_name="Search")

    async def emit(event):
        emitted.append(event)

    monkeypatch.setattr(presenter, "emit", emit)
    processor = AgentEventProcessor(presenter)
    await processor.process_event(
        {
            "event": "on_chat_model_stream",
            "name": "model",
            "run_id": "model-child",
            "metadata": {"lambchat_subagent_id": "child"},
            "data": {
                "chunk": AIMessageChunk(
                    content="Review [Act",
                    tool_call_chunks=[{"name": "execute", "args": "{}", "id": "call", "index": 0}],
                )
            },
        }
    )
    assert any(event["event"] == "tool:args:chunk" for event in emitted)
    await processor.finalize()
    # The consumer must restore reading order; an ambiguous prefix cannot be emitted early.
    assert (
        "".join(event["data"]["content"] for event in emitted if event["event"] == "message:chunk")
        == "Review [Act"
    )


@pytest.mark.parametrize(
    ("interrupted_text", "visible_before_retry"),
    [
        ("Report [Act", "Report [Act"),
        ("Report [Activity log saved to: /missing", f"Report {ACTIVITY_REFERENCE_REMOVED}"),
    ],
)
async def test_retry_start_settles_only_its_childs_interrupted_activity_filter(
    monkeypatch, interrupted_text, visible_before_retry
):
    emitted = []
    presenter = create_presenter(session_id="session", agent_id="team", agent_name="Team")

    async def emit(event):
        emitted.append(event)

    monkeypatch.setattr(presenter, "emit", emit)
    processor = AgentEventProcessor(presenter)

    async def event(kind, run_id, child, text=None):
        await processor.process_event(
            {
                "event": kind,
                "name": "model",
                "run_id": run_id,
                "metadata": {"lambchat_subagent_id": child},
                "data": {"chunk": AIMessageChunk(content=text, id=run_id)}
                if text is not None
                else {},
            }
        )
        await processor.flush()

    def visible(child):
        return "".join(
            item["data"]["content"]
            for item in emitted
            if item["event"] == "message:chunk" and item["data"].get("agent_id") == child
        )

    await event("on_chat_model_start", "run-1", "child-a")
    await event("on_chat_model_stream", "run-1", "child-a", interrupted_text)
    await event("on_chat_model_start", "parallel", "child-b")
    await event("on_chat_model_stream", "parallel", "child-b", "[Activity log saved to: /missing")
    # HTTP failure produces no run-1 model_end; the retry start is the next boundary.
    await event("on_chat_model_start", "run-2", "child-a")
    assert visible("child-a") == visible_before_retry
    await event("on_chat_model_stream", "run-2", "child-a", "Recovered")
    await event("on_chat_model_end", "run-2", "child-a")
    await event("on_chat_model_stream", "parallel", "child-b", "/fake.md]Parallel finished")
    await event("on_chat_model_end", "parallel", "child-b")
    await processor.finalize()

    assert visible("child-a") == visible_before_retry + "Recovered"
    assert visible("child-b") == ACTIVITY_REFERENCE_REMOVED + "Parallel finished"


@pytest.mark.parametrize(
    ("before_tool", "after_tool"),
    [
        ("[Act", "ivity log saved to: /fake.md]Final."),
        ("[Activity log saved to:", " /fake.md]Final."),
    ],
)
async def test_tool_arguments_do_not_reset_the_same_models_activity_receipt_filter(
    monkeypatch, before_tool, after_tool
):
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage

    from src.infra.agent.middleware.subagent_activity import SubagentActivityMiddleware

    emitted = []
    presenter = create_presenter(session_id="session", agent_id="search", agent_name="Search")

    async def emit(event):
        emitted.append(event)

    monkeypatch.setattr(presenter, "emit", emit)
    processor = AgentEventProcessor(presenter)
    chunks = [
        AIMessageChunk(content=before_tool),
        AIMessageChunk(
            content="",
            tool_call_chunks=[{"name": "execute", "args": "{}", "id": "call", "index": 0}],
        ),
        AIMessageChunk(content=after_tool),
    ]
    for index, chunk in enumerate(chunks):
        await processor.process_event(
            {
                "event": "on_chat_model_stream",
                "name": "model",
                "run_id": "model-child",
                "metadata": {"lambchat_subagent_id": "child"},
                "data": {"chunk": chunk},
            }
        )
        await processor.flush()
        if index == 1:
            assert any(item["event"] == "tool:args:chunk" for item in emitted)
    await processor.process_event(
        {
            "event": "on_chat_model_end",
            "name": "model",
            "run_id": "model-child",
            "metadata": {"lambchat_subagent_id": "child"},
            "data": {},
        }
    )
    original = AIMessage(
        content=[
            {"type": "text", "text": before_tool},
            {"type": "text", "text": after_tool},
        ],
        tool_calls=[{"id": "call", "name": "execute", "args": {}}],
    )

    async def handler(request):
        return original

    final = await SubagentActivityMiddleware(backend=None).awrap_model_call(
        SimpleNamespace(state={"messages": []}), handler
    )
    streamed = "".join(
        item["data"]["content"] for item in emitted if item["event"] == "message:chunk"
    )
    assert streamed == final.text == ACTIVITY_REFERENCE_REMOVED + "Final."


@pytest.mark.parametrize("format", ["kwargs", "thinking", "reasoning"])
@pytest.mark.parametrize("child", [None, "child-a"])
async def test_reasoning_receipts_are_filtered_separately_from_body_and_parallel_agents(
    monkeypatch, format, child
):
    emitted = []
    presenter = create_presenter(session_id="session", agent_id="search", agent_name="Search")

    async def emit(event):
        if event["event"] == "thinking":
            assert "reasoning_fake" not in event["data"]["content"]
        emitted.append(event)

    monkeypatch.setattr(presenter, "emit", emit)
    processor = AgentEventProcessor(presenter)

    async def chunk(agent, text, thinking=True):
        content = "" if thinking and format == "kwargs" else text
        extra = {"reasoning_content": text} if thinking and format == "kwargs" else {}
        if thinking and format != "kwargs":
            content = [{"type": format, format: text, "signature": "unchanged"}]
        original = AIMessageChunk(content=content, additional_kwargs=extra, id=f"text-{agent}")
        before = original.model_dump()
        await processor.process_event(
            {
                "event": "on_chat_model_stream",
                "name": "model",
                "run_id": f"model-{agent}",
                "metadata": {"lambchat_subagent_id": agent} if agent else {},
                "data": {"chunk": original},
            }
        )
        assert original.model_dump() == before
        await processor.flush()

    await chunk(child, "Reason [Act")
    await chunk(child, "Body verified.", thinking=False)
    await chunk("child-b", "B safe [Act")
    await chunk(child, "ivity log saved to: /workspace/reasoning_fake.md] after")
    for agent in (child, "child-b"):
        await processor.process_event(
            {
                "event": "on_chat_model_end",
                "run_id": f"model-{agent}",
                "metadata": {"lambchat_subagent_id": agent} if agent else {},
                "data": {},
            }
        )
    own_id = child or "search"

    def thoughts(agent):
        return "".join(
            event["data"]["content"]
            for event in emitted
            if event["event"] == "thinking" and event["data"].get("agent_id") == agent
        )

    assert thoughts(own_id) == f"Reason {ACTIVITY_REFERENCE_REMOVED} after"
    assert thoughts("child-b") == "B safe [Act"
    assert (
        "".join(event["data"]["content"] for event in emitted if event["event"] == "message:chunk")
        == "Body verified."
    )


@pytest.mark.parametrize("blocks", [False, True])
async def test_root_model_body_receipts_are_redacted_before_sse_and_output(monkeypatch, blocks):
    emitted = []
    presenter = create_presenter(session_id="session", agent_id="search", agent_name="Search")

    async def emit(event):
        if event["event"] == "message:chunk":
            assert "root_invented.md" not in event["data"]["content"]
        emitted.append(event)

    monkeypatch.setattr(presenter, "emit", emit)
    processor = AgentEventProcessor(presenter)
    for text in [
        "Verified. ```text\n[Act",
        "ivity log saved to: /workspace/root_invented.md]",
        "\n``` Done.",
    ]:
        await processor.process_event(
            {
                "event": "on_chat_model_stream",
                "name": "model",
                "run_id": "root-model",
                "metadata": {},
                "data": {
                    "chunk": AIMessageChunk(
                        content=[{"type": "text", "text": text}] if blocks else text, id="root-text"
                    )
                },
            }
        )
        await processor.flush()
    await processor.process_event(
        {
            "event": "on_chat_model_end",
            "name": "model",
            "run_id": "root-model",
            "metadata": {},
            "data": {},
        }
    )
    streamed = "".join(e["data"]["content"] for e in emitted if e["event"] == "message:chunk")
    assert (
        streamed
        == processor.output_text
        == "Verified. ```text\n[Unverified activity receipt removed.]\n``` Done."
    )


@pytest.mark.parametrize("ending", ["end", "retry", "finalize"])
async def test_root_benign_buffered_suffix_is_counted_once_on_every_finish_path(
    monkeypatch, ending
):
    emitted = []
    outputs_at_emit = []
    presenter = create_presenter(session_id="session", agent_id="search", agent_name="Search")

    async def emit(event):
        emitted.append(event)
        outputs_at_emit.append(processor.output_text)

    monkeypatch.setattr(presenter, "emit", emit)
    processor = AgentEventProcessor(presenter)
    await processor.process_event(
        {
            "event": "on_chat_model_stream",
            "name": "model",
            "run_id": "first",
            "metadata": {},
            "data": {"chunk": AIMessageChunk(content="Benign [Act", id="root-text")},
        }
    )
    if ending == "retry":
        await processor.process_event(
            {
                "event": "on_chat_model_start",
                "name": "model",
                "run_id": "second",
                "metadata": {},
                "data": {},
            }
        )
    elif ending == "end":
        await processor.process_event(
            {
                "event": "on_chat_model_end",
                "name": "model",
                "run_id": "first",
                "metadata": {},
                "data": {},
            }
        )
    else:
        await processor.finalize()
    await processor.flush()
    streamed = "".join(e["data"]["content"] for e in emitted if e["event"] == "message:chunk")
    assert streamed == outputs_at_emit[-1] == "Benign [Act"
    assert processor.output_text == ("" if ending == "finalize" else streamed)


@pytest.mark.parametrize("child", [None, "summary-child"])
@pytest.mark.parametrize("ending", ["end", "retry", "finalize"])
async def test_summary_receipts_are_filtered_on_the_summary_channel_without_body_output(
    monkeypatch, child, ending
):
    emitted = []
    presenter = create_presenter(session_id="session", agent_id="search", agent_name="Search")

    async def emit(event):
        if event["event"] == "summary":
            assert "summary_fake.md" not in event["data"].get("content", "")
        emitted.append(event)

    monkeypatch.setattr(presenter, "emit", emit)
    processor = AgentEventProcessor(presenter)
    metadata = {"lc_source": "summarization", **({"lambchat_subagent_id": child} if child else {})}
    for value in [
        "Context [Act",
        "ivity log saved to: /workspace/summary_fake.md] preserve /workspace/real.txt [Act",
    ]:
        await processor.process_event(
            {
                "event": "on_chat_model_stream",
                "name": "model",
                "run_id": "summary-1",
                "metadata": metadata,
                "data": {
                    "chunk": AIMessageChunk(
                        content=[{"type": "text", "text": value}], id="summary-text"
                    )
                },
            }
        )
        await processor.flush()
    if ending == "end":
        await processor.process_event(
            {
                "event": "on_chat_model_end",
                "name": "model",
                "run_id": "summary-1",
                "metadata": metadata,
                "data": {},
            }
        )
    elif ending == "retry":
        await processor.process_event(
            {
                "event": "on_chat_model_start",
                "name": "model",
                "run_id": "summary-2",
                "metadata": metadata,
                "data": {},
            }
        )
        await processor.flush()
    else:
        await processor.finalize()
    content = "".join(e["data"].get("content", "") for e in emitted if e["event"] == "summary")
    assert (
        content
        == "Context [Unverified activity receipt removed.] preserve /workspace/real.txt [Act"
    )
    assert not any(e["event"] == "message:chunk" for e in emitted)
    assert processor.output_text == ""
