"""对话轮结束后的沙箱空闲暂停（省成本）。

每个 run 到达终态（completed / failed / cancelled / expired / waiting_human）
后，检查该用户是否还有进行中的对话可能需要沙箱；没有则立即暂停沙箱，
不再干等空闲超时烧算力。waiting_human 也触发：等人工输入可能很久，
暂停后恢复对话时 get_or_create 自动唤醒，全程无感。

安全边界：
- 快速连发消息由宽限期吸收，避免每条消息都触发暂停+恢复抖动；
- 新 run 在暂停后才提交也安全——下次 get_or_create 会自动恢复（已验证链路）；
- 本模块所有失败只记日志，绝不影响对话主流程。
"""

from __future__ import annotations

import asyncio

from src.infra.logging import get_logger

logger = get_logger(__name__)

# 终态后的宽限秒数：吸收用户连续对话节奏（暂停+恢复有快照开销，不值得抖动）
_IDLE_GRACE_SECONDS = 60

# 仍可能需要沙箱的会话状态（waiting_human 有意排除：等人期间暂停，恢复无感）
_ACTIVE_TASK_STATUSES = frozenset(
    {
        "queued",
        "pending",
        "starting",
        "running",
        "recovering",
        "cancelling",
    }
)

# 只有带暂停语义的云端平台参与（local 无沙箱池，daytona 走自身 auto-delete）
_IDLE_PAUSE_PLATFORMS = frozenset({"e2b", "cubesandbox"})

# 触发空闲暂停检查的 run 终态（waiting_human 有意包含：等人期间暂停，恢复无感）
IDLE_PAUSE_TRIGGER_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "cancelled",
        "expired",
        "waiting_human",
    }
)

# 已有待检任务的 user（进程内去重；跨 pod 重复触发是幂等的）
_pending_users: set[str] = set()


async def maybe_pause_user_sandbox(user_id: str) -> bool:
    """无进行中对话需要沙箱时暂停该用户的沙箱；返回是否实际暂停。"""
    try:
        from src.kernel.config import settings

        if not getattr(settings, "SANDBOX_PAUSE_WHEN_IDLE", True):
            return False
        if settings.SANDBOX_PLATFORM.lower() not in _IDLE_PAUSE_PLATFORMS:
            return False
        if await _count_active_runs(user_id) > 0:
            return False

        from src.infra.sandbox.session_manager import get_session_sandbox_manager

        stopped = await get_session_sandbox_manager().stop(user_id)
        if stopped:
            logger.info(
                "[sandbox-idle] Paused sandbox for user %s (no active runs need it)",
                user_id,
            )
        return stopped
    except Exception as e:
        logger.warning("[sandbox-idle] Pause check failed for user %s: %s", user_id, e)
        return False


async def _count_active_runs(user_id: str) -> int:
    """统计该用户仍处于进行中状态的会话数（跨 pod 一致，读 sessions 集合）。"""
    from src.infra.storage.mongodb import get_mongo_client
    from src.kernel.config import settings

    client = get_mongo_client()
    return await client[settings.MONGODB_DB]["sessions"].count_documents(
        {
            "user_id": user_id,
            "metadata.task_status": {"$in": sorted(_ACTIVE_TASK_STATUSES)},
        }
    )


def schedule_idle_pause(user_id: str) -> None:
    """终态后延迟触发空闲暂停检查（fire-and-forget，同 user 去重）。"""
    if not user_id or user_id in _pending_users:
        return

    async def _delayed() -> None:
        try:
            await asyncio.sleep(_IDLE_GRACE_SECONDS)
            await maybe_pause_user_sandbox(user_id)
        finally:
            _pending_users.discard(user_id)

    try:
        task = asyncio.create_task(_delayed())
    except RuntimeError:
        # 无运行中的事件循环（同步上下文）——静默放弃，空闲超时兜底
        return
    _pending_users.add(user_id)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
