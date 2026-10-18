"""Only successful activity writes may add the reserved activity-log footer."""

from types import SimpleNamespace

import pytest
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.infra.agent.middleware.subagent_activity import SubagentActivityMiddleware


@pytest.mark.parametrize("write_mode", ["no_activity", "success", "failure"])
@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("blocks", [False, True])
async def test_model_cannot_claim_an_activity_log_that_the_middleware_did_not_write(
    write_mode, wrapped, blocks
):
    fake = "/workspace/session/subagent_activity/activity_invented.md"
    text = f"Review complete. See /workspace/session/report.md.\n\n[Activity log saved to: {fake}]"
    content = [{"type": "text", "text": text}] if blocks else text
    original = AIMessage(
        content=content,
        id="final",
        usage_metadata={"input_tokens": 2000, "output_tokens": 60, "total_tokens": 2060},
        response_metadata={"model_name": "test-model"},
        additional_kwargs={"preserve": True},
    )
    extra = ToolMessage("Structured output", tool_call_id="structured")
    response = ModelResponse(result=[original, extra], structured_response={"ok": True})
    writes = []

    class Backend:
        work_dir = "/workspace/session"

        async def awrite(self, path, content):
            writes.append(path)
            return SimpleNamespace(error="Unavailable" if write_mode == "failure" else None)

    async def handler(request):
        return response if wrapped else original

    messages = [HumanMessage("Continue from your own history")]
    if write_mode != "no_activity":
        messages.append(ToolMessage("Verified evidence", tool_call_id="read"))
    result = await SubagentActivityMiddleware(
        backend=Backend(), run_id_factory=lambda: "verified"
    ).awrap_model_call(SimpleNamespace(state={"messages": messages}), handler)
    message = result.result[0] if wrapped else result

    assert fake not in message.text
    assert "Review complete. See /workspace/session/report.md." in message.text
    assert message.text.count("Activity log saved to:") == int(write_mode == "success")
    if write_mode == "success":
        assert writes == ["/workspace/session/subagent_activity/activity_verified.md"]
        assert writes[0] in message.text
    assert message.usage_metadata == original.usage_metadata
    assert message.response_metadata == original.response_metadata
    assert message.additional_kwargs == original.additional_kwargs
    assert original.content == content
    if wrapped:
        assert result.structured_response == {"ok": True}
        assert result.result[1:] == [extra]


@pytest.mark.parametrize("tool_call", [False, True])
@pytest.mark.parametrize("split_blocks", [False, True])
async def test_unclosed_or_split_model_receipts_cannot_reappear_in_final_or_tool_messages(
    tool_call, split_blocks
):
    text = "Verified. [Activity log saved to: /workspace/missing.md"
    content = (
        [
            {"type": "text", "text": "Verified. [Act"},
            {"type": "text", "text": "ivity log saved to: /workspace/missing.md"},
        ]
        if split_blocks
        else text
    )
    original = AIMessage(
        content=content,
        tool_calls=[{"id": "read", "name": "read_file", "args": {}}] if tool_call else [],
    )

    async def handler(request):
        return original

    result = await SubagentActivityMiddleware(backend=None).awrap_model_call(
        SimpleNamespace(state={"messages": []}), handler
    )
    assert result.text == "Verified. [Unverified activity receipt removed.]"
    assert result.tool_calls == original.tool_calls
    assert original.content == content


@pytest.mark.parametrize("closed", [False, True])
async def test_removed_receipt_leaves_one_idempotent_notice_and_preserves_signed_blocks(closed):
    raw = AIMessage(
        content=[
            {
                "type": "thinking",
                "thinking": "signed raw [Activity log saved to: /workspace/raw.md]",
                "signature": "keep",
            },
            {"type": "text", "text": "```text\n[Act"},
            {
                "type": "text",
                "text": "ivity log saved to: /workspace/fake.md" + ("]\n```" if closed else ""),
            },
        ],
        id="preserve",
        response_metadata={"model": "same"},
        usage_metadata={"input_tokens": 9, "output_tokens": 3, "total_tokens": 12},
    )
    before = raw.model_dump()
    sanitized = SubagentActivityMiddleware._strip_model_references(raw)
    assert sanitized.text.count("[Unverified activity receipt removed.]") == 1
    assert "/workspace/fake.md" not in sanitized.text
    assert sanitized.content[0] == raw.content[0]
    assert (
        sanitized.id == raw.id
        and sanitized.usage_metadata == raw.usage_metadata
        and sanitized.response_metadata == raw.response_metadata
    )
    assert SubagentActivityMiddleware._strip_model_references(sanitized) is sanitized
    assert raw.model_dump() == before


@pytest.mark.parametrize("wrapped", [False, True])
async def test_root_response_middleware_sanitizes_checkpoint_text_without_writing_logs(wrapped):
    from src.infra.agent.middleware import subagent_activity as module

    cleaner = getattr(module, "ActivityReferenceMiddleware", None)
    assert cleaner is not None, (
        "Root needs response-only cleaning before native checkpoint persistence"
    )
    original = AIMessage(
        content="Answer [Activity log saved to: /workspace/fake.md]",
        id="keep",
        tool_calls=[{"id": "call", "name": "read_file", "args": {"path": "/workspace/real.md"}}],
        usage_metadata={"input_tokens": 9, "output_tokens": 3, "total_tokens": 12},
    )
    second = AIMessage(content="[Activity log saved to: /workspace/fake2.md]")
    extra = ToolMessage("actual tool evidence", tool_call_id="other")
    response = (
        ModelResponse(result=[original, extra, second], structured_response={"ok": True})
        if wrapped
        else original
    )

    async def handler(request):
        return response

    result = await cleaner().awrap_model_call(SimpleNamespace(state={"messages": [extra]}), handler)
    messages = result.result if wrapped else [result]
    assert messages[0].text == "Answer [Unverified activity receipt removed.]"
    assert (
        messages[0].id == original.id
        and messages[0].tool_calls == original.tool_calls
        and messages[0].usage_metadata == original.usage_metadata
    )
    assert original.text.endswith("/workspace/fake.md]")
    if wrapped:
        assert messages[1] is extra
        assert messages[2].text == "[Unverified activity receipt removed.]"
        assert result.structured_response == {"ok": True}


@pytest.mark.parametrize("write_error", [None, "disk unavailable"])
async def test_fork_inherits_root_cleaner_without_stripping_successful_child_receipt(write_error):
    from deepagents import create_deep_agent
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult

    from src.infra.agent.middleware import subagent_activity as module

    cleaner = getattr(module, "ActivityReferenceMiddleware", None)
    assert cleaner is not None
    writes = []

    class Backend:
        work_dir = "/workspace/session"

        async def awrite(self, path, content):
            writes.append((path, content))
            return SimpleNamespace(error=write_error)

    class Model(BaseChatModel):
        @property
        def _llm_type(self):
            return "receipt-composition-test"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            child = any(m.type == "system" and "CHILD_PROBE" in str(m.content) for m in messages)
            if child:
                if not any(isinstance(m, ToolMessage) and m.name == "read_file" for m in messages):
                    message = AIMessage(
                        content="Child [Activity log saved to: /workspace/child_fake.md]",
                        tool_calls=[
                            {
                                "id": "read",
                                "name": "read_file",
                                "args": {"file_path": "/missing.txt"},
                            }
                        ],
                    )
                else:
                    message = AIMessage(
                        content=[
                            {
                                "type": "thinking",
                                "thinking": "signed reasoning",
                                "signature": "keep",
                            },
                            {
                                "type": "text",
                                "text": "Child verified [Activity log saved to: /workspace/child_fake.md]",
                            },
                        ],
                        usage_metadata={"input_tokens": 9, "output_tokens": 3, "total_tokens": 12},
                    )
            elif not any(isinstance(m, ToolMessage) and m.name == "task" for m in messages):
                message = AIMessage(
                    content="Root [Activity log saved to: /workspace/root_fake.md]",
                    tool_calls=[
                        {
                            "id": "delegate",
                            "name": "task",
                            "args": {
                                "description": "Review the contract",
                                "subagent_type": "child",
                            },
                        }
                    ],
                )
            else:
                message = AIMessage(
                    content="Root verified [Activity log saved to: /workspace/root_fake.md]"
                )
            return ChatResult(generations=[ChatGeneration(message=message)])

    graph = create_deep_agent(
        model=Model(),
        middleware=[cleaner()],
        subagents=[
            {
                "name": "child",
                "description": "Contract reviewer",
                "mode": "fork",
                "system_prompt": "CHILD_PROBE",
                "middleware": [
                    SubagentActivityMiddleware(backend=Backend(), run_id_factory=lambda: "verified")
                ],
            }
        ],
    )
    result = await graph.ainvoke({"messages": [HumanMessage("Review the contract")]})
    reports = [m for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "task"]
    assert reports
    report = str(reports[-1].content)
    assert "child_fake.md" not in report and "[Unverified activity receipt removed.]" in report
    assert report.count("[Activity log saved to:") == int(write_error is None)
    assert writes and writes[-1][0].endswith("activity_verified.md")
    for m in result["messages"]:
        if isinstance(m, AIMessage):
            assert "root_fake.md" not in m.text
    assert result["messages"][-1].text == "Root verified [Unverified activity receipt removed.]"


async def test_persistent_assembly_keeps_current_verified_receipt_on_same_child_continuation():
    from langchain_core.tools import tool
    from langgraph.checkpoint.memory import InMemorySaver

    from src.infra.agent.subagent_assembly import assemble_subagent_sessions
    from tests.agents.core.test_fork_subagent_contract import _ScriptedChatModel

    writes = []

    class Backend:
        work_dir = "/workspace/session"

        async def awrite(self, path, content):
            writes.append((path, content))
            return SimpleNamespace(error=None)

    @tool
    def review_contract() -> str:
        """Return controlled test evidence."""
        return "Contract evidence"

    model = _ScriptedChatModel(
        script=[
            message
            for turn in (1, 2)
            for message in [
                AIMessage(
                    content="",
                    tool_calls=[{"id": f"review-{turn}", "name": "review_contract", "args": {}}],
                ),
                AIMessage(content=f"Reviewed {turn}. [Activity log saved to: /workspace/fake.md]"),
            ]
        ]
    )
    ids = iter(["11111111", "22222222"])
    saver = InMemorySaver()
    sessions, _ = assemble_subagent_sessions(
        session_id="parent",
        user_id="owner",
        specs={
            "reviewer": {
                "name": "reviewer",
                "description": "Contract reviewer",
                "system_prompt": "Review independently",
                "tools": [review_contract],
                "middleware": [
                    SubagentActivityMiddleware(backend=Backend(), run_id_factory=lambda: next(ids))
                ],
            }
        },
        model=model,
        backend=None,
        tools=[],
        checkpointer=saver,
        store=None,
        system_prompt="Parent",
        fallback_model=None,
        thinking=None,
    )
    try:
        first = await sessions.start(
            "reviewer", "First review", call_id="task-1", config={}, background=True
        )
        cid = first["subagent_id"]
        for turn in (1, 2):
            if turn == 2:
                await sessions.send(cid, "Add retry constraints", config={}, background=True)
            result = await sessions.wait(cid, config={})
            assert result["status"] == "completed"
            assert result["result"].count("[Unverified activity receipt removed.]") == 1
            assert "fake.md" not in result["result"]
            assert result["result"].count("[Activity log saved to:") == 1
            assert writes[-1][0] in result["result"]
        assert len(writes) == 2 and writes[0][0] != writes[1][0]
        snapshot = await sessions.graphs[cid].aget_state(sessions.configs[cid])
        ai = [
            m for m in snapshot.values["messages"] if isinstance(m, AIMessage) and not m.tool_calls
        ]
        assert len(ai) == 2 and all("fake.md" not in m.text for m in ai)
        assert all(m.text.count("[Activity log saved to:") == 1 for m in ai)
    finally:
        await sessions.close()
