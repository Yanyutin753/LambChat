"""对话轮结束后的沙箱空闲暂停（省成本）。

每个 run 到达终态（completed / failed / cancelled / expired / waiting_human）
后，检查该用户是否还有进行中的对话可能需要沙箱；没有则立即暂停沙箱，
不再干等空闲超时烧算力。waiting_human 也触发：等人工输入可能很久，
暂停后恢复对话时 get_or_create 自动唤醒，全程无感。

浏览生命周期（桌面「云端电脑」面板）：
- 云端文件浏览（fs/cloud/list|read）会唤醒 paused 沙箱并保活——每次
  浏览请求 touch 一份**浏览租约**（Redis TTL，默认 10 分钟）；
- 租约存续期间本模块的空闲暂停豁免（用户正在看，别打断浏览）；
- 浏览唤醒的沙箱没有 run 终态事件可挂，由**浏览回收器**兜底：宽限窗
  内无新浏览且无进行中对话 → 暂停回去，杜绝「看一眼文件空跑一小时」；
- 回收器是进程内任务（丢失由 E2B 绝对超时兜底暂停；Daytona 平台有
  自身 auto-stop，天然兜底，不参与回收）。

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

# 浏览租约秒数：最后一次云端文件浏览后，沙箱保持可看的窗口；窗口内空闲
# 暂停豁免，窗口过后回收器可暂停（权衡：太短看文件途中被暂停抖动，太长
# 空跑烧钱；10 分钟 ≈ 一次从容的文件检查时长）
BROWSE_LEASE_SECONDS = 600

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

# 已有浏览回收器在跑的 user（进程内去重）
_reaping_users: set[str] = set()


def _browse_lease_key(user_id: str) -> str:
    return f"sandbox:browse:{user_id}"


async def touch_browse_lease(user_id: str) -> None:
    """续一份浏览租约（每次云端文件浏览请求调用；失败静默——顶多提前暂停）。"""
    try:
        from src.infra.storage.redis import get_redis_client

        await get_redis_client().set(_browse_lease_key(user_id), "1", ex=BROWSE_LEASE_SECONDS)
    except Exception as e:
        logger.debug("[sandbox-browse] lease touch failed for %s: %s", user_id, e)


async def _has_browse_lease_impl(user_id: str) -> bool:
    """浏览租约是否存续（用户最近浏览过云端文件）。

    Redis 不可用时按**存续**处理：暂停是不可逆体验中断（浏览中途断连），
    不确定时宁可多保留一个宽限窗，由回收器下一轮与平台超时兜底。
    """
    try:
        from src.infra.storage.redis import get_redis_client

        return await get_redis_client().get(_browse_lease_key(user_id)) is not None
    except Exception as e:
        logger.debug("[sandbox-browse] lease check failed for %s: %s", user_id, e)
        return True


# 公共名（测试打桩点）：maybe_pause / 回收器都经由模块属性调用
has_browse_lease = _has_browse_lease_impl


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
        if await has_browse_lease(user_id):
            # 用户最近在浏览云端文件：租约窗内不打断，回收器负责窗口过后
            # 的暂停（schedule_browse_reaper）
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


def schedule_browse_reaper(user_id: str) -> None:
    """云端文件浏览的回收器：宽限窗过后仍无浏览、无进行中对话则暂停沙箱。

    浏览唤醒（paused → running）没有 run 终态事件可挂 idle pause，挂了也
    会被浏览租约豁免——由本回收器在租约过期后补上暂停。循环重排：租约
    仍存续（用户持续浏览）时再等一轮。进程内任务，进程重启即丢——由
    E2B 沙箱绝对超时（on_timeout=pause）兜底，Daytona 有自身 auto-stop。
    """
    if not user_id or user_id in _reaping_users:
        return
    try:
        from src.kernel.config import settings

        if settings.SANDBOX_PLATFORM.lower() not in _IDLE_PAUSE_PLATFORMS:
            return
    except Exception:
        return

    async def _reap() -> None:
        try:
            while True:
                await asyncio.sleep(BROWSE_LEASE_SECONDS)
                if await has_browse_lease(user_id):
                    continue  # 用户仍在浏览：下一轮再看（新请求也在续租约）
                await maybe_pause_user_sandbox(user_id)
                return
        finally:
            _reaping_users.discard(user_id)

    try:
        task = asyncio.create_task(_reap())
    except RuntimeError:
        return
    _reaping_users.add(user_id)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
