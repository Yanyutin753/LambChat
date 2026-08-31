"""响应语言注入链路的纯函数测试。

界面 locale 通过 Accept-Language 头进入 chat 路由，被固定到
agent_options["response_language"]，由各 agent 节点注入系统提示词。
"""

from __future__ import annotations

from src.api.routes.chat import build_conversation_config
from src.api.routes.chat_language import apply_response_language, resolve_response_language
from src.kernel.schemas.agent import AgentRequest


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


def test_conversation_config_persists_language_for_retry_and_scheduled_paths() -> None:
    # 定时任务/断点恢复从持久化的 agent_options 重建执行上下文，
    # 语言必须随之持久化，重试轮次注入的字节才与首轮一致（前缀缓存不失效）
    request = AgentRequest(
        message="你好",
        agent_options={"model": "gpt-test", "response_language": "zh"},
    )

    config = build_conversation_config(
        run_id="run-1",
        agent_id="fast",
        request=request,
        language="zh",
        session_id="session-1",
    )

    assert config["agent_options"]["response_language"] == "zh"
