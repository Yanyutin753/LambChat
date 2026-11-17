from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.infra.llm.client import LLMClient


@pytest.mark.parametrize("target", ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"])
@pytest.mark.parametrize(
    "provider,source", [("anthropic", "glm-5.2"), ("google_genai", "gemini-4-argon")]
)
def test_foreign_signed_thoughts_become_text_without_changing_tool_history(
    target, provider, source
):
    model = LLMClient._create_model("anthropic", target, api_key="test")
    messages = [
        HumanMessage("Add 137 and 286"),
        AIMessage(
            content=[{"type": "thinking", "thinking": "Use calculator", "signature": "foreign"}],
            tool_calls=[{"name": "calculator", "args": {"a": 137, "b": 286}, "id": "call_1"}],
            response_metadata={"model_provider": provider, "model_name": source},
        ),
        ToolMessage(content="423", tool_call_id="call_1"),
    ]
    before = deepcopy(messages)
    payload = model._get_request_payload(messages)
    assistant = payload["messages"][1]["content"]
    assert not any(b["type"] in {"thinking", "redacted_thinking"} for b in assistant)
    assert any(b.get("text") == "Use calculator" for b in assistant)
    assert [b["id"] for b in assistant if b["type"] == "tool_use"] == ["call_1"]
    assert payload["messages"][2]["content"][0]["tool_use_id"] == "call_1"
    assert messages == before


def test_claude_native_signature_is_preserved_across_claude_models():
    model = LLMClient._create_model("anthropic", "claude-opus-5-5", api_key="test")
    block = {"type": "thinking", "thinking": "Native reasoning", "signature": "native"}
    message = AIMessage(
        content=[block, {"type": "text", "text": "423"}],
        response_metadata={"model_provider": "anthropic", "model_name": "claude-sonnet-5-5"},
    )
    payload = model._get_request_payload([HumanMessage("Calculate"), message, HumanMessage("Next")])
    assert payload["messages"][1]["content"][0] == block


def test_foreign_redacted_thinking_is_not_sent_as_a_claude_signature():
    model = LLMClient._create_model("anthropic", "claude-sonnet-5-5", api_key="test")
    message = AIMessage(
        content=[
            {"type": "redacted_thinking", "data": "opaque-foreign"},
            {"type": "text", "text": "423"},
        ],
        response_metadata={"model_provider": "anthropic", "model_name": "glm-5.2"},
    )
    payload = model._get_request_payload([HumanMessage("Calculate"), message, HumanMessage("Next")])
    assert [b["type"] for b in payload["messages"][1]["content"]] == ["text"]


@pytest.mark.parametrize("source", [{}, {"model_provider": "anthropic"}])
def test_legacy_claude_history_without_model_identity_keeps_its_signature(source):
    model = LLMClient._create_model("anthropic", "claude-sonnet-5-5", api_key="test")
    block = {"type": "thinking", "thinking": "Original thought", "signature": "original"}
    message = AIMessage(content=[block, {"type": "text", "text": "423"}], response_metadata=source)
    payload = model._get_request_payload([HumanMessage("Calculate"), message, HumanMessage("Next")])
    assert payload["messages"][1]["content"][0] == block


def test_glm_native_history_keeps_its_signature_on_the_anthropic_compatible_lane():
    model = LLMClient._create_model("zai", "glm-5.2", api_key="test")
    block = {"type": "thinking", "thinking": "Original thought", "signature": "glm-signature"}
    message = AIMessage(
        content=[block, {"type": "text", "text": "423"}],
        response_metadata={"model_provider": "anthropic", "model_name": "glm-5.2"},
    )
    payload = model._get_request_payload([HumanMessage("Calculate"), message, HumanMessage("Next")])
    assert payload["messages"][1]["content"][0] == block
