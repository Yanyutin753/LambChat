"""周期性僵尸 trace 兜底终结（全局，不限 session）。

启动清理只扫 ``sessions.metadata.task_status``（arq 任务路径才写），
直连 SSE run（``/api/{agent_id}/stream``）与挂死 run 的 trace 停在
running 时结构性无人回收（2026-09-05 生产实例：run_20260905032659 挂
running 8 小时，滚动重启也清不掉）。本模块把
``expire_stale_running_traces_globally`` 挂到统一调度器周期执行；判定
沿用 updated_at 心跳 + 10 分钟 TTL 的既有约定，多副本并发下按 status
条件更新天然幂等，无需租约。
"""

from __future__ import annotations

from typing import Any

from src.infra.logging import get_logger
from src.infra.scheduler.runtime import ScheduledJob, get_runtime_scheduler
from src.infra.session.trace_storage import get_trace_storage
from src.infra.task.lifecycle import is_shutting_down
from src.kernel.config import settings

logger = get_logger(__name__)

DEFAULT_STALE_TRACE_RECOVERY_INTERVAL_SECONDS = 300


def recovery_interval_seconds() -> int:
    value = getattr(
        settings,
        "STALE_TRACE_RECOVERY_INTERVAL_SECONDS",
        DEFAULT_STALE_TRACE_RECOVERY_INTERVAL_SECONDS,
    )
    return int(value or 0)


async def run_scheduled_stale_trace_recovery() -> dict[str, Any]:
    if is_shutting_down():
        # 关闭中的实例不再改写 trace 终态，避免与关停中的写入者竞争
        return {"status": "skipped", "reason": "shutting_down"}
    try:
        expired = await get_trace_storage().expire_stale_running_traces_globally()
    except Exception:
        logger.exception("[StaleTraceRecovery] sweep failed")
        return {"status": "error"}
    return {"status": "ok", "expired": expired}


def register_stale_trace_recovery_job() -> None:
    interval = recovery_interval_seconds()
    if interval <= 0:
        logger.info("[StaleTraceRecovery] Periodic sweep disabled by settings")
        return

    get_runtime_scheduler().register_job(
        ScheduledJob.from_interval(
            id="trace.stale_run_recovery",
            name="Stale running trace recovery",
            interval_seconds=interval,
            enabled=True,
            handler=run_scheduled_stale_trace_recovery,
        )
    )
    logger.info("[StaleTraceRecovery] Periodic sweep registered: interval=%ss", interval)
