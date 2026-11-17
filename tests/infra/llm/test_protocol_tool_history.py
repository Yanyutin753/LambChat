import json
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.infra.llm.client import LLMClient


@pytest.mark.parametrize(
    "provider,name,api_format",
    [
        ("anthropic", "claude-sonnet-5-5", None),
        ("zai", "glm-5.2", None),
        ("google", "gemini-4-argon", None),
        ("openai", "gpt-6-luna", "responses"),
        ("openai", "gpt-6.1-sol", "chat_completions"),
        ("openai", "deepseek-v4.1-flash", "responses"),
        ("xai", "grok-4.7", "chat_completions"),
        ("azure", "gpt-4o", "chat_completions"),
    ],
)
def test_long_cross_model_history_preserves_parallel_tool_pairs_and_failed_result(
    provider, name, api_format
):
    model = LLMClient._create_model(
        provider,
        name,
        api_key="test",
        api_format=api_format,
        **({"api_base": "https://test.openai.azure.com"} if provider == "azure" else {}),
    )
    messages = []
    for i in range(40):
        messages.extend([HumanMessage(f"Record ledger-{i}"), AIMessage(f"Saved ledger-{i}")])
    messages.extend(
        [
            HumanMessage("Calculate and look up the record"),
            AIMessage(
                content=[
                    {"type": "thinking", "thinking": "Use both tools", "signature": "glm-signature"}
                ],
                tool_calls=[
                    {"name": "calculator", "args": {"a": 137, "b": 286}, "id": "call_1"},
                    {"name": "lookup", "args": {"key": "ledger-39"}, "id": "call_2"},
                ],
                response_metadata={"model_provider": "anthropic", "model_name": "glm-5.2"},
            ),
            ToolMessage(content="423", tool_call_id="call_1", name="calculator"),
            ToolMessage(
                content="lookup unavailable", tool_call_id="call_2", name="lookup", status="error"
            ),
        ]
    )
    original = deepcopy(messages)
    if provider == "google":
        request = model._prepare_request(messages)
        parts = [p for c in request["contents"] for p in c.parts or []]
        calls = [p.function_call.name for p in parts if p.function_call]
        results = [p.function_response.name for p in parts if p.function_response]
        payload = [c.model_dump(mode="json") for c in request["contents"]]
    else:
        payload = model._get_request_payload(messages)
        if "input" in payload:
            calls = [i["call_id"] for i in payload["input"] if i.get("type") == "function_call"]
            results = [
                i["call_id"] for i in payload["input"] if i.get("type") == "function_call_output"
            ]
        elif provider in {"anthropic", "zai"}:
            blocks = [b for m in payload["messages"] for b in m["content"] if isinstance(b, dict)]
            calls = [b["id"] for b in blocks if b["type"] == "tool_use"]
            results = [b["tool_use_id"] for b in blocks if b["type"] == "tool_result"]
        else:
            calls = [tc["id"] for m in payload["messages"] for tc in m.get("tool_calls", [])]
            results = [m["tool_call_id"] for m in payload["messages"] if m["role"] == "tool"]
    assert len(calls) == 2 and calls == results
    encoded = json.dumps(payload, default=str)
    assert "lookup unavailable" in encoded and "423" in encoded
    assert all(f"Saved ledger-{i}" in encoded for i in range(40))
    assert messages == original
