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
