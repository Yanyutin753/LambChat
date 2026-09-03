"""Codex 式会话基线装配策略（从 api 路由下沉，保 chat.py 行数红线）。

照搬 openai/codex 的提示缓存设计：稳定内容（记忆索引）在消息头部注入一次，
报时漂移、目标签名去重，变化内容一律靠后；工具描述保持全静态。
"""

from __future__ import annotations

from src.infra.chat.model_facing import build_model_facing_message
from src.kernel.config import settings


async def session_has_prior_messages(session_id: str, *, exclude_run_id: str | None = None) -> bool:
    """会话是否已有历史消息（按 traces 计数）。exclude_run_id 用于 executor
    侧判定首轮：本 run 的用户消息 trace 在 executor 开跑前已写入，需排除。"""
    from src.infra.storage.mongodb import get_mongo_client

    client = get_mongo_client()
    query: dict = {"session_id": session_id}
    if exclude_run_id:
        query["run_id"] = {"$ne": exclude_run_id}
    count = await client[settings.MONGODB_DB][settings.MONGODB_TRACES_COLLECTION].count_documents(
        query
    )
    return count > 0


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


async def _should_inject_session_memory(
    session_id: str | None, *, exclude_run_id: str | None = None
) -> bool:
    """Codex 式会话基线：记忆块只在会话首轮注入一次，之后 append-only——
    逐轮注入的内容各异的块会击穿 provider 前缀缓存（生产实测）。
    开关关闭时零查询成本。"""
    if not getattr(settings, "ENABLE_MEMORY", False):
        return False
    if not getattr(settings, "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED", False):
        return False
    if not session_id:
        return True  # 全新会话，必为首轮
    return not await session_has_prior_messages(session_id, exclude_run_id=exclude_run_id)


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
    """POST 侧只做零成本本地格式化（报时 → 技能 → 目标块）；首轮记忆装配
    （索引基线 + 相关记忆快照）移至 executor 后台执行，提交延迟与召回解耦。
    返回 (消息, 是否注入了目标块)。"""
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


async def inject_session_memory(message: str, *, user_id: str, raw_query: str | None) -> str:
    """首轮记忆装配（executor 后台）：索引基线置头、相关记忆快照置尾。

    字节顺序与 POST 侧装配完全一致（基线 → 报时/技能/目标 → 快照），仅
    执行时机移出提交关键路径——持久化与发送字节不变，前缀缓存语义不变。
    一切失败静默降级为不注入（由底层 best-effort 保证）。"""
    from src.infra.agent.middleware.prompt_injection import build_session_memory_baseline
    from src.infra.chat.memory_context import append_memory_context

    baseline = await build_session_memory_baseline(user_id)
    if baseline:
        message = f"{baseline}\n\n{message}"
    return await append_memory_context(message, user_id, raw_query=raw_query)
