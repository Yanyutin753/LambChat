from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

from arq.worker import Worker

from src.infra.logging import get_logger
from src.kernel.config import settings

from .arq_payloads import TaskArqPayloadStore, UserMessageSearchIndexPayloadStore
from .arq_settings import build_arq_redis_settings
from .arq_worker import run_agent_task, update_user_message_search_index

logger = get_logger(__name__)


class EmbeddedArqRuntime:
    """Own the lifecycle of an arq worker embedded in the FastAPI process.

    Worker 以监督任务运行：异常退出或静默返回都会记录日志并自动重建，
    避免副本 API 正常但永远不再消费队列（2026-08-27 生产事故根因）。
    """

    def __init__(
        self,
        worker_factory: Callable[..., Any] = Worker,
        restart_delay_seconds: float = 5.0,
        on_worker_restarted: Callable[[], Any] | None = None,
    ) -> None:
        self._worker_factory = worker_factory
        self._restart_delay = restart_delay_seconds
        self._on_worker_restarted = on_worker_restarted
        self._worker: Any | None = None
        self._supervisor: asyncio.Future | None = None
        self._stopping = False
        self._recovery_tasks: set[asyncio.Task[None]] = set()

    @property
    def is_running(self) -> bool:
        return self._supervisor is not None and not self._supervisor.done()

    async def start(self) -> None:
        if self.is_running:
            return
        if getattr(settings, "TASK_BACKEND", "local") != "arq":
            return
        if not getattr(settings, "ARQ_EMBEDDED_WORKER", True):
            return

        self._stopping = False
        self._worker = self._create_worker()
        self._supervisor = asyncio.ensure_future(self._supervise())
        logger.info("Embedded arq worker started")

    def _create_worker(self) -> Any:
        return self._worker_factory(
            [run_agent_task, update_user_message_search_index],
            queue_name=settings.ARQ_QUEUE_NAME,
            redis_settings=build_arq_redis_settings(settings),
            handle_signals=False,
            max_jobs=settings.ARQ_WORKER_MAX_JOBS,
            job_timeout=settings.ARQ_JOB_TIMEOUT_SECONDS,
            ctx={
                "payload_store": TaskArqPayloadStore(),
                "search_index_payload_store": UserMessageSearchIndexPayloadStore(),
            },
            allow_abort_jobs=True,
        )

    async def _close_worker_quietly(self, worker: Any) -> None:
        close = getattr(worker, "close", None)
        if close is None:
            return
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.warning("Failed to close dead arq worker", exc_info=True)

    async def _supervise(self) -> None:
        while not self._stopping:
            worker = self._worker
            if worker is None:  # start() 已保证首个 worker 存在，此处仅类型收窄
                return
            try:
                result = worker.async_run()
                if inspect.isawaitable(result):
                    await result
                if self._stopping:
                    return
                logger.warning(
                    "Embedded arq worker exited silently; restarting in %.1fs",
                    self._restart_delay,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._stopping:
                    return
                logger.exception(
                    "Embedded arq worker crashed; restarting in %.1fs",
                    self._restart_delay,
                )
            await self._close_worker_quietly(worker)
            if self._stopping:
                return
            await asyncio.sleep(self._restart_delay)
            if self._stopping:
                return
            self._worker = self._create_worker()
            # worker 崩溃时在途 run 会被标为 FAILED+recoverable（payload 已删），
            # 周期孤儿接管是 running_only 会跳过它们——重启后主动补一次恢复，
            # 否则这些会话要等任意 Pod 重启才能恢复。
            callback = self._on_worker_restarted
            if callback is not None:
                recovery_task = asyncio.create_task(callback())
                self._recovery_tasks.add(recovery_task)
                recovery_task.add_done_callback(self._recovery_tasks.discard)

    async def stop(self) -> None:
        self._stopping = True
        if self._worker is not None:
            await self._close_worker_quietly(self._worker)

        if self._supervisor is not None and not self._supervisor.done():
            self._supervisor.cancel()
            try:
                await self._supervisor
            except asyncio.CancelledError:
                pass

        if self._recovery_tasks:
            await asyncio.gather(*self._recovery_tasks, return_exceptions=True)

        self._worker = None
        self._supervisor = None


_runtime: EmbeddedArqRuntime | None = None


async def _recover_stale_tasks_after_worker_restart() -> None:
    """Worker 崩溃重启后补一次全量恢复（与启动清理等价，有租约互斥保护）。"""
    try:
        from .manager import get_task_manager

        await get_task_manager().cleanup_stale_tasks(running_only=False)
    except Exception:
        logger.exception("Post-restart stale task recovery failed")


def get_arq_runtime() -> EmbeddedArqRuntime:
    global _runtime
    if _runtime is None:
        _runtime = EmbeddedArqRuntime(on_worker_restarted=_recover_stale_tasks_after_worker_restart)
    return _runtime


async def start_arq_runtime() -> None:
    await get_arq_runtime().start()


async def stop_arq_runtime() -> None:
    global _runtime
    runtime = _runtime
    _runtime = None
    if runtime is not None:
        await runtime.stop()
