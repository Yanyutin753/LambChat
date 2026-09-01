"""Periodic orphan task takeover for multi-replica deployments.

启动清理（startup_cleanup）只在实例启动时执行——执行实例崩溃后，存活副本
不会重新扫描孤儿任务（分布式部署测试报告 P1）。本模块把 RUNNING 任务的
接管挂到统一调度器周期执行：租约互斥与心跳判定沿用 startup_cleanup 的既有
保护；PENDING/QUEUED 重放与 FAILED 恢复仍仅在启动时运行，避免周期扫描
误重放排队中的任务。
"""

from __future__ import annotations

from typing import Any

from src.infra.logging import get_logger
from src.infra.scheduler.runtime import ScheduledJob, get_runtime_scheduler
from src.infra.task.lifecycle import is_shutting_down
from src.infra.task.manager import get_task_manager
from src.kernel.config import settings

logger = get_logger(__name__)

DEFAULT_ORPHAN_RECOVERY_INTERVAL_SECONDS = 15


def recovery_interval_seconds() -> int:
    value = getattr(
        settings, "TASK_ORPHAN_RECOVERY_INTERVAL_SECONDS", DEFAULT_ORPHAN_RECOVERY_INTERVAL_SECONDS
    )
    return int(value or 0)


async def run_scheduled_orphan_recovery() -> dict[str, Any]:
    if is_shutting_down():
        # 关闭中的实例不再接管任务，交还给存活副本（关闭静默的调度器层闸门）。
        return {"status": "skipped", "reason": "shutting_down"}
    task_manager = get_task_manager()
    await task_manager.cleanup_stale_tasks(running_only=True)
    return {"status": "ok"}


def register_orphan_recovery_job() -> None:
    interval = recovery_interval_seconds()
    if interval <= 0:
        logger.info("[OrphanRecovery] Periodic takeover disabled by settings")
        return

    get_runtime_scheduler().register_job(
        ScheduledJob.from_interval(
            id="task.orphan_recovery",
            name="Orphan task takeover",
            interval_seconds=interval,
            enabled=True,
            handler=run_scheduled_orphan_recovery,
        )
    )
    logger.info("[OrphanRecovery] Periodic takeover registered: interval=%ss", interval)
