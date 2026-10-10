from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.infra.llm.client import LLMClient, model_supports_thinking
from src.infra.llm.reasoning_patch import apply_reasoning_patches


def history():
    return [
        HumanMessage(content="Calculate 1+1"),
        AIMessage(
            content="",
            tool_calls=[{"name": "calculator", "args": {}, "id": "call_test", "type": "tool_call"}],
        ),
        ToolMessage(content="2", tool_call_id="call_test"),
    ]


@pytest.mark.parametrize("provider", ["deepseek", "anthropic"])
def test_deepseek_cross_model_tool_history_retains_thinking(provider):
    model = LLMClient._create_model(
        provider, "deepseek-flash", api_key="test", thinking={"type": "enabled", "level": "max"}
    )
    messages = history()
    original = deepcopy(messages)
    payload = model._get_request_payload(messages)
    assistant = next(m for m in payload["messages"] if m["role"] == "assistant")
    if provider == "anthropic":
        assert assistant["content"][0] == {"type": "thinking", "thinking": "", "signature": ""}
        assert payload["thinking"]["type"] == "enabled"
        assert payload["output_config"]["effort"] == "max"
    else:
        assert assistant["reasoning_content"] == ""
        assert payload["reasoning_effort"] == "max"
    assert messages == original


def test_deepseek_plain_history_preserves_actual_reasoning():
    apply_reasoning_patches()
    model = LLMClient._create_model("deepseek", "deepseek-flash", api_key="test")
    message = AIMessage(
        content="2",
        additional_kwargs={"reasoning_content": "actual reasoning"},
        response_metadata={"model_name": "deepseek-flash"},
    )
    payload = model._get_request_payload(
        [HumanMessage(content="1+1"), message, HumanMessage(content="Continue")]
    )
    assert payload["messages"][1]["reasoning_content"] == "actual reasoning"


def test_deepseek_anthropic_preserves_existing_thinking():
    model = LLMClient._create_model("anthropic", "deepseek-flash", api_key="test")
    block = {"type": "thinking", "thinking": "actual reasoning", "signature": "original-signature"}
    message = AIMessage(content=[block, {"type": "text", "text": "2"}])
    payload = model._get_request_payload([HumanMessage(content="1+1"), message])
    assert payload["messages"][1]["content"][0] == block


@pytest.mark.parametrize(
    "provider,name", [("openai", "gpt-4o"), ("anthropic", "claude-sonnet-4-5")]
)
def test_other_models_do_not_receive_empty_reasoning(provider, name):
    model = LLMClient._create_model(provider, name, api_key="test")
    payload = model._get_request_payload(history())
    assistant = next(m for m in payload["messages"] if m["role"] == "assistant")
    assert "reasoning_content" not in assistant
    if isinstance(assistant["content"], list):
        assert all(b["type"] != "thinking" for b in assistant["content"])


def test_anthropic_deepseek_exposes_thinking_intensity():
    assert model_supports_thinking("anthropic", "deepseek-flash")


def test_switching_deepseek_history_to_gpt_does_not_leak_reasoning():
    model = LLMClient._create_model("openai", "gpt-4o", api_key="test")
    message = AIMessage(
        content="2",
        additional_kwargs={"reasoning_content": "private reasoning"},
        response_metadata={"model_name": "deepseek-flash"},
    )
    payload = model._get_request_payload([HumanMessage(content="1+1"), message])
    assert "reasoning_content" not in payload["messages"][1]


def test_switching_openai_reasoning_to_anthropic_preserves_it():
    model = LLMClient._create_model("anthropic", "deepseek-flash", api_key="test")
    message = AIMessage(
        content="2",
        additional_kwargs={"reasoning_content": "actual reasoning"},
        response_metadata={"model_name": "deepseek-flash"},
    )
    payload = model._get_request_payload([HumanMessage(content="1+1"), message])
    assert payload["messages"][1]["content"][0]["thinking"] == "actual reasoning"


def test_legacy_deepseek_keeps_tool_continuation_reasoning():
    model = LLMClient._create_model(
        "deepseek", "deepseek-reasoner", api_key="test", api_format="chat_completions"
    )
    messages = history()
    messages[1].additional_kwargs["reasoning_content"] = "legacy reasoning"
    messages[1].response_metadata["model_name"] = "deepseek-reasoner"
    payload = model._get_request_payload(messages)
    assert payload["messages"][1]["reasoning_content"] == "legacy reasoning"


def test_gpt_reasoning_blocks_switched_to_deepseek_anthropic_have_thinking():
    model = LLMClient._create_model("anthropic", "deepseek-flash", api_key="test")
    message = AIMessage(
        content=[
            {"type": "reasoning", "reasoning": "GPT reasoning"},
            {"type": "text", "text": "2"},
        ],
        response_metadata={"model_provider": "openai"},
    )
    payload = model._get_request_payload([HumanMessage(content="1+1"), message])
    assert payload["messages"][1]["content"][0]["type"] == "thinking"
