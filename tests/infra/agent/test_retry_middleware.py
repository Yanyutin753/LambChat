import httpx
import pytest
from langchain_core.messages import AIMessage

from src.infra.agent.middleware.retry import EmptyContentRetryMiddleware, ModelFallbackMiddleware


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


async def test_empty_content_retry_exhausted_returns_last_response_without_raise() -> None:
    """重试耗尽仍空最终消息时返回最后响应，不上抛。

    中间件层没有「用户是否已通过流式拿到正文」的视野：2026-09-05 13:50 生产
    4 例，上游流式已把完整答案交付（message:chunk + done 之后）但最终聚合
    AIMessage 为空，此处上抛会在 done 后追加 error、把成功 run 标成失败，
    还触发 210K input 的重试/降级重复烧钱。「零正文」的终态判定权在
    executor 层（按真实 message:chunk 事件判定，见
    tests/infra/task/test_executor_no_output_guard.py）。
    """
    middleware = EmptyContentRetryMiddleware(max_retries=1, retry_delay=0)
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return AIMessage(content="", additional_kwargs={"reasoning_content": "长篇思考"})

    result = await middleware.awrap_model_call(None, handler)

    assert result.content == ""
    assert calls == 2


async def test_truncated_content_exhausted_still_returns_last_response() -> None:
    """截断启发式命中的半截回答不上抛：部分内容已流出，保留给用户。"""
    middleware = EmptyContentRetryMiddleware(max_retries=1, retry_delay=0)

    async def handler(_request):
        return AIMessage(
            content="半截回答：",
            response_metadata={"stop_reason": "max_tokens"},
        )

    result = await middleware.awrap_model_call(None, handler)

    assert result.content == "半截回答："


async def test_tool_call_only_response_returns_without_raise() -> None:
    """只有 tool_calls 的响应是正常中间态，不算空、立即返回。"""
    middleware = EmptyContentRetryMiddleware(max_retries=1, retry_delay=0)
    message = AIMessage(
        content="",
        tool_calls=[{"name": "web_search", "args": {"q": "news"}, "id": "call-1"}],
    )

    async def handler(_request):
        return message

    result = await middleware.awrap_model_call(None, handler)

    assert result is message


async def test_fallback_empty_final_message_returns_response_without_raise() -> None:
    """兜底模型的最终消息为空时返回该响应，不上抛（同上：流式可能已交付）。"""
    primary_model = object()
    fallback_model = object()
    middleware = ModelFallbackMiddleware(fallback_model="openai/fallback-model")
    middleware._fallback_llm = fallback_model

    async def handler(request):
        if request.model is primary_model:
            return AIMessage(content="")
        return AIMessage(content="", additional_kwargs={"reasoning_content": "兜底也在思考"})

    result = await middleware.awrap_model_call(_Request(primary_model), handler)

    assert result.content == ""


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
