import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.exceptions import ContextOverflowError, ModelInvalidRequestError
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import Field

from src.infra.agent.middleware.summary_fallback import summarization_fallback_patch


class RecordingModel(GenericFakeChatModel):
    calls: list = Field(default_factory=list)
    native_error: Any = None

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self.bind(tools=tools, tool_choice=tool_choice, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append((messages, kwargs))
        if self.native_error is not None and kwargs.get("tools"):
            raise self.native_error
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def build(model, tmp_path):
    import deepagents.graph as graph

    defaults = {"trigger": ("messages", 3), "keep": ("messages", 1), "truncate_args_settings": None}
    with patch(
        "deepagents.middleware.summarization.compute_summarization_defaults", return_value=defaults
    ):
        with summarization_fallback_patch(None):
            return graph.create_summarization_middleware(model, FilesystemBackend(tmp_path))


async def continued(request):
    return ModelResponse(result=[AIMessage("continued")])


def request_for(model):
    return ModelRequest(
        model=model,
        system_message=SystemMessage("Original agent instructions"),
        messages=[
            HumanMessage("Remember critical decision: preserve data"),
            AIMessage(
                "", tool_calls=[{"id": "read-1", "name": "read_file", "args": {"path": "a"}}]
            ),
            ToolMessage("Verified original file evidence", tool_call_id="read-1"),
            AIMessage("The previous test passed"),
            HumanMessage("Continue with the next task"),
        ],
        tools=[
            {"name": "read_file", "description": "Read a file", "parameters": {"type": "object"}}
        ],
    )


async def test_summary_reuses_native_system_tools_and_history_without_execution(tmp_path):
    model = RecordingModel(
        messages=iter([AIMessage("Decision: preserve data. Artifact a verified.")])
    )
    middleware = build(model, tmp_path)
    request = request_for(model)
    response = await middleware.awrap_model_call(request, continued)
    [messages, kwargs] = model.calls[0]
    assert messages[:-1] == [request.system_message, *request.messages[:-1]]
    assert kwargs["tools"] == request.tools
    assert kwargs["tool_choice"] == "none"
    assert request.tool_choice is None
    assert "SESSION INTENT" in messages[-1].content
    assert "ARTIFACTS" in messages[-1].content
    assert "media_reference_information" in messages[-1].content
    current_instructions = messages[-1].content.split("</messages>")[-1]
    assert "do not execute tools" in current_instructions
    assert "identifiers" in current_instructions
    assert (
        "Decision: preserve data"
        in response.command.update["_summarization_event"]["summary_message"].content
    )
    assert request.messages[0].content == "Remember critical decision: preserve data"
    assert not any(message.content == "continued" for message in request.messages)
    assert len(list(tmp_path.rglob("*.md"))) == 1


@pytest.mark.parametrize("failure", ["overflow", "unsupported_tool_choice", "tool_call", "empty"])
async def test_native_summary_recovers_with_original_summary_path(tmp_path, failure):
    bad = AIMessage("")
    if failure == "tool_call":
        bad = AIMessage("", tool_calls=[{"id": "do-not-execute", "name": "read_file", "args": {}}])
    model = RecordingModel(messages=iter([bad, AIMessage("Safe conventional summary")]))
    if failure in {"overflow", "unsupported_tool_choice"}:
        model.native_error = (
            ContextOverflowError("too large")
            if failure == "overflow"
            else ModelInvalidRequestError("tool_choice none is unsupported")
        )
        model.messages = iter([AIMessage("Safe conventional summary")])
    middleware = build(model, tmp_path)
    result = await middleware.awrap_model_call(request_for(model), continued)
    assert len(model.calls) == 2
    assert model.calls[0][1]["tool_choice"] == "none"
    assert not model.calls[1][1].get("tools")
    fallback_instructions = model.calls[1][0][-1].content.split("</messages>")[-1]
    assert "do not execute tools" in fallback_instructions
    assert "identifiers" in fallback_instructions
    assert (
        "Safe conventional summary"
        in result.command.update["_summarization_event"]["summary_message"].content
    )


async def test_summary_outside_model_call_keeps_original_path(tmp_path):
    model = RecordingModel(messages=iter([AIMessage("Manual summary")]))
    middleware = build(model, tmp_path)
    assert (
        await middleware._acreate_summary([HumanMessage("Manual compaction")]) == "Manual summary"
    )
    assert not model.calls[0][1].get("tools")


async def test_nested_factory_protection_does_not_attempt_native_summary_twice(tmp_path):
    from src.infra.agent.middleware.summary_fallback import _reuse_summary_prefix

    bad = AIMessage("", tool_calls=[{"id": "never-execute", "name": "read_file", "args": {}}])
    model = RecordingModel(messages=iter([bad, AIMessage("Conventional summary")]))
    middleware = build(model, tmp_path)
    _reuse_summary_prefix(middleware)
    result = await middleware.awrap_model_call(request_for(model), continued)
    assert len(model.calls) == 2
    assert model.calls[0][1].get("tools")
    assert not model.calls[1][1].get("tools")
    assert (
        "Conventional summary"
        in result.command.update["_summarization_event"]["summary_message"].content
    )


async def test_failed_main_request_reuses_its_summary_without_duplicate_stats(
    tmp_path, monkeypatch
):
    summaries = []

    async def emit(_counter, _messages, summary):
        summaries.append(summary)

    monkeypatch.setattr("src.infra.agent.middleware.summary_stats._emit_freed_tokens", emit)
    model = RecordingModel(
        messages=iter([AIMessage("Saved context"), AIMessage("Unneeded repeat")])
    )
    middleware = build(model, tmp_path)
    request = request_for(model)

    async def failure(_request):
        raise TimeoutError("Transient failure after successful compaction")

    with pytest.raises(TimeoutError):
        await middleware.awrap_model_call(request, failure)
    result = await middleware.awrap_model_call(request, continued)
    assert len(model.calls) == 1
    assert summaries == ["Saved context"]
    assert (
        "Saved context" in result.command.update["_summarization_event"]["summary_message"].content
    )


@pytest.mark.parametrize("changed", ["system", "tools", "tool_choice", "settings", "history"])
async def test_summary_retry_reuse_never_ignores_changed_request_input(tmp_path, changed):
    model = RecordingModel(
        messages=iter([AIMessage("First context"), AIMessage("Changed context")])
    )
    middleware = build(model, tmp_path)
    first = request_for(model)
    await middleware.awrap_model_call(first, continued)
    if changed == "system":
        second = first.override(system_message=SystemMessage("Different private instructions"))
    elif changed == "tools":
        second = first.override(tools=[{**first.tools[0], "description": "Changed authorization"}])
    elif changed == "settings":
        second = first.override(model_settings={"temperature": 0.2})
    elif changed == "tool_choice":
        second = first.override(tool_choice="auto")
    else:
        second = first.override(
            messages=[HumanMessage("Different source evidence"), *first.messages[1:]]
        )
    result = await middleware.awrap_model_call(second, continued)
    assert len(model.calls) == 2
    assert (
        "Changed context"
        in result.command.update["_summarization_event"]["summary_message"].content
    )


async def test_identical_history_in_another_thread_never_reuses_summary(tmp_path):
    from langchain_core.runnables import RunnableLambda

    model = RecordingModel(
        messages=iter([AIMessage("Tenant A context"), AIMessage("Tenant B context")])
    )
    middleware = build(model, tmp_path)

    async def run(_):
        return await middleware.awrap_model_call(request_for(model), continued)

    first = await RunnableLambda(run).ainvoke(
        {}, config={"configurable": {"thread_id": "tenant-a"}}
    )
    second = await RunnableLambda(run).ainvoke(
        {}, config={"configurable": {"thread_id": "tenant-b"}}
    )
    assert len(model.calls) == 2
    assert (
        "Tenant A context"
        in first.command.update["_summarization_event"]["summary_message"].content
    )
    assert (
        "Tenant B context"
        in second.command.update["_summarization_event"]["summary_message"].content
    )


async def test_summary_with_model_without_tool_binding_keeps_original_path(tmp_path):
    class NoToolsModel(RecordingModel):
        def bind_tools(self, tools, **kwargs):
            raise NotImplementedError

    model = NoToolsModel(messages=iter([AIMessage("Unsupported binding summary")]))
    result = await build(model, tmp_path).awrap_model_call(request_for(model), continued)
    assert len(model.calls) == 1
    assert not model.calls[0][1].get("tools")
    assert (
        "Unsupported binding summary"
        in result.command.update["_summarization_event"]["summary_message"].content
    )


async def test_summary_does_not_reuse_another_concurrent_requests_prefix(tmp_path):
    model = RecordingModel(
        messages=iter([AIMessage("Summary A"), AIMessage("Summary B"), AIMessage("Manual")])
    )
    middleware = build(model, tmp_path)
    first, second = request_for(model), request_for(model)
    first = first.override(system_message=SystemMessage("Tenant A"))
    second = second.override(
        system_message=SystemMessage("Tenant B"),
        messages=[HumanMessage("Tenant B private history"), *second.messages[1:]],
    )
    await asyncio.gather(
        middleware.awrap_model_call(first, continued),
        middleware.awrap_model_call(second, continued),
    )
    by_system = {messages[0].content: messages[1].content for messages, _ in model.calls}
    assert by_system == {
        "Tenant A": "Remember critical decision: preserve data",
        "Tenant B": "Tenant B private history",
    }
    await middleware._acreate_summary([HumanMessage("Manual")])
    assert not model.calls[-1][1].get("tools")


async def test_summary_counts_system_and_tools_before_using_native_prefix(tmp_path):
    model = RecordingModel(
        messages=iter([AIMessage("Bounded summary")]), profile={"max_input_tokens": 1000}
    )
    middleware = build(model, tmp_path)
    request = request_for(model)
    request = request.override(system_message=SystemMessage("Large system instructions. " * 600))

    with pytest.raises(ContextOverflowError):
        await middleware.awrap_model_call(request, continued)
    assert len(model.calls) == 1
    assert not model.calls[0][1].get("tools")


@pytest.mark.parametrize("unhashable", [False, True])
async def test_deep_agent_summary_uses_the_fully_assembled_model_prefix(tmp_path, unhashable):
    from deepagents import create_deep_agent

    from src.infra.agent.middleware.prompt_injection import SectionPromptMiddleware

    class UnhashableSectionPromptMiddleware(SectionPromptMiddleware):
        __hash__ = None

    section_type = UnhashableSectionPromptMiddleware if unhashable else SectionPromptMiddleware
    model = RecordingModel(messages=iter([AIMessage("Summary"), AIMessage("Final answer")]))
    defaults = {
        "trigger": ("messages", 3),
        "keep": ("messages", 1),
        "truncate_args_settings": None,
    }
    with patch(
        "deepagents.middleware.summarization.compute_summarization_defaults", return_value=defaults
    ):
        with summarization_fallback_patch(None):
            graph = create_deep_agent(
                model=model,
                backend=FilesystemBackend(tmp_path),
                system_prompt="Base instructions",
                middleware=[section_type(sections=["Required project rules"])],
            )
    result = await graph.ainvoke({"messages": request_for(model).messages})
    assert result["messages"][-1].content == "Final answer"
    assert len(model.calls) == 2
    summary_messages, summary_kwargs = model.calls[0]
    main_messages, main_kwargs = model.calls[1]
    assert summary_messages[0] == main_messages[0]
    assert "Required project rules" in summary_messages[0].text
    assert summary_kwargs["tools"] == main_kwargs["tools"]
    assert summary_kwargs["tool_choice"] == "none"
    assert main_kwargs["tool_choice"] is None


async def test_persistent_child_summary_uses_its_complete_system_tools_and_history(tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver

    from src.infra.agent.middleware.prompt_injection import SectionPromptMiddleware
    from src.infra.agent.subagent_assembly import assemble_subagent_sessions
    from src.infra.agent.subagent_sessions import SubagentInboxMiddleware

    model = RecordingModel(messages=iter([AIMessage("Child summary"), AIMessage("Child answer")]))
    saver = InMemorySaver()
    sessions, _ = assemble_subagent_sessions(
        session_id="parent",
        user_id="owner",
        specs={
            "researcher": {
                "name": "researcher",
                "description": "Research",
                "system_prompt": "Child rules",
            }
        },
        model=model,
        backend=FilesystemBackend(tmp_path),
        tools=[],
        checkpointer=saver,
        store=None,
        system_prompt="Parent rules",
        fallback_model=None,
        thinking=None,
        child_middleware=lambda: [SectionPromptMiddleware(sections=["Required child rules"])],
    )
    sessions.records["child"] = {"pending": []}
    defaults = {"trigger": ("messages", 3), "keep": ("messages", 1), "truncate_args_settings": None}
    with patch(
        "deepagents.middleware.summarization.compute_summarization_defaults", return_value=defaults
    ):
        graph = await sessions.build_graph("researcher", SubagentInboxMiddleware(sessions, "child"))
    result = await graph.ainvoke(
        {"messages": request_for(model).messages},
        {"configurable": {"thread_id": "child-summary"}},
    )
    assert result["messages"][-1].content == "Child answer"
    assert len(model.calls) == 2
    summary_messages, summary_kwargs = model.calls[0]
    main_messages, main_kwargs = model.calls[1]
    assert summary_messages[0] == main_messages[0]
    assert "Required child rules" in summary_messages[0].text
    assert "Parent communication" in summary_messages[0].text
    assert summary_kwargs["tools"] == main_kwargs["tools"]
    assert summary_kwargs["tool_choice"] == "none"
    assert main_kwargs["tool_choice"] is None


@pytest.mark.parametrize("mode", ["native", "manual", "fallback", "retry"])
async def test_generated_summary_redacts_receipts_before_checkpoint_but_retains_raw_input(
    tmp_path, mode
):
    raw = AIMessage(
        content=[
            {"type": "thinking", "thinking": "signed raw reasoning", "signature": "unchanged"},
            {
                "type": "text",
                "text": "Context [Activity log saved to: /workspace/summary_fake.md] artifact /workspace/real.txt",
            },
        ]
    )
    bad = AIMessage("", tool_calls=[{"id": "never-execute", "name": "read_file", "args": {}}])
    model = RecordingModel(messages=iter(([bad, raw] if mode == "fallback" else [raw])))
    middleware = build(model, tmp_path)
    request = request_for(model)
    request.messages[
        0
    ].content = "Original user quote [Activity log saved to: /workspace/summary_fake.md]"
    original = request.messages[0].content
    if mode == "manual":
        summary = await middleware._acreate_summary(request.messages)
    else:
        if mode == "retry":

            async def failure(_request):
                raise TimeoutError("Failed after generated summary")

            with pytest.raises(TimeoutError):
                await middleware.awrap_model_call(request, failure)
        result = await middleware.awrap_model_call(request, continued)
        summary = result.command.update["_summarization_event"]["summary_message"].content
    assert "[Unverified activity receipt removed.]" in summary and "summary_fake.md" not in summary
    assert "/workspace/real.txt" in summary
    assert request.messages[0].content == original
    assert raw.content[0] == {
        "type": "thinking",
        "thinking": "signed raw reasoning",
        "signature": "unchanged",
    }
    assert (
        raw.content[1]["text"].endswith("artifact /workspace/real.txt")
        and "summary_fake.md" in raw.content[1]["text"]
    )
    assert len(model.calls) == (2 if mode == "fallback" else 1)


async def test_native_summary_disables_tool_selection_without_changing_main_request(tmp_path):
    class ToolSelectingModel(RecordingModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if kwargs.get("tools") and kwargs.get("tool_choice") != "none":
                self.calls.append((messages, kwargs))
                from langchain_core.outputs import ChatGeneration, ChatResult

                return ChatResult(
                    generations=[
                        ChatGeneration(
                            message=AIMessage(
                                "",
                                tool_calls=[
                                    {
                                        "id": "unsafe",
                                        "name": "execute",
                                        "args": {"command": "should never run"},
                                    }
                                ],
                            )
                        )
                    ]
                )
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    model = ToolSelectingModel(messages=iter([AIMessage("Safe replacement context")]))
    request = request_for(model)
    response = await build(model, tmp_path).awrap_model_call(request, continued)
    assert len(model.calls) == 1
    assert model.calls[0][1]["tool_choice"] == "none"
    assert request.tool_choice is None
    assert (
        "Safe replacement context"
        in response.command.update["_summarization_event"]["summary_message"].content
    )


@pytest.mark.parametrize("protocol", ["anthropic", "openai_chat", "openai_responses"])
@pytest.mark.parametrize("original_choice", [None, "auto", "required"])
async def test_summary_no_tools_survives_actual_protocol_payload(
    tmp_path, monkeypatch, protocol, original_choice
):
    from langchain_core.outputs import ChatGeneration, ChatResult

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel
    from src.infra.llm.openai_chat import LambChatOpenAIChatModel

    model = (
        LambChatAnthropicChatModel(
            model="glm-5.3",
            api_key="offline-test",
            max_tokens=4096,
            thinking={"type": "enabled", "budget_tokens": 1024},
        )
        if protocol == "anthropic"
        else LambChatOpenAIChatModel(
            model="gpt-5.4",
            api_key="offline-test",
            use_responses_api=protocol == "openai_responses",
        )
    )
    payloads = []

    async def capture(self, messages, stop=None, run_manager=None, **kwargs):
        payloads.append(self._get_request_payload(messages, stop=stop, **kwargs))
        return ChatResult(generations=[ChatGeneration(message=AIMessage("Verified summary"))])

    monkeypatch.setattr(type(model), "_agenerate", capture)
    middleware = build(model, tmp_path)
    request = request_for(model).override(tool_choice=original_choice)
    await middleware.awrap_model_call(request, continued)
    assert len(payloads) == 1
    assert payloads[0]["tool_choice"] == ({"type": "none"} if protocol == "anthropic" else "none")
    assert payloads[0]["tools"]
    assert request.tool_choice == original_choice
    assert request.model_settings == {}
    if protocol == "anthropic":
        assert payloads[0]["thinking"] == {"type": "enabled", "budget_tokens": 1024}
