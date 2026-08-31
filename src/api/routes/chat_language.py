"""chat 路由的响应语言解析。

界面 locale 经 Accept-Language 头进入，被固定到 agent_options 后随既有
链路（task_context / submit / submit_arq / scheduler）透传到各 agent
节点，由 SectionPromptMiddleware 注入系统提示词。
"""

from __future__ import annotations

from src.agents.core.subagent_prompts import RESPONSE_LANGUAGE_NAMES


def resolve_response_language(accept_language: str | None) -> str | None:
    """从 Accept-Language 头解析用户界面语言，用于固定模型回复语言。

    与 auth.utils._get_language 不同：无法识别时返回 None 而非回落
    "en"，让 agent 不注入语言提示段，保留模型跟随用户消息语言的默认
    行为（未带头的 API 客户端不受影响）。
    """
    if not accept_language:
        return None
    lang = accept_language.split(",")[0].split("-")[0].strip().lower()
    return lang if lang in RESPONSE_LANGUAGE_NAMES else None


def apply_response_language(agent_options: dict, accept_language: str | None) -> str | None:
    """把界面 locale 固定到 agent_options，随既有链路透传到各 agent 节点。"""
    language = resolve_response_language(accept_language)
    if language is not None:
        agent_options["response_language"] = language
    return language
