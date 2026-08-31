"""Codex 同款 /v1/responses KV 缓存优化。

对齐 openai/codex（codex-rs client.rs）的三个请求整形手段，确保
LambChat responses 线格式模型的 KV 缓存命中率高：

- ``prompt_cache_key``：会话级稳定路由提示，同一会话的跨轮请求落到
  同一缓存机器（codex-rs: `prompt_cache_key = session_id`）。
  /v1/responses 与 /v1/chat/completions 两种线格式都注入（SDK 3.6.0
  起后者同样支持该字段，替代 user 做缓存路由）。
- ``include: ["reasoning.encrypted_content"]``：推理内容加密回传，重放
  历史时前缀与生成时 token 级一致（codex-rs 无条件携带）。
- ``store: False``：无状态全量重放，不依赖服务端会话存储（codex-rs 强制）。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from src.infra.llm.client import LLMClient
from src.infra.llm.responses_cache import (
    current_responses_prompt_cache_key,
    reset_responses_prompt_cache_key,
    session_prompt_cache_key,
    set_responses_prompt_cache_key,
)
from src.kernel.config import settings

AGENTS_BASE_SOURCE = Path("src/agents/core/base.py").read_text(encoding="utf-8")


def _responses_model():
    return LLMClient._create_model(
        "openai",
        "gpt-5.2",
        temperature=0.7,
        api_key="sk-test",
        api_format="responses",
    )


def _chat_model():
    return LLMClient._create_model(
        "openai",
        "gpt-5.2",
        temperature=0.7,
        api_key="sk-test",
    )


@pytest.fixture(autouse=True)
def _clear_prompt_cache_key():
    token = set_responses_prompt_cache_key(None)
    yield
    reset_responses_prompt_cache_key(token)


# ── 模型构造默认值（include / store）──────────────────────────────────────


def test_responses_model_gets_codex_cache_defaults() -> None:
    model = _responses_model()
    assert model.include == ["reasoning.encrypted_content"]
    assert model.store is False


def test_chat_completions_model_gets_no_cache_defaults() -> None:
    model = _chat_model()
    assert model.include is None
    assert model.store is None


def test_kill_switch_disables_codex_cache_defaults(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_KV_CACHE", False, raising=False)
    model = _responses_model()
    assert model.include is None
    assert model.store is None


def test_responses_cache_policy_lives_in_payload_not_model_kwargs() -> None:
    model = _responses_model()
    assert "prompt_cache_key" not in model.model_kwargs
    assert model.prompt_cache_options is None


# ── prompt_cache_key 按次注入 ─────────────────────────────────────────────


def test_payload_injects_session_prompt_cache_key() -> None:
    model = _responses_model()
    token = set_responses_prompt_cache_key("session-42")
    try:
        payload = model._get_request_payload([HumanMessage(content="hi")])
    finally:
        reset_responses_prompt_cache_key(token)
    assert payload["prompt_cache_key"] == "session-42"


def test_payload_injection_absent_without_session_context() -> None:
    model = _responses_model()
    payload = model._get_request_payload([HumanMessage(content="hi")])
    assert "prompt_cache_key" not in payload


def test_chat_completions_payload_also_gets_prompt_cache_key() -> None:
    # SDK 3.6.0 起 /v1/chat/completions 同样支持 prompt_cache_key（替代 user
    # 字段做缓存路由）；非 responses 渠道（OpenAI chat / 中转 GLM 等）同样受益
    model = _chat_model()
    token = set_responses_prompt_cache_key("session-42")
    try:
        payload = model._get_request_payload([HumanMessage(content="hi")])
    finally:
        reset_responses_prompt_cache_key(token)
    assert payload["prompt_cache_key"] == "session-42"


def test_kill_switch_disables_payload_injection(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_KV_CACHE", False, raising=False)
    model = _responses_model()
    token = set_responses_prompt_cache_key("session-42")
    try:
        payload = model._get_request_payload([HumanMessage(content="hi")])
    finally:
        reset_responses_prompt_cache_key(token)
    assert "prompt_cache_key" not in payload


def test_kill_switch_disables_chat_completions_injection(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_KV_CACHE", False, raising=False)
    model = _chat_model()
    token = set_responses_prompt_cache_key("session-42")
    try:
        payload = model._get_request_payload([HumanMessage(content="hi")])
    finally:
        reset_responses_prompt_cache_key(token)
    assert "prompt_cache_key" not in payload


def test_explicit_invoke_kwarg_wins_over_context_key() -> None:
    model = _responses_model()
    token = set_responses_prompt_cache_key("session-42")
    try:
        payload = model._get_request_payload(
            [HumanMessage(content="hi")], prompt_cache_key="caller-key"
        )
    finally:
        reset_responses_prompt_cache_key(token)
    assert payload["prompt_cache_key"] == "caller-key"


# ── ContextVar 帮助函数 ──────────────────────────────────────────────────


def test_session_prompt_cache_key_scopes_value() -> None:
    assert current_responses_prompt_cache_key() is None
    with session_prompt_cache_key("outer-session"):
        assert current_responses_prompt_cache_key() == "outer-session"
        with session_prompt_cache_key("inner-session"):
            assert current_responses_prompt_cache_key() == "inner-session"
        assert current_responses_prompt_cache_key() == "outer-session"
    assert current_responses_prompt_cache_key() is None


def test_session_prompt_cache_key_restores_on_error() -> None:
    class BoomError(Exception):
        pass

    with pytest.raises(BoomError), session_prompt_cache_key("doomed-session"):
        raise BoomError()
    assert current_responses_prompt_cache_key() is None


def test_blank_session_id_yields_no_key() -> None:
    with session_prompt_cache_key("   "):
        assert current_responses_prompt_cache_key() is None


def test_overlong_session_id_is_truncated() -> None:
    with session_prompt_cache_key("s" * 100):
        assert len(current_responses_prompt_cache_key() or "") == 64


# ── Agent 执行层接线（源码结构）──────────────────────────────────────────


def test_base_graph_agent_binds_session_key_around_graph_execution() -> None:
    # fast/search/team 各自重写 _stream，绑定必须放在未被重写的公共入口：
    # stream() → _stream_with_cache_key() → self._stream(...)
    assert "return self._stream_with_cache_key(" in AGENTS_BASE_SOURCE
    assert "set_responses_prompt_cache_key(session_id)" in AGENTS_BASE_SOURCE
    assert "reset_responses_prompt_cache_key(cache_key_token)" in AGENTS_BASE_SOURCE
    assert "async for event in self._stream(message, session_id" in AGENTS_BASE_SOURCE
    assert "session_prompt_cache_key(session_id)" in AGENTS_BASE_SOURCE


# ── 回归：缓存默认值不影响 payload 其余部分 ─────────────────────────────


def test_responses_payload_shape_unaffected_by_cache_defaults() -> None:
    model = _responses_model()
    payload = model._get_request_payload([HumanMessage(content="hi")])
    assert payload["model"] == "gpt-5.2"
    assert payload["store"] is False
    assert payload["include"] == ["reasoning.encrypted_content"]
    assert isinstance(payload["input"], list)


def test_auto_detect_model_still_gets_prompt_cache_key() -> None:
    # use_responses_api=None（自动探测）的实例：纯文本消息走 chat completions
    # 分支，同样注入会话级 key（两种线格式都支持该字段）。
    from src.infra.llm.openai_chat import LambChatOpenAIChatModel

    class _Foreign(LambChatOpenAIChatModel):
        pass

    foreign = _Foreign(model="gpt-5.2", api_key="sk-test")  # type: ignore[call-arg]
    token = set_responses_prompt_cache_key("session-42")
    try:
        payload = foreign._get_request_payload([HumanMessage(content="hi")])
    finally:
        reset_responses_prompt_cache_key(token)
    assert payload["prompt_cache_key"] == "session-42"


def test_context_helpers_accept_mock_session_ids() -> None:
    # session_id 可能是 MagicMock（测试脚手架传入）：非字符串一律视为无 key
    token = set_responses_prompt_cache_key(MagicMock())
    try:
        assert current_responses_prompt_cache_key() is None
    finally:
        reset_responses_prompt_cache_key(token)
