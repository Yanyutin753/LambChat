"""响应语言段的 prompt-cache 稳定性契约。

LambChat 的前缀缓存要求连续轮次的 system message 字节一致（见
prompt_injection.py 的会话快照设计与 build_model_facing_message 的
写时注入约束）。语言段是 agent_options 的纯函数，必须满足同样约束：

- 同一 locale 跨轮/跨请求 → 字节稳定（cache_read 持续命中）
- 无 locale（未带 Accept-Language 的 API 客户端）→ 与历史字节完全一致
  （零缓存影响）
- 切换 locale 只改语言段本身（单次前缀失效，之后重新稳定）
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage

from src.agents.core.persona import build_persona_prompt_sections
from src.agents.core.subagent_prompts import (
    MAIN_AGENT_PROMPT_SECTIONS,
    build_response_language_section,
)
from src.infra.agent.middleware._helpers import _append_system_text_block
from src.infra.agent.middleware.prompt_injection import SectionPromptMiddleware

_BASE_SYSTEM = SystemMessage(content="You are a deep agent with tools.")
_PERSONA = "你是一位资深后端工程师。\n\n回答保持严谨，给出可验证的结论。"


def _node_sections(persona_prompt: str | None, language: str | None) -> list[str]:
    """按节点实际组装顺序构造段落：policies → persona → memory → language。"""
    return [
        s
        for s in (
            *MAIN_AGENT_PROMPT_SECTIONS,
            *build_persona_prompt_sections(persona_prompt),
            "",  # memory_guide（ENABLE_MEMORY 关闭时为空串）
            build_response_language_section(language),
        )
        if s
    ]


def _render_turn(language: str | None) -> str:
    """渲染一轮模型调用的最终 system message 字节。"""
    middleware = SectionPromptMiddleware(sections=_node_sections(_PERSONA, language))
    return str(_append_system_text_block(_BASE_SYSTEM, middleware._prompt).content)


def test_same_locale_produces_identical_system_message_across_turns() -> None:
    # 连续轮次（乃至不同副本上的两次构造）必须字节一致，前缀缓存才不失效
    assert _render_turn("zh") == _render_turn("zh")
    assert "Simplified Chinese" in _render_turn("zh")


def test_absent_locale_keeps_pre_feature_prompt_bytes() -> None:
    # 未带 Accept-Language 的客户端：语言段缺失，其余段落与历史字节一致
    legacy_middleware = SectionPromptMiddleware(
        sections=[
            s
            for s in (*MAIN_AGENT_PROMPT_SECTIONS, *build_persona_prompt_sections(_PERSONA))
            if s
        ]
    )
    legacy_prompt = legacy_middleware._prompt

    current_prompt = SectionPromptMiddleware(
        sections=_node_sections(_PERSONA, None)
    )._prompt

    assert "Response Language" not in current_prompt
    assert current_prompt == legacy_prompt


def test_locale_switch_only_alters_the_language_block() -> None:
    # 用户中途切换界面语言：失效范围仅限语言段内的语言名，其余前缀不变
    zh_prompt = _render_turn("zh")
    en_prompt = _render_turn("en")

    marker = "### Response Language"
    assert zh_prompt.split(marker)[0] == en_prompt.split(marker)[0]
    assert zh_prompt.rsplit("respond in ", 1)[0] == en_prompt.rsplit("respond in ", 1)[0]
    assert zh_prompt != en_prompt


def test_language_section_is_deterministic_for_each_locale() -> None:
    for language in ("en", "zh", "ja", "ko", "ru"):
        assert build_response_language_section(language) == build_response_language_section(
            language
        )
