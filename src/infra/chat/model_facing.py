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
    include_timestamp: bool = True,
    include_turn_context: bool = True,
) -> str:
    """Codex 式装配，稳定内容在前、变化内容在后，全部写时一次性：

    - include_timestamp=False 时省略报时前缀（漂移注入：距上次报时超过
      阈值或会话首轮才带，长会话省 ~80% 报时 token；位于最新消息上，
      不影响前缀缓存）
    - include_turn_context=False 时省略 goal/自动模式块（签名去重：目标
      未变不重复注入，历史中已有同字节块）
    - include_memory=False 时跳过记忆快照（仅会话首轮注入）
    """
    if include_timestamp:
        formatted = format_user_message_with_timestamp(raw_message, user_timezone)
    else:
        formatted = raw_message
    formatted = append_required_skills_prompt(formatted, enabled_skills)
    if include_turn_context:
        formatted = append_turn_context_prompt(formatted, active_goal, auto_mode)
    if include_memory:
        formatted = await append_memory_context(formatted, user_id, raw_query=raw_message)
    return formatted
