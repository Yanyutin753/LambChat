"""Tests for summary freed-token stats.

自动摘要压缩发生后，被摘要的历史消息会被替换为一条摘要消息。包装层用
中间件自己的 token 计数器计算「压缩前 − 压缩后」的差值，经 presenter 推送
一条 ``summary`` SSE 事件（content 为空、携带 freed_tokens），前端总结
Item 据此展示本次压缩释放了多少 token。

统计属尽力而为：presenter 缺失、计数器异常等任何失败都不得影响摘要主流程。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage, HumanMessage

from src.infra.agent.middleware.summary_fallback import (
    summarization_fallback_patch,
)
from src.infra.agent.middleware.summary_stats import (
    _SUMMARY_MESSAGE_PREFIX,
    attach_summary_token_stats,
)


def _stub_middleware(
    *,
    summary: str = "short summary",
    token_counter=None,
):
    mw = SimpleNamespace()
    mw.token_counter = token_counter or (
        lambda messages: sum(len(str(m.content)) for m in messages)
    )

    async def ok(_messages):
        return summary

    mw._acreate_summary = ok
    return mw


class _FakePresenter:
    def __init__(self):
        self.events = []

    def present_summary(
        self,
        content,
        summary_id=None,
        depth=0,
        agent_id=None,
        freed_tokens=None,
    ):
        return {
            "event": "summary",
            "data": {
                "content": content,
                "summary_id": summary_id,
                "depth": depth,
                "agent_id": agent_id,
                "freed_tokens": freed_tokens,
            },
        }

    async def emit(self, event):
        self.events.append(event)
        return event


def _patch_get_config(monkeypatch, presenter=None, checkpoint_ns="", raises=False):
    import langgraph.config as lc_config

    if raises:

        def _raise():
            raise RuntimeError("not in a run")

        monkeypatch.setattr(lc_config, "get_config", _raise)
        return

    monkeypatch.setattr(
        lc_config,
        "get_config",
        lambda: {"configurable": {"presenter": presenter, "checkpoint_ns": checkpoint_ns}},
    )


async def test_emits_freed_tokens_after_successful_summary(monkeypatch):
    presenter = _FakePresenter()
    _patch_get_config(monkeypatch, presenter)
    history = [HumanMessage(content="a" * 400), AIMessage(content="b" * 400)]
    mw = attach_summary_token_stats(_stub_middleware(summary="short summary"))

    result = await mw._acreate_summary(history)

    assert result == "short summary"
    before = 800
    after = len(_SUMMARY_MESSAGE_PREFIX + "short summary")
    [event] = presenter.events
    assert event["event"] == "summary"
    assert event["data"]["freed_tokens"] == before - after
    assert event["data"]["content"] == ""
    assert event["data"]["depth"] == 0


async def test_missing_presenter_does_not_break_summary(monkeypatch):
    _patch_get_config(monkeypatch, presenter=None)
    mw = attach_summary_token_stats(_stub_middleware())

    assert await mw._acreate_summary([HumanMessage(content="x")]) == "short summary"


async def test_get_config_outside_run_does_not_break_summary(monkeypatch):
    _patch_get_config(monkeypatch, raises=True)
    mw = attach_summary_token_stats(_stub_middleware())

    assert await mw._acreate_summary([HumanMessage(content="x")]) == "short summary"


async def test_no_positive_freed_tokens_sends_no_event(monkeypatch):
    """摘要没有带来上下文缩减时不发事件（freed <= 0）。"""
    presenter = _FakePresenter()
    _patch_get_config(monkeypatch, presenter)
    mw = attach_summary_token_stats(_stub_middleware(token_counter=lambda _messages: 10))

    assert await mw._acreate_summary([HumanMessage(content="x")]) == "short summary"
    assert presenter.events == []


async def test_depth_follows_checkpoint_ns(monkeypatch):
    """depth 推导对齐 AgentEventProcessor：checkpoint_ns 含「|」视为子代理。"""
    presenter = _FakePresenter()
    _patch_get_config(monkeypatch, presenter, checkpoint_ns="task:abc|task:def")
    mw = attach_summary_token_stats(_stub_middleware())

    await mw._acreate_summary([HumanMessage(content="a" * 400)])

    [event] = presenter.events
    assert event["data"]["depth"] == 1


async def test_token_counter_failure_is_swallowed(monkeypatch):
    presenter = _FakePresenter()
    _patch_get_config(monkeypatch, presenter)

    def broken(_messages):
        raise ValueError("counter exploded")

    mw = attach_summary_token_stats(_stub_middleware(token_counter=broken))

    assert await mw._acreate_summary([HumanMessage(content="x")]) == "short summary"
    assert presenter.events == []


def test_attach_is_idempotent():
    mw = attach_summary_token_stats(_stub_middleware())
    once = attach_summary_token_stats(mw)

    assert once is mw


def test_patch_window_attaches_stats_marker(monkeypatch):
    """窗口内构建的摘要中间件总是带上 stats 包装（无论是否配置兜底模型）。"""
    import deepagents.graph as deepagents_graph
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    _patch_get_config(monkeypatch, _FakePresenter())
    original = deepagents_graph.create_summarization_middleware
    model = GenericFakeChatModel(messages=iter([AIMessage("ok")] * 10))

    with summarization_fallback_patch(None):
        built = deepagents_graph.create_summarization_middleware(model, object())
        assert getattr(built._acreate_summary, "_lambchat_summary_stats", False) is True

    assert deepagents_graph.create_summarization_middleware is original


async def test_fallback_summary_success_still_emits_stats(monkeypatch):
    """主模型摘要失败换兜底模型成功时，stats 也要发（stats 包装在最外层）。"""
    import httpx
    import openai

    presenter = _FakePresenter()
    _patch_get_config(monkeypatch, presenter)

    response = httpx.Response(status_code=401, request=httpx.Request("POST", "http://test/v1/chat"))
    body = {"error": {"code": "", "message": "Invalid token", "type": "new_api_error"}}
    auth_error = openai.AuthenticationError(
        "Error code: 401 - Invalid token", response=response, body=body
    )

    async def failing(_messages):
        raise auth_error

    mw = SimpleNamespace()
    mw.token_counter = lambda messages: sum(len(str(m.content)) for m in messages)
    mw._acreate_summary = failing

    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    fallback_llm = GenericFakeChatModel(messages=iter([AIMessage("ok")] * 10))
    get_model = AsyncMock(return_value=fallback_llm)
    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", get_model)

    from src.infra.agent.middleware.summary_fallback import (
        protect_summarization_middleware,
    )

    protected = protect_summarization_middleware(
        mw, fallback_model="openai/fallback-model", thinking=None
    )
    wrapped = attach_summary_token_stats(
        protected,
        passthrough_markers=("_lambchat_summary_fallback",),
    )

    result = await wrapped._acreate_summary([HumanMessage(content="a" * 400)])

    assert result == "ok"
    [event] = presenter.events
    assert event["data"]["freed_tokens"] == 400 - len(_SUMMARY_MESSAGE_PREFIX + "ok")
