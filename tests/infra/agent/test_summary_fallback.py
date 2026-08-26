"""Tests for summarization fallback protection.

deepagents 的自动摘要中间件在 awrap_model_call 外层直接调用主模型生成摘要，
不经过 ModelRetryMiddleware / ModelFallbackMiddleware 链。当主模型挂死
（首事件超时 / 429 / 5xx）时，摘要失败会让整个 agent 任务终止。
这里的保护逻辑：摘要调用失败且可重试时，换兜底模型重做一次摘要。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.infra.agent.middleware.summary_fallback import (
    protect_summarization_middleware,
    summarization_fallback_patch,
)


def _stub_middleware(*, fail_with: BaseException | None = None, summary: str = "primary summary"):
    mw = SimpleNamespace()
    mw._lc_helper = SimpleNamespace(
        summary_prompt="Summarize:\n{messages}",
        trim_tokens_to_summarize=None,
        token_counter=None,
        keep=None,
    )
    if fail_with is not None:

        async def failing(_messages):
            raise fail_with

        mw._acreate_summary = failing
    else:

        async def ok(_messages):
            return summary

        mw._acreate_summary = ok
    return mw


def _fake_fallback_llm(monkeypatch, *, text: str = "fallback summary"):
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    fake = GenericFakeChatModel(messages=iter([AIMessage(text)] * 10))
    get_model = AsyncMock(return_value=fake)
    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", get_model)
    return get_model, fake


async def test_retryable_summary_failure_switches_to_fallback_model(monkeypatch) -> None:
    mw = _stub_middleware(fail_with=TimeoutError("model stream produced no first event"))
    get_model, _ = _fake_fallback_llm(monkeypatch)

    protected = protect_summarization_middleware(
        mw, fallback_model="openai/fallback-model", thinking=None
    )

    result = await protected._acreate_summary([HumanMessage(content="history")])

    assert result == "fallback summary"
    get_model.assert_awaited_once_with(model="openai/fallback-model", thinking=None)


def _openai_authentication_error():
    import httpx
    import openai

    response = httpx.Response(status_code=401, request=httpx.Request("POST", "http://test/v1/chat"))
    body = {"error": {"code": "", "message": "Invalid token", "type": "new_api_error"}}
    return openai.AuthenticationError(
        "Error code: 401 - Invalid token", response=response, body=body
    )


async def test_auth_summary_failure_switches_to_fallback_model(monkeypatch) -> None:
    """401/403 鉴权失败对同一把 key 永不瞬态：摘要调用必须换兜底模型重做，
    而不是把裸 401 直接抛给用户（2026-08-26 生产 oaifree Invalid token 事故）。"""
    mw = _stub_middleware(fail_with=_openai_authentication_error())
    get_model, _ = _fake_fallback_llm(monkeypatch)

    protected = protect_summarization_middleware(
        mw, fallback_model="openai/fallback-model", thinking=None
    )

    result = await protected._acreate_summary([HumanMessage(content="history")])

    assert result == "fallback summary"
    get_model.assert_awaited_once_with(model="openai/fallback-model", thinking=None)


async def test_non_retryable_summary_failure_propagates(monkeypatch) -> None:
    mw = _stub_middleware(fail_with=ValueError("bad request payload"))
    get_model, _ = _fake_fallback_llm(monkeypatch)

    protected = protect_summarization_middleware(
        mw, fallback_model="openai/fallback-model", thinking=None
    )

    with pytest.raises(ValueError, match="bad request payload"):
        await protected._acreate_summary([HumanMessage(content="history")])
    get_model.assert_not_awaited()


async def test_no_fallback_configured_leaves_summary_call_untouched() -> None:
    mw = _stub_middleware(summary="primary summary")

    protected = protect_summarization_middleware(mw, fallback_model=None)

    assert await protected._acreate_summary([HumanMessage(content="history")]) == "primary summary"


async def test_fallback_failure_reraises_after_logging(monkeypatch) -> None:
    mw = _stub_middleware(fail_with=TimeoutError("first event timeout"))

    async def broken_get_model(**_kwargs):
        raise RuntimeError("no fallback llm")

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", broken_get_model)

    protected = protect_summarization_middleware(
        mw, fallback_model="openai/fallback-model", thinking=None
    )

    with pytest.raises(RuntimeError, match="no fallback llm"):
        await protected._acreate_summary([HumanMessage(content="history")])


def test_protect_is_idempotent() -> None:
    mw = _stub_middleware(fail_with=TimeoutError("boom"))
    once = protect_summarization_middleware(mw, fallback_model="openai/fallback-model")
    twice = protect_summarization_middleware(once, fallback_model="openai/fallback-model")

    assert once is twice


def test_patch_window_wraps_deepagents_summarization_factory(monkeypatch) -> None:
    """deepagents.graph.create_summarization_middleware 在窗口内被替换、窗口外恢复。"""
    import deepagents.graph as deepagents_graph
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    original = deepagents_graph.create_summarization_middleware
    model = GenericFakeChatModel(messages=iter([AIMessage("ok")] * 10))

    with summarization_fallback_patch("openai/fallback-model"):
        built = deepagents_graph.create_summarization_middleware(model, object())
        assert getattr(built._acreate_summary, "_lambchat_summary_fallback", False) is True

    assert deepagents_graph.create_summarization_middleware is original

    built_after = original(model, object())
    assert getattr(built_after._acreate_summary, "_lambchat_summary_fallback", False) is False


def test_patch_window_without_fallback_model_injects_counter_only() -> None:
    """无兜底模型：工厂仍被替换（注入计数器），但不加摘要兜底保护。"""
    import deepagents.graph as deepagents_graph
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    original = deepagents_graph.create_summarization_middleware
    model = GenericFakeChatModel(messages=iter([AIMessage("ok")] * 10))

    with summarization_fallback_patch(None):
        assert deepagents_graph.create_summarization_middleware is not original
        built = deepagents_graph.create_summarization_middleware(model, object())
        assert getattr(built._acreate_summary, "_lambchat_summary_fallback", False) is False

    assert deepagents_graph.create_summarization_middleware is original


def test_image_aware_counter_charges_realistic_image_cost() -> None:
    """图片按真实成本计价（对齐 codex 的 7373 字节 ≈ 1844 token/张），不再按 85 低估。"""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    from src.infra.agent.middleware.summary_fallback import _image_aware_counter_for

    model = GenericFakeChatModel(messages=iter([AIMessage("ok")] * 10))
    counter = _image_aware_counter_for(model)

    text_only = HumanMessage(content="same text")
    with_image = HumanMessage(
        content=[
            {"type": "text", "text": "same text"},
            {"type": "image_url", "image_url": {"url": "https://x/img.png"}},
        ]
    )

    assert counter([with_image]) - counter([text_only]) >= 1844


def test_patch_injects_image_aware_counter_even_without_fallback(monkeypatch) -> None:
    """无兜底模型时也要注入图片感知计数器（否则图片对压缩触发器不可见）。"""
    import deepagents.graph as deepagents_graph
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    model = GenericFakeChatModel(messages=iter([AIMessage("ok")] * 10))
    original = deepagents_graph.create_summarization_middleware
    captured: dict = {}

    def fake_original(model, backend, **kwargs):
        captured.update(kwargs)
        return original(model, backend, **kwargs)

    monkeypatch.setattr(deepagents_graph, "create_summarization_middleware", fake_original)

    with summarization_fallback_patch(None):
        deepagents_graph.create_summarization_middleware(model, object())

    assert "token_counter" in captured
    assert captured["token_counter"] is not None


def test_patch_does_not_override_explicit_token_counter(monkeypatch) -> None:
    import deepagents.graph as deepagents_graph
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    model = GenericFakeChatModel(messages=iter([AIMessage("ok")] * 10))
    original = deepagents_graph.create_summarization_middleware
    captured: dict = {}

    def fake_original(model, backend, **kwargs):
        captured.update(kwargs)
        return original(model, backend, **kwargs)

    monkeypatch.setattr(deepagents_graph, "create_summarization_middleware", fake_original)
    explicit = lambda messages: 0  # noqa: E731

    with summarization_fallback_patch(None):
        deepagents_graph.create_summarization_middleware(model, object(), token_counter=explicit)

    assert captured["token_counter"] is explicit
