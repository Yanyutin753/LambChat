"""Capability negotiation is bounded and isolated from authentication/network failures."""

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.agents.core.recommendations import (
    RecommendedQuestions,
    build_recommend_questions,
    generate_recommend_questions,
)
from src.infra.llm.client import LLMClient
from src.infra.llm.providers import PROVIDER_REGISTRY
from src.infra.llm.structured_output import (
    bind_structured_output,
    is_unsupported_structured_output,
    remember_structured_output_method,
    structured_output_methods,
)

QUESTIONS = ["first?", "second?", "third?"]


@pytest.mark.parametrize("provider", [*PROVIDER_REGISTRY, "private-gateway"])
def test_every_channel_uses_its_actual_protocol_with_an_arbitrary_model_alias(provider):
    model = LLMClient._create_model(
        provider, "private-model-alias", api_key="test-only", api_base="https://test.invalid"
    )
    methods = structured_output_methods(model, RecommendedQuestions)
    protocol = PROVIDER_REGISTRY.get(provider, ("openai", []))[0]
    assert methods == (
        ("json_schema", "function_calling")
        if protocol == "anthropic"
        else ("json_schema", "json_mode", "function_calling")
    )
    for method in methods:
        assert bind_structured_output(model, RecommendedQuestions, method) is not None


class Model:
    def __init__(self, results, protocol="openai-chat"):
        self._llm_type = protocol
        self.results = results
        self.calls = []

    async def invoke(self, method, schema):
        self.calls.append(method)
        result = self.results[method]
        if isinstance(result, BaseException):
            raise result
        if isinstance(result, AIMessage):
            return {"raw": result, "parsed": None}
        return {"raw": AIMessage(content=""), "parsed": schema(questions=result)}

    def with_structured_output(self, schema, *, method, include_raw):
        async def invoke(_prompt):
            return await self.invoke(method, schema)

        return RunnableLambda(invoke)

    def bind(self, **kwargs):
        assert kwargs == {"response_mime_type": "application/json"}

        async def invoke(_prompt):
            self.calls.append("json_mode")
            return AIMessage(content=json.dumps({"questions": self.results["json_mode"]}))

        return RunnableLambda(invoke)


@pytest.fixture
def use_model(monkeypatch):
    def install(model):
        async def get_model(**kwargs):
            return model

        monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", get_model)
        monkeypatch.setattr("src.agents.core.recommendations.settings.LLM_MAX_RETRIES", 0)

    return install


def error(status, message):
    request = httpx.Request("POST", "https://test.invalid")
    return httpx.HTTPStatusError(message, request=request, response=httpx.Response(status))


@pytest.mark.parametrize("protocol", ["openai-chat", "azure-openai-chat", "custom-compatible"])
async def test_all_supported_methods_are_tried_only_once(use_model, protocol):
    model = Model(
        {
            "json_schema": AIMessage(content="ignored schema"),
            "json_mode": error(422, "response_format is not supported"),
            "function_calling": QUESTIONS,
        },
        protocol,
    )
    use_model(model)
    assert await generate_recommend_questions("How?") == QUESTIONS
    assert model.calls == ["json_schema", "json_mode", "function_calling"]


async def test_anthropic_compatibility_ignores_schema_then_uses_tools(use_model):
    model = Model(
        {
            "json_schema": AIMessage(content="plain lines"),
            "function_calling": QUESTIONS,
        },
        "anthropic-chat",
    )
    use_model(model)
    assert await generate_recommend_questions("How?") == QUESTIONS
    assert model.calls == ["json_schema", "function_calling"]


async def test_google_json_only_models_receive_no_schema_on_fallback(use_model):
    model = Model(
        {
            "json_schema": error(400, "responseJsonSchema is not supported"),
            "json_mode": QUESTIONS,
        },
        "chat-google-generative-ai",
    )
    use_model(model)
    assert await generate_recommend_questions("How?") == QUESTIONS
    assert model.calls == ["json_schema", "json_mode"]


@pytest.mark.parametrize(
    "failure",
    [
        error(401, "json_schema auth failure"),
        error(403, "response_format permission denied"),
        error(429, "json_mode rate limit"),
        error(500, "json_schema upstream error"),
        error(400, "Invalid API key"),
        error(400, "context_length_exceeded"),
        TimeoutError("timeout"),
    ],
)
async def test_real_failures_do_not_trigger_protocol_fallback(use_model, failure):
    model = Model({"json_schema": failure})
    use_model(model)
    assert await generate_recommend_questions("How?") == build_recommend_questions("How?")
    assert model.calls == ["json_schema"]


@pytest.mark.parametrize(
    "metadata, extra",
    [
        ({"stop_reason": "max_tokens"}, {}),
        ({"finish_reason": "length"}, {}),
        ({"incomplete_details": {"reason": "max_output_tokens"}}, {}),
        ({"finish_reason": "SAFETY"}, {}),
        ({}, {"refusal": "refused"}),
    ],
)
async def test_truncation_and_refusal_do_not_trigger_more_generations(use_model, metadata, extra):
    model = Model(
        {
            "json_schema": AIMessage(
                content="",
                response_metadata=metadata,
                additional_kwargs=extra,
            )
        }
    )
    use_model(model)
    assert await generate_recommend_questions("How?") == build_recommend_questions("How?")
    assert model.calls == ["json_schema"]


async def test_cancellation_propagates_without_fallback(use_model):
    model = Model({"json_schema": asyncio.CancelledError()})
    use_model(model)
    with pytest.raises(asyncio.CancelledError):
        await generate_recommend_questions("How?")
    assert model.calls == ["json_schema"]


async def test_unsupported_formats_terminate_without_prompt_only_request(use_model):
    model = Model(
        {
            method: NotImplementedError()
            for method in (
                "json_schema",
                "json_mode",
                "function_calling",
            )
        }
    )
    use_model(model)
    assert await generate_recommend_questions("How?") == build_recommend_questions("How?")
    assert model.calls == ["json_schema", "json_mode", "function_calling"]


async def test_cached_method_can_recover_when_gateway_capabilities_change(use_model):
    model = Model({"json_mode": error(400, "json_mode unsupported"), "json_schema": QUESTIONS})
    remember_structured_output_method(model, RecommendedQuestions, "json_mode")
    use_model(model)
    assert await generate_recommend_questions("How?") == QUESTIONS
    assert model.calls == ["json_mode", "json_schema"]
    assert structured_output_methods(model, RecommendedQuestions)[0] == "json_schema"


def test_preference_is_scoped_to_instance_and_schema():
    first, second = Model({}), Model({})

    class OtherSchema(RecommendedQuestions):
        pass

    remember_structured_output_method(first, RecommendedQuestions, "json_mode")
    assert structured_output_methods(first, RecommendedQuestions)[0] == "json_mode"
    assert structured_output_methods(second, RecommendedQuestions)[0] == "json_schema"
    assert structured_output_methods(first, OtherSchema)[0] == "json_schema"


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("Unrecognized method json_schema"),
        TypeError("unexpected keyword argument 'response_format'"),
        NotImplementedError(),
        error(422, "Invalid schema: additionalProperties must be false"),
    ],
)
def test_explicit_capability_rejections_are_recognized(failure):
    assert is_unsupported_structured_output(failure)
