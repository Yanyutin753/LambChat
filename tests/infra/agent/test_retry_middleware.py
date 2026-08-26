import httpx
import pytest
from langchain_core.messages import AIMessage

from src.infra.agent.middleware.retry import ModelFallbackMiddleware


class _Request:
    def __init__(self, model) -> None:
        self.model = model

    def override(self, **kwargs):
        return _Request(kwargs.get("model", self.model))


async def test_fallback_runs_when_primary_raises_non_retryable_error() -> None:
    primary_model = object()
    fallback_model = object()
    middleware = ModelFallbackMiddleware(fallback_model="openai/fallback-model")
    middleware._fallback_llm = fallback_model

    async def handler(request):
        if request.model is primary_model:
            raise ValueError("bad request payload")
        return AIMessage(content="fallback answer")

    result = await middleware.awrap_model_call(_Request(primary_model), handler)

    assert result.content == "fallback answer"


async def test_fallback_runs_when_primary_raises_authentication_error() -> None:
    """回归守卫：上游 401（oaifree Invalid token）必须换兜底模型重放，
    绝不让裸 401 冒泡成用户可见错误（2026-08-26 生产事故场景）。"""
    import httpx
    import openai

    primary_model = object()
    fallback_model = object()
    middleware = ModelFallbackMiddleware(fallback_model="openai/fallback-model")
    middleware._fallback_llm = fallback_model

    response = httpx.Response(status_code=401, request=httpx.Request("POST", "http://test/v1/chat"))
    body = {"error": {"code": "", "message": "Invalid token", "type": "new_api_error"}}

    async def handler(request):
        if request.model is primary_model:
            raise openai.AuthenticationError(
                "Error code: 401 - Invalid token", response=response, body=body
            )
        return AIMessage(content="fallback answer")

    result = await middleware.awrap_model_call(_Request(primary_model), handler)

    assert result.content == "fallback answer"


async def test_fallback_runs_when_primary_returns_empty_content() -> None:
    primary_model = object()
    fallback_model = object()
    middleware = ModelFallbackMiddleware(fallback_model="openai/fallback-model")
    middleware._fallback_llm = fallback_model

    async def handler(request):
        if request.model is primary_model:
            return AIMessage(content="")
        return AIMessage(content="fallback answer")

    result = await middleware.awrap_model_call(_Request(primary_model), handler)

    assert result.content == "fallback answer"


async def test_fallback_runs_when_primary_returns_truncated_content() -> None:
    primary_model = object()
    fallback_model = object()
    middleware = ModelFallbackMiddleware(fallback_model="openai/fallback-model")
    middleware._fallback_llm = fallback_model

    async def handler(request):
        if request.model is primary_model:
            return AIMessage(
                content="Here is the result:",
                response_metadata={"stop_reason": "max_tokens"},
            )
        return AIMessage(content="fallback answer")

    result = await middleware.awrap_model_call(_Request(primary_model), handler)

    assert result.content == "fallback answer"


async def test_fallback_model_is_created_with_same_thinking_config(monkeypatch) -> None:
    calls = []
    fallback_model = object()
    thinking = {"type": "enabled", "level": "medium", "budget_tokens": 8192}
    middleware = ModelFallbackMiddleware(
        fallback_model="openai/fallback-model",
        thinking=thinking,
    )

    async def fake_get_model(**kwargs):
        calls.append(kwargs)
        return fallback_model

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", fake_get_model)

    result = await middleware._get_fallback_llm()

    assert result is fallback_model
    assert calls == [{"model": "openai/fallback-model", "thinking": thinking}]


def test_is_retryable_error_recognizes_asyncio_timeout() -> None:
    """A bare asyncio.TimeoutError (e.g. from wait_for) must be retryable."""
    import asyncio

    from src.infra.agent.middleware.retry import _is_retryable_error

    assert _is_retryable_error(asyncio.TimeoutError()) is True


@pytest.mark.parametrize(
    "error_type",
    [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout],
)
def test_is_retryable_error_recognizes_every_httpx_timeout(error_type) -> None:
    from src.infra.agent.middleware.retry import _is_retryable_error

    assert _is_retryable_error(error_type("timed out")) is True


def test_retry_stack_does_not_bound_the_complete_streaming_call(monkeypatch) -> None:
    from src.infra.agent.middleware.retry import create_retry_middleware

    monkeypatch.setattr("src.kernel.config.settings.LLM_MAX_RETRIES", 3)

    middleware = create_retry_middleware()

    assert [type(item).__name__ for item in middleware] == [
        "DeadAttachmentFilterMiddleware",
        "HistoricalImageCapMiddleware",
        "ModelRetryMiddleware",
        "EmptyContentRetryMiddleware",
        "UniqueResponseIdMiddleware",
    ]


async def test_official_model_retry_middleware_retries_first_event_timeout(
    monkeypatch,
) -> None:
    from src.infra.agent.middleware.retry import create_retry_middleware

    monkeypatch.setattr("src.kernel.config.settings.LLM_MAX_RETRIES", 3)
    monkeypatch.setattr("src.kernel.config.settings.LLM_RETRY_DELAY", 0)
    retry = create_retry_middleware()[2]
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise TimeoutError("model stream produced no first event")
        return AIMessage(content="ok")

    result = await retry.awrap_model_call(None, handler)

    assert result.content == "ok"
    assert calls == 4


def test_retry_stack_leads_with_dead_attachment_filter() -> None:
    """Dead attachment filtering must wrap every model call (outermost layer)."""
    from src.infra.agent.middleware.dead_attachment import DeadAttachmentFilterMiddleware
    from src.infra.agent.middleware.retry import create_retry_middleware

    stack = create_retry_middleware(fallback_model="glm-5.3")

    assert isinstance(stack[0], DeadAttachmentFilterMiddleware)
