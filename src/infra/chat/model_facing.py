"""模型侧用户消息装配（从 api 路由下沉到 chat 基础设施层）。

用户消息只包含时间戳、技能与轮次上下文。跨会话记忆由 memory_recall
工具按需检索，不注入用户消息。
"""

from __future__ import annotations

from src.infra.chat.turn_context import append_turn_context_prompt
from src.infra.chat.user_message_timestamp import format_user_message_with_timestamp
from src.infra.goal import GoalSpec


def append_required_skills_prompt(message: str, enabled_skills: list[str] | None) -> str:
    """Append a run-scoped instruction for explicitly selected skills."""
    if not enabled_skills:
        return message

    skill_paths = "\n".join(f"- {name}: /skills/{name}/SKILL.md" for name in enabled_skills if name)
    if not skill_paths:
        return message

    return (
        f"{message}\n\n"
        "<required_skills>\n"
        "Required skills for this message:\n"
        f"{skill_paths}\n\n"
        "You must read and follow the SKILL.md instructions for each required skill "
        "before answering. Use these skills for this message unless the request is "
        "impossible or unsafe, and clearly say so if you cannot use them.\n"
        "</required_skills>"
    )


async def build_model_facing_message(
    raw_message: str,
    user_timezone: str | None,
    enabled_skills: list[str] | None,
    active_goal: GoalSpec | None,
    auto_mode: bool,
    user_id: str,
    include_memory: bool = False,
    include_timestamp: bool = True,
    include_turn_context: bool = True,
) -> str:
    """装配本轮模型消息。

    `include_memory` 仅保留调用兼容性，记忆始终不进入用户消息。
    """
    if include_timestamp:
        formatted = format_user_message_with_timestamp(raw_message, user_timezone)
    else:
        formatted = raw_message
    formatted = append_required_skills_prompt(formatted, enabled_skills)
    if include_turn_context:
        formatted = append_turn_context_prompt(formatted, active_goal, auto_mode)
    return formatted
