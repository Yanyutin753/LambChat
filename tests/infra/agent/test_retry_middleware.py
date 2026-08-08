from __future__ import annotations

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


async def test_fallback_runs_when_primary_hangs_without_returning(monkeypatch) -> None:
    """A primary model that never returns and never raises must still trigger
    fallback via wait_for, instead of blocking the request forever (the gemini
    third-party-proxy hang)."""
    import asyncio

    primary_model = object()
    fallback_model = object()
    from langchain.agents.factory import _chain_async_model_call_handlers

    from src.infra.agent.middleware.retry import create_retry_middleware

    monkeypatch.setattr("src.kernel.config.settings.LLM_REQUEST_TIMEOUT", 0.05)
    monkeypatch.setattr("src.kernel.config.settings.LLM_MAX_RETRIES", 0)

    middleware = create_retry_middleware(fallback_model="openai/fallback-model")
    fallback = next(item for item in middleware if isinstance(item, ModelFallbackMiddleware))
    fallback._fallback_llm = fallback_model
    composed = _chain_async_model_call_handlers([item.awrap_model_call for item in middleware])
    assert composed is not None

    async def handler(request):
        if request.model is primary_model:
            await asyncio.sleep(10)  # simulate a hung stream
        return AIMessage(content="fallback answer")

    result = await composed(_Request(primary_model), handler)

    assert result.model_response.result[0].content == "fallback answer"


async def test_fallback_timeout_does_not_hang_forever(monkeypatch) -> None:
    """The safety net must also bound a fallback provider that stalls."""
    import asyncio

    primary_model = object()
    fallback_model = object()
    from langchain.agents.factory import _chain_async_model_call_handlers

    from src.infra.agent.middleware.retry import create_retry_middleware

    monkeypatch.setattr("src.kernel.config.settings.LLM_REQUEST_TIMEOUT", 0.02)
    monkeypatch.setattr("src.kernel.config.settings.LLM_MAX_RETRIES", 0)

    middleware = create_retry_middleware(fallback_model="openai/fallback-model")
    fallback = next(item for item in middleware if isinstance(item, ModelFallbackMiddleware))
    fallback._fallback_llm = fallback_model
    composed = _chain_async_model_call_handlers([item.awrap_model_call for item in middleware])
    assert composed is not None

    async def handler(request):
        await asyncio.sleep(10)

    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            composed(_Request(primary_model), handler),
            timeout=0.2,
        )

    # Distinguish the middleware's configured timeout from the test's 0.2s
    # deadlock guard. Without a bound around fallback this takes ~0.2s.
    assert loop.time() - started < 0.15


async def test_request_timeout_is_retried_before_fallback(monkeypatch) -> None:
    """A hung attempt times out inside retry instead of bypassing retries."""
    import asyncio

    from langchain.agents.factory import _chain_async_model_call_handlers

    from src.infra.agent.middleware.retry import create_retry_middleware

    primary_model = object()
    fallback_model = object()
    monkeypatch.setattr("src.kernel.config.settings.LLM_REQUEST_TIMEOUT", 0.02)
    monkeypatch.setattr("src.kernel.config.settings.LLM_MAX_RETRIES", 1)
    monkeypatch.setattr("src.kernel.config.settings.LLM_RETRY_DELAY", 0)

    middleware = create_retry_middleware(fallback_model="openai/fallback-model")
    fallback = next(item for item in middleware if isinstance(item, ModelFallbackMiddleware))
    fallback._fallback_llm = fallback_model
    composed = _chain_async_model_call_handlers([item.awrap_model_call for item in middleware])
    assert composed is not None

    primary_calls = 0
    fallback_calls = 0

    async def handler(request):
        nonlocal primary_calls, fallback_calls
        if request.model is primary_model:
            primary_calls += 1
            if primary_calls == 1:
                await asyncio.sleep(10)
            return AIMessage(content="primary recovered")
        fallback_calls += 1
        return AIMessage(content="fallback answer")

    result = await composed(_Request(primary_model), handler)

    assert result.model_response.result[0].content == "primary recovered"
    assert primary_calls == 2
    assert fallback_calls == 0


async def test_request_timeout_error_reports_configured_duration(monkeypatch) -> None:
    """Timeout errors remain actionable even when no fallback is configured."""
    import asyncio

    from src.infra.agent.middleware.retry import ModelRequestTimeoutMiddleware

    monkeypatch.setattr("src.kernel.config.settings.LLM_REQUEST_TIMEOUT", 0.01)

    async def handler(request):
        await asyncio.sleep(10)

    with pytest.raises(asyncio.TimeoutError, match="0.01s"):
        await ModelRequestTimeoutMiddleware().awrap_model_call(_Request(object()), handler)


def test_is_retryable_error_recognizes_asyncio_timeout() -> None:
    """A bare asyncio.TimeoutError (e.g. from wait_for) must be retryable."""
    import asyncio

    from src.infra.agent.middleware.retry import _is_retryable_error

    assert _is_retryable_error(asyncio.TimeoutError()) is True
