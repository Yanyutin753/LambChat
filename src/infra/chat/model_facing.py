"""模型侧用户消息装配（从 api 路由下沉到 chat 基础设施层）。

时间戳 → 技能 → 轮次上下文 → 相关记忆块：所有按轮变化的动态内容在消息
创建时一次性写入并随状态持久化，使持久化历史与发送给模型的字节逐字一致，
provider prompt-cache 前缀跨轮连续；前端展示用原始 raw_message，不受影响。
"""

from __future__ import annotations

from src.infra.chat.memory_context import append_memory_context
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
    include_memory: bool = True,
) -> str:
    """include_memory=False 时跳过记忆块（POST 关键路径不再等召回）——块由
    _execute_agent_stream 在后台追加，字节顺序不变（记忆块本来就是最后一段）。
    """
    formatted = format_user_message_with_timestamp(raw_message, user_timezone)
    formatted = append_required_skills_prompt(formatted, enabled_skills)
    formatted = append_turn_context_prompt(formatted, active_goal, auto_mode)
    if include_memory:
        formatted = await append_memory_context(formatted, user_id, raw_query=raw_message)
    return formatted
