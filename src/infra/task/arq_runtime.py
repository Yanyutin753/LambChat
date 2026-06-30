from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from typing import Any, Callable

from arq.worker import Worker

from src.infra.logging import get_logger
from src.kernel.config import settings

from .arq_payloads import TaskArqPayloadStore
from .arq_settings import build_arq_redis_settings
from .arq_worker import run_agent_task, run_workflow_task

logger = get_logger(__name__)


class EmbeddedArqRuntime:
    """Own the lifecycle of an arq worker embedded in the FastAPI process."""

    def __init__(
        self,
        worker_factory: Callable[..., Any] = Worker,
        worker_context: Mapping[str, Any] | None = None,
    ) -> None:
        self._worker_factory = worker_factory
        self._worker_context = dict(worker_context or {})
        self._worker: Any | None = None
        self._task: asyncio.Future | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _build_worker_context(
        self,
        worker_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx: dict[str, Any] = {"payload_store": TaskArqPayloadStore()}
        ctx.update({key: value for key, value in self._worker_context.items() if value is not None})
        if worker_context:
            ctx.update({key: value for key, value in worker_context.items() if value is not None})
        return ctx

    async def start(self, worker_context: Mapping[str, Any] | None = None) -> None:
        if self.is_running:
            return
        if getattr(settings, "TASK_BACKEND", "local") != "arq":
            return
        if not getattr(settings, "ARQ_EMBEDDED_WORKER", True):
            return

        self._worker = self._worker_factory(
            [run_agent_task, run_workflow_task],
            queue_name=settings.ARQ_QUEUE_NAME,
            redis_settings=build_arq_redis_settings(settings),
            handle_signals=False,
            max_jobs=settings.ARQ_WORKER_MAX_JOBS,
            job_timeout=settings.ARQ_JOB_TIMEOUT_SECONDS,
            ctx=self._build_worker_context(worker_context),
            allow_abort_jobs=True,
        )
        self._task = asyncio.ensure_future(self._worker.async_run())
        logger.info("Embedded arq worker started")

    async def stop(self) -> None:
        if self._worker is not None:
            close = getattr(self._worker, "close", None)
            if close is not None:
                result = close()
                if inspect.isawaitable(result):
                    await result

        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._worker = None
        self._task = None


_runtime: EmbeddedArqRuntime | None = None


def get_arq_runtime() -> EmbeddedArqRuntime:
    global _runtime
    if _runtime is None:
        _runtime = EmbeddedArqRuntime()
    return _runtime


async def start_arq_runtime(
    *,
    plugin_runtime: object | None = None,
    plugin_runtime_state_storage: object | None = None,
) -> None:
    worker_context = {
        "plugin_runtime": plugin_runtime,
        "plugin_runtime_state_storage": plugin_runtime_state_storage,
    }
    await get_arq_runtime().start(worker_context=worker_context)


async def stop_arq_runtime() -> None:
    global _runtime
    runtime = _runtime
    _runtime = None
    if runtime is not None:
        await runtime.stop()
