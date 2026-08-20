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


def test_patch_window_noop_without_fallback_model() -> None:
    import deepagents.graph as deepagents_graph

    original = deepagents_graph.create_summarization_middleware

    with summarization_fallback_patch(None):
        assert deepagents_graph.create_summarization_middleware is original
