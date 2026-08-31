"""响应语言注入链路的纯函数测试。

界面 locale 通过 Accept-Language 头进入 chat 路由，被固定到
agent_options["response_language"]，由各 agent 节点注入系统提示词。
"""

from __future__ import annotations

from src.api.routes.chat_language import apply_response_language, resolve_response_language


def test_resolve_response_language_accepts_primary_tag_from_accept_language() -> None:
    assert resolve_response_language("zh-CN,zh;q=0.9,en;q=0.8") == "zh"
    assert resolve_response_language("en-US,en;q=0.9") == "en"
    assert resolve_response_language("ru") == "ru"
    assert resolve_response_language("JA") == "ja"


def test_resolve_response_language_returns_none_for_missing_or_unsupported() -> None:
    assert resolve_response_language(None) is None
    assert resolve_response_language("") is None
    assert resolve_response_language("fr-CA,fr;q=0.9") is None


def test_apply_response_language_pins_locale_into_agent_options() -> None:
    agent_options = {"model": "gpt-test"}

    applied = apply_response_language(agent_options, "zh-CN,zh;q=0.9")

    assert applied == "zh"
    assert agent_options["response_language"] == "zh"
    assert agent_options["model"] == "gpt-test"


def test_apply_response_language_keeps_options_untouched_without_header() -> None:
    agent_options = {"model": "gpt-test"}

    assert apply_response_language(agent_options, None) is None
    assert "response_language" not in agent_options
