"""Recommended questions must request protocol-level structured output."""

from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from src.agents.core.recommendations import (
    RecommendedQuestions,
    _extract_text,
    _parse_questions,
    generate_recommend_questions,
)
from src.infra.llm.client import LLMClient
from src.infra.llm.structured_output import bind_structured_output


@pytest.mark.parametrize(
    "first_result",
    [
        httpx.HTTPStatusError(
            "response_format json_schema is not supported",
            request=httpx.Request("POST", "https://example.test"),
            response=httpx.Response(400),
        ),
        AIMessage(content="three plain text lines, despite the schema"),
    ],
)
async def test_format_negotiation_recovers_without_model_name_allowlists(monkeypatch, first_result):
    calls = []
    expected = ["first?", "second?", "third?"]

    class Model:
        _llm_type = "openai-chat"
        model = "a-new-model-never-seen-before"

        def with_structured_output(self, schema, *, method, include_raw):
            async def invoke(_prompt):
                calls.append(method)
                if method == "json_schema":
                    if isinstance(first_result, Exception):
                        raise first_result
                    return {"raw": first_result, "parsed": None}
                return {"raw": AIMessage(content=""), "parsed": schema(questions=expected)}

            return SimpleNamespace(ainvoke=invoke)

    model = Model()

    async def get_model(**kwargs):
        return model

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", get_model)
    assert await generate_recommend_questions("How?") == expected
    assert calls == ["json_schema", "json_mode"]
    calls.clear()
    assert await generate_recommend_questions("What next?") == expected
    assert calls == ["json_mode"]


@pytest.mark.parametrize(
    ("protocol", "name", "method"),
    [
        ("anthropic-chat", "glm-5.3-flash", "json_schema"),
        ("anthropic-chat", "claude-sonnet-4-6", "json_schema"),
        ("openai-chat", "glm-5.3-flash", "json_schema"),
        ("azure-openai-chat", "gpt-4o", "json_schema"),
        ("chat-google-generative-ai", "gemini-2.5-flash", "json_schema"),
    ],
)
async def test_recommendations_request_native_output_contract(monkeypatch, protocol, name, method):
    calls = []
    expected = ["草稿什么时候保存？", "附件也会保留吗？", "换设备能恢复吗？"]

    class Model:
        _llm_type = protocol
        model = name

        def with_structured_output(self, schema, **kwargs):
            calls.append(kwargs)

            async def invoke(_prompt):
                return {"parsed": schema(questions=expected), "raw": AIMessage(content="")}

            return SimpleNamespace(ainvoke=invoke)

        async def ainvoke(self, _prompt):
            return AIMessage(content="\n".join(expected))

    async def get_model(**kwargs):
        return Model()

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", get_model)
    questions = await generate_recommend_questions("为什么输入框草稿丢了？")
    assert calls == [{"method": method, "include_raw": True}]
    assert questions == expected


@pytest.mark.parametrize(
    ("provider", "name", "api_format", "method"),
    [
        ("anthropic", "glm-5.3-flash", None, "function_calling"),
        ("anthropic", "claude-sonnet-4-6", None, "json_schema"),
        ("openai", "gpt-4o", "chat_completions", "json_mode"),
        ("openai", "gpt-4o", "responses", "json_mode"),
        ("google", "gemini-2.5-flash", None, "json_schema"),
        ("google", "unknown-google-model", None, "json_mode"),
        ("anthropic", "private-alias", None, "json_schema"),
    ],
)
def test_output_contract_reaches_actual_protocol_payload(provider, name, api_format, method):
    model = LLMClient._create_model(provider, name, api_key="test-only", api_format=api_format)
    runnable = bind_structured_output(model, RecommendedQuestions, method)
    bound = (
        runnable.steps[0]
        if provider == "google" and method == "json_mode"
        else runnable.steps[0].steps__["raw"]
    )
    # BaseChatModel removes tracing metadata before calling the provider adapter.
    request_kwargs = {
        key: value for key, value in bound.kwargs.items() if key != "ls_structured_output_format"
    }
    messages = [HumanMessage(content="Return recommended questions in JSON.")]
    if provider == "google":
        payload = model._prepare_request(messages, **request_kwargs)
        config = payload["config"]
        assert config.response_mime_type == "application/json"
        if method == "json_mode":
            assert config.response_json_schema is None
        else:
            assert (
                config.response_json_schema["properties"]["questions"]["items"]["type"] == "string"
            )
    else:
        payload = model._get_request_payload(messages, **request_kwargs)
        if name.startswith("glm"):
            assert payload["tool_choice"] == {"type": "tool", "name": "RecommendedQuestions"}
            schema = payload["tools"][0]["input_schema"]
            assert schema["properties"]["questions"]["minItems"] == 3
            assert schema["properties"]["questions"]["maxItems"] == 3
            assert schema["properties"]["questions"]["items"]["type"] == "string"
        elif provider == "anthropic":
            assert payload["output_config"]["format"]["type"] == "json_schema"
            assert payload["output_config"]["format"]["schema"]["required"] == ["questions"]
        elif api_format == "responses":
            assert payload["text"]["format"] == {"type": "json_object"}
        else:
            assert payload["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "questions", [["one"], ["a", "b", "c", "d"], ["a", "b", " "], ["a", "b", 42]]
)
async def test_invalid_output_cannot_be_displayed_as_recommendations(questions):
    import json

    with pytest.raises(ValidationError):
        RecommendedQuestions(questions=questions)
    assert await _parse_questions(json.dumps({"questions": questions})) == []


async def test_legacy_json_text_blocks_are_joined_without_reasoning():
    content = [
        {"type": "thinking", "thinking": "private reasoning"},
        {"type": "text", "text": '{"questions":[" first? ",'},
        {"type": "text", "text": '"second?","third?"]}'},
    ]
    assert await _parse_questions(_extract_text(content)) == ["first?", "second?", "third?"]


async def test_rate_limited_recommendation_skips_retry_storm(monkeypatch):
    """429 限流窗口内推荐问题只试一次,直接落本地启发式(issue #1123)。"""

    from src.agents.core.recommendations import build_recommend_questions

    calls: list[str] = []

    class Model:
        _llm_type = "anthropic-chat"
        model = "glm-5.3"

        def with_structured_output(self, schema, *, method, include_raw):  # noqa: ANN001
            async def invoke(_prompt):
                calls.append(method)
                raise httpx.HTTPStatusError(
                    "Error code: 429 - rate limit exceeded",
                    request=httpx.Request("POST", "https://unit.invalid"),
                    response=httpx.Response(429),
                )

            return SimpleNamespace(ainvoke=invoke)

    async def get_model(**kwargs):  # noqa: ANN003
        return Model()

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", get_model)
    monkeypatch.setattr("src.agents.core.recommendations.settings.LLM_MAX_RETRIES", 6)

    questions = await generate_recommend_questions("聊到一半该问什么?")

    assert calls == ["json_schema"]
    assert questions == build_recommend_questions("聊到一半该问什么?")
