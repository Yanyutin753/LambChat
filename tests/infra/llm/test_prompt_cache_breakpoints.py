"""Tests for the Anthropic prompt-cache breakpoint placement."""

from __future__ import annotations

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
    # Previous-turn boundary segment is below the minimum cacheable size.
    assert not _marked(result[1])
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
    tools = bound.kwargs["tools"]
    assert len(tools) == 2
    assert tools[-1].get("cache_control") == {"type": "ephemeral"}
    assert all("cache_control" not in t for t in tools[:-1])


def test_bind_tools_skips_breakpoint_when_tools_segment_too_small() -> None:
    # tools 序列化后不足最小可缓存段（~1024 token），加断点只会被服务端忽略
    bound = _bind([_tool("alpha", "tiny")])
    assert all("cache_control" not in t for t in bound.kwargs["tools"])


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
    last = bound.kwargs["tools"][-1]
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
    assert all("cache_control" not in t for t in bound.kwargs["tools"])
