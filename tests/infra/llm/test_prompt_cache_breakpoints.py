"""Tests for the Anthropic prompt-cache breakpoint placement."""

from __future__ import annotations

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.infra.llm.anthropic_chat import _apply_prompt_cache_control


def _marked(message) -> bool:
    content = message.content
    if not isinstance(content, list) or not content:
        return False
    return bool(content[-1].get("cache_control"))


def test_short_conversation_gets_system_and_final_breakpoints_only() -> None:
    messages = [
        SystemMessage(content="system prompt"),
        HumanMessage(content="hi"),
        AIMessage(content="hello"),
    ]
    result = _apply_prompt_cache_control(messages)
    assert _marked(result[0])
    assert not _marked(result[1])
    # The original user request has no completed turn before it.
    assert _marked(result[2])


def test_long_conversation_gets_previous_turn_boundary_breakpoint() -> None:
    big = "x" * 5000
    messages = [
        SystemMessage(content="system prompt"),
        HumanMessage(content=big),
        AIMessage(content=big),
        # newest turn
        HumanMessage(content="new question"),
    ]
    result = _apply_prompt_cache_control(messages)
    assert _marked(result[0])  # system
    assert _marked(result[2])  # end of previous turn
    assert _marked(result[3])  # final message
    assert not _marked(result[1])


def test_final_breakpoint_falls_back_to_content_bearing_message() -> None:
    messages = [
        SystemMessage(content="system prompt"),
        HumanMessage(content="do it"),
        AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}]),
        ToolMessage(content="result", tool_call_id="1"),
        # empty-content trailing AIMessage (pure tool-call turn end)
        AIMessage(content="", tool_calls=[{"name": "u", "args": {}, "id": "2"}]),
    ]
    result = _apply_prompt_cache_control(messages)
    # The trailing empty AIMessage cannot carry a breakpoint; the nearest
    # message with content blocks (the ToolMessage) gets it instead.
    assert not _marked(result[4])
    assert _marked(result[3])


def test_input_messages_are_not_mutated() -> None:
    messages = [
        SystemMessage(content="system prompt"),
        HumanMessage(content="hi"),
        AIMessage(content="hello"),
    ]
    originals = [m.content for m in messages]
    _apply_prompt_cache_control(messages)
    assert [m.content for m in messages] == originals


# ── tools 块缓存断点（跨会话/子代理复用 system+tools 前缀）──────────────


def _bind(tools):
    from pydantic import SecretStr

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    model = LambChatAnthropicChatModel(model_name="claude-sonnet-4-5", api_key=SecretStr("sk-test"))
    return model.bind_tools(tools)


def _tool_payload(bound):
    return bound.bound._get_request_payload(
        [SystemMessage(content="Current policy."), HumanMessage(content="Review.")],
        **bound.kwargs,
    )["tools"]


def _tool(name: str, description: str):
    from langchain_core.tools import tool

    @tool(description=description)
    def sample(payload: str) -> str:
        return payload

    sample.name = name
    return sample


BIG_DESC = "x" * 4000


def test_bind_tools_marks_last_tool_with_cache_control() -> None:
    bound = _bind([_tool("alpha", BIG_DESC), _tool("beta", BIG_DESC)])
    tools = _tool_payload(bound)
    assert len(tools) == 2
    assert tools[-1].get("cache_control") == {"type": "ephemeral"}
    assert all("cache_control" not in t for t in tools[:-1])


def test_small_tools_prefix_leaves_minimum_length_to_the_provider() -> None:
    bound = _bind([_tool("alpha", "tiny")])
    tools = _tool_payload(bound)
    assert tools[0]["description"] == "tiny"
    assert tools[-1].get("cache_control") == {"type": "ephemeral"}


def test_bind_tools_preserves_explicit_cache_control() -> None:
    from langchain_core.tools import tool

    @tool
    def marked(payload: str) -> str:
        """Explicitly marked tool."""

    marked.name = "marked"
    explicit = [
        {
            "name": "marked",
            "description": BIG_DESC,
            "input_schema": {"type": "object", "properties": {}},
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]
    bound = _bind(explicit)
    last = _tool_payload(bound)[-1]
    assert last["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_bind_tools_respects_enable_prompt_cache_disabled() -> None:
    from pydantic import SecretStr

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    model = LambChatAnthropicChatModel(
        model_name="claude-sonnet-4-5",
        api_key=SecretStr("sk-test"),
        enable_prompt_cache=False,
    )
    bound = model.bind_tools([_tool("alpha", BIG_DESC)])
    assert all("cache_control" not in t for t in _tool_payload(bound))


def test_short_previous_answer_retains_anchor_across_many_small_tool_steps() -> None:
    from pydantic import SecretStr

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    messages = [
        SystemMessage(content="Review the full conversation and tool evidence. " * 150),
        HumanMessage(content="Keep the tenant isolation and idempotency evidence. " * 300),
        AIMessage(content="Understood."),
        HumanMessage(content="Verify the next batch."),
    ]
    for index in range(12):
        messages.extend(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "check", "args": {}, "id": f"check-{index}"}],
                ),
                ToolMessage(content="ok", tool_call_id=f"check-{index}"),
            ]
        )
    originals = [message.model_dump() for message in messages]
    model = LambChatAnthropicChatModel(model_name="claude-sonnet-4-5", api_key=SecretStr("sk-test"))
    payload = model._get_request_payload(model._prepare(messages))
    # The prior request's entry is beyond the final breakpoint's 20-block lookback.
    assert sum(len(message["content"]) for message in payload["messages"][2:]) > 20
    previous_answer = payload["messages"][1]
    assert previous_answer["role"] == "assistant"
    assert isinstance(previous_answer["content"], list), "Previous-turn cache anchor missing"
    assert previous_answer["content"][0]["text"] == "Understood."
    assert previous_answer["content"][0].get("cache_control") == {"type": "ephemeral"}
    assert [message.model_dump() for message in messages] == originals


@pytest.mark.parametrize(
    "block",
    [
        {"type": "thinking", "thinking": "Check the invariant.", "signature": "test"},
        {"type": "redacted_thinking", "data": "test"},
        {"type": "reasoning", "reasoning": "Check the invariant."},
        {"type": "text", "text": ""},
    ],
)
def test_cache_anchors_fall_back_past_reasoning_and_empty_text(block) -> None:
    messages = [
        SystemMessage(content="Review all current evidence. " * 200),
        HumanMessage(content="Original review request."),
        AIMessage(content=[block]),
        HumanMessage(content="New review request."),
        AIMessage(content=[block]),
    ]
    originals = [message.model_dump() for message in messages]
    result = _apply_prompt_cache_control(messages)
    assert all("cache_control" not in item for index in (2, 4) for item in result[index].content)
    assert _marked(result[1])
    assert _marked(result[3])
    assert [message.model_dump() for message in messages] == originals


def test_cache_anchor_keeps_reasoning_unmarked_after_eligible_text() -> None:
    messages = [
        SystemMessage(content="Review all current evidence. " * 200),
        HumanMessage(content="Original request."),
        AIMessage(
            content=[
                {"type": "text", "text": "Understood."},
                {"type": "thinking", "thinking": "Keep checking.", "signature": "test"},
            ]
        ),
        HumanMessage(content="Next request."),
    ]
    originals = [message.model_dump() for message in messages]
    result = _apply_prompt_cache_control(messages)
    assert result[2].content[0].get("cache_control") == {"type": "ephemeral"}
    assert "cache_control" not in result[2].content[1]
    assert [message.model_dump() for message in messages] == originals


class _CapturedCacheRequestError(Exception):
    pass


@pytest.fixture
def captured_cache_requests(monkeypatch):
    from unittest.mock import AsyncMock

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    payloads = []

    async def capture(self, payload):
        payloads.append(payload)
        raise _CapturedCacheRequestError

    monkeypatch.setattr(LambChatAnthropicChatModel, "_acreate", capture)
    monkeypatch.setattr(LambChatAnthropicChatModel, "_quota_begin", AsyncMock(return_value=None))
    return payloads


def _payload_cache_controls(payload):
    blocks = list(payload.get("tools", []))
    if isinstance(payload.get("system"), list):
        blocks.extend(payload["system"])
    for message in payload.get("messages", []):
        if isinstance(message.get("content"), list):
            blocks.extend(message["content"])
    return [block["cache_control"] for block in blocks if "cache_control" in block]


@pytest.mark.parametrize(
    "policy_owner", ["message", "tools", "request", "model_kwargs", "model_tools"]
)
@pytest.mark.parametrize("streaming", [False, True])
async def test_explicit_cache_policy_is_preserved_without_extra_default_markers(
    policy_owner, streaming, captured_cache_requests
) -> None:
    from copy import deepcopy

    from pydantic import SecretStr

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    control = {"type": "ephemeral", "ttl": "1h"}
    tools = [{"name": "check", "description": BIG_DESC, "input_schema": {"type": "object"}}]
    messages = [SystemMessage(content="Current policy."), HumanMessage(content="Review.")]
    kwargs = {}
    model_kwargs = {}
    if policy_owner == "message":
        messages[-1] = HumanMessage(
            content=[{"type": "text", "text": "Review.", "cache_control": control}]
        )
    elif policy_owner == "tools":
        tools[-1]["cache_control"] = control
    elif policy_owner == "model_tools":
        tools[-1]["cache_control"] = control
        model_kwargs["tools"] = tools
    elif policy_owner == "request":
        kwargs["cache_control"] = control
    else:
        model_kwargs["cache_control"] = control
    originals = [message.model_dump() for message in messages]
    original_tools = deepcopy(tools)
    model = LambChatAnthropicChatModel(
        model_name="claude-sonnet-4-5",
        api_key=SecretStr("sk-test"),
        model_kwargs=model_kwargs,
    )
    caller = model if policy_owner == "model_tools" else model.bind_tools(tools)
    with pytest.raises(_CapturedCacheRequestError):
        if streaming:
            async for _ in caller.astream(messages, **kwargs):
                pass
        else:
            await caller.ainvoke(messages, **kwargs)
    assert len(captured_cache_requests) == 1
    payload = captured_cache_requests[0]
    if policy_owner in {"request", "model_kwargs"}:
        assert payload["cache_control"] == control
        assert _payload_cache_controls(payload) == []
    else:
        assert _payload_cache_controls(payload) == [control]
    assert [message.model_dump() for message in messages] == originals
    assert tools == original_tools


async def test_four_explicit_tool_breakpoints_do_not_gain_default_message_markers(
    captured_cache_requests,
) -> None:
    from pydantic import SecretStr

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    control = {"type": "ephemeral"}
    tools = [
        {
            "name": f"check_{index}",
            "description": "Check one invariant.",
            "input_schema": {"type": "object"},
            "cache_control": control,
        }
        for index in range(4)
    ]
    model = LambChatAnthropicChatModel(model_name="claude-sonnet-4-5", api_key=SecretStr("sk-test"))
    with pytest.raises(_CapturedCacheRequestError):
        await model.bind_tools(tools).ainvoke(
            [SystemMessage(content="Check current evidence."), HumanMessage(content="Review.")]
        )
    assert len(_payload_cache_controls(captured_cache_requests[0])) == 4


@pytest.mark.parametrize("streaming", [False, True])
async def test_default_request_retains_four_cache_anchors_and_original_inputs(
    streaming, captured_cache_requests
) -> None:
    from copy import deepcopy

    from pydantic import SecretStr

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    tools = [{"name": "check", "description": BIG_DESC, "input_schema": {"type": "object"}}]
    messages = [
        SystemMessage(content="Keep all original evidence. " * 200),
        HumanMessage(content="Original request."),
        AIMessage(content="Understood."),
        HumanMessage(content="Next request."),
    ]
    originals = [message.model_dump() for message in messages]
    original_tools = deepcopy(tools)
    model = LambChatAnthropicChatModel(model_name="claude-sonnet-4-5", api_key=SecretStr("sk-test"))
    with pytest.raises(_CapturedCacheRequestError):
        if streaming:
            async for _ in model.bind_tools(tools).astream(messages):
                pass
        else:
            await model.bind_tools(tools).ainvoke(messages)
    payload = captured_cache_requests[0]
    assert len(_payload_cache_controls(payload)) == 4
    assert payload["messages"][1]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert [message.model_dump() for message in messages] == originals
    assert tools == original_tools


@pytest.mark.parametrize("streaming", [False, True])
async def test_native_agent_cache_policy_keeps_its_budget_and_ttl(
    streaming, captured_cache_requests
) -> None:
    from langchain.agents.middleware.types import ModelRequest
    from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
    from pydantic import SecretStr

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    model = LambChatAnthropicChatModel(model_name="claude-sonnet-4-5", api_key=SecretStr("sk-test"))
    request = ModelRequest(
        model=model,
        system_message=SystemMessage(content="Review original evidence."),
        messages=[
            HumanMessage(content="Original request."),
            AIMessage(content="Prior detailed observations. " * 200),
            HumanMessage(content="Continue."),
        ],
        tools=[_tool("check", "Check one invariant.")],
    )
    middleware = AnthropicPromptCachingMiddleware(ttl="1h")

    async def handler(prepared):
        caller = prepared.model.bind_tools(prepared.tools)
        messages = [prepared.system_message, *prepared.messages]
        if streaming:
            async for _ in caller.astream(messages, **prepared.model_settings):
                pass
        else:
            await caller.ainvoke(messages, **prepared.model_settings)

    with pytest.raises(_CapturedCacheRequestError):
        await middleware.awrap_model_call(request, handler)
    payload = captured_cache_requests[0]
    control = {"type": "ephemeral", "ttl": "1h"}
    assert payload["cache_control"] == control
    assert _payload_cache_controls(payload) == [control, control]
    assert isinstance(request.system_message.content, str)
    assert not request.tools[0].extras
    assert request.model_settings == {}


@pytest.mark.parametrize("enabled", [False, True])
def test_request_payload_uses_the_same_cache_entrypoint(enabled) -> None:
    from pydantic import SecretStr

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    model = LambChatAnthropicChatModel(
        model_name="claude-sonnet-4-5",
        api_key=SecretStr("sk-test"),
        enable_prompt_cache=enabled,
    )
    bound = model.bind_tools([_tool("check", "tiny")])
    payload = model._get_request_payload(
        [
            SystemMessage(content="Original policy."),
            HumanMessage(content="Original request."),
            AIMessage(content="Understood."),
            HumanMessage(content="Continue."),
        ],
        **bound.kwargs,
    )
    assert len(_payload_cache_controls(payload)) == (4 if enabled else 0)
