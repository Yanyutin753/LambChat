"""模型侧会话消息装配策略（从 api 路由下沉，保 chat.py 行数红线）。

记忆不进入用户消息；这里只负责报时漂移与目标签名去重。
"""

from __future__ import annotations

from src.infra.chat.model_facing import build_model_facing_message

# 报时漂移阈值：超过未报时才带时间戳前缀（Codex current_time_reminder 模式）
TIME_REPORT_DRIFT_SECONDS = 30 * 60


def _turn_context_signature(active_goal, auto_mode: bool) -> str | None:
    """goal/自动模式块的内容签名——None 表示本轮无块。"""
    if active_goal is None and not auto_mode:
        return None
    goal_part = getattr(active_goal, "objective", "") or "" if active_goal else ""
    return f"{goal_part}|auto={bool(auto_mode)}"


def _time_report_due(existing_metadata: dict | None) -> bool:
    """距上次报时是否超过漂移阈值（首轮/无记录=应报）。"""
    last = (existing_metadata or {}).get("prompt_time_reported_at")
    if not last:
        return True
    try:
        from datetime import datetime, timezone

        last_dt = datetime.fromisoformat(str(last))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last_dt).total_seconds() >= TIME_REPORT_DRIFT_SECONDS
    except (TypeError, ValueError):
        return True


async def assemble_first_turn_message(
    *,
    raw_message: str,
    user_timezone: str | None,
    enabled_skills: list[str] | None,
    active_goal,
    auto_mode: bool,
    user_id: str,
    include_timestamp: bool,
    last_tc_signature: str | None,
) -> tuple[str, bool]:
    """装配报时、技能与目标块；记忆不进入用户消息。

    返回 (消息, 是否注入了目标块)。
    """
    tc_signature = _turn_context_signature(active_goal, auto_mode)
    inject_turn_context = tc_signature is not None and tc_signature != last_tc_signature

    formatted = await build_model_facing_message(
        raw_message,
        user_timezone,
        enabled_skills,
        active_goal,
        auto_mode,
        user_id,
        include_memory=False,
        include_timestamp=include_timestamp,
        include_turn_context=inject_turn_context,
    )
    return formatted, inject_turn_context
