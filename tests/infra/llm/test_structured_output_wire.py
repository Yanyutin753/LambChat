"""Exercise the SDK HTTP boundary, including Responses and Azure deployment aliases."""

import json
from unittest.mock import AsyncMock

import httpx2
import openai
import pytest
from langchain_core.messages import HumanMessage

from src.agents.core.recommendations import RecommendedQuestions
from src.infra.llm.client import LLMClient
from src.infra.llm.quota import QuotaChatMixin
from src.infra.llm.structured_output import bind_structured_output


@pytest.mark.parametrize(
    "provider, api_format",
    [
        ("openai", "chat_completions"),
        ("openai", "responses"),
        ("azure", "chat_completions"),
    ],
)
@pytest.mark.parametrize("method", ["json_schema", "json_mode", "function_calling"])
async def test_structured_contract_and_usage_survive_sdk_serialization(
    provider, api_format, method, monkeypatch
):
    monkeypatch.setattr(QuotaChatMixin, "_quota_begin", AsyncMock(return_value=None))
    captured = []
    questions = ["first?", "second?", "third?"]
    answer = json.dumps({"questions": questions})
    name = "a-private-deployment-alias"

    def respond(request):
        captured.append(json.loads(request.content))
        if api_format == "responses":
            output = (
                [
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "RecommendedQuestions",
                        "arguments": answer,
                        "id": "fc-1",
                        "status": "completed",
                    }
                ]
                if method == "function_calling"
                else [
                    {
                        "type": "message",
                        "id": "msg-1",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": answer, "annotations": []}],
                    }
                ]
            )
            return httpx2.Response(
                200,
                json={
                    "object": "response",
                    "id": "resp-1",
                    "created_at": 1,
                    "model": name,
                    "status": "completed",
                    "output": output,
                    "usage": {"input_tokens": 7, "output_tokens": 5, "total_tokens": 12},
                },
            )
        message = {"role": "assistant", "content": answer}
        if method == "function_calling":
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "RecommendedQuestions", "arguments": answer},
                    }
                ],
            }
        return httpx2.Response(
            200,
            json={
                "object": "chat.completion",
                "id": "chatcmpl-1",
                "created": 1,
                "model": name,
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if method == "function_calling" else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
            },
        )

    transport = httpx2.MockTransport(respond)
    client = httpx2.AsyncClient(transport=transport)
    if provider == "azure":
        sdk = openai.AsyncAzureOpenAI(
            api_key="test-only",
            azure_endpoint="https://test.invalid",
            azure_deployment=name,
            api_version="2024-08-01-preview",
            http_client=client,
        )
    else:
        sdk = openai.AsyncOpenAI(
            api_key="test-only", base_url="https://test.invalid/v1", http_client=client
        )
    model = LLMClient._create_model(
        provider,
        name,
        api_key="test-only",
        api_format=api_format,
        api_base="https://test.invalid",
    )
    model.root_async_client = sdk
    model.async_client = sdk.chat.completions
    model.streaming = False
    try:
        response = await bind_structured_output(model, RecommendedQuestions, method).ainvoke(
            [HumanMessage(content="Return questions in JSON.")]
        )
        assert response["parsed"].questions == questions
        assert response["raw"].usage_metadata["total_tokens"] == 12
        assert len(captured) == 1
        payload = captured[0]
        if method == "function_calling":
            choice = payload["tool_choice"]
            assert choice["type"] == "function"
            assert (choice.get("name") or choice["function"]["name"]) == "RecommendedQuestions"
        else:
            fmt = (
                payload["text"]["format"]
                if api_format == "responses"
                else payload["response_format"]
            )
            assert fmt["type"] == ("json_schema" if method == "json_schema" else "json_object")
            if method == "json_schema":
                schema = fmt.get("json_schema", fmt)["schema"]
                assert schema["properties"]["questions"]["items"]["type"] == "string"
                assert schema["required"] == ["questions"]
    finally:
        await sdk.close()
