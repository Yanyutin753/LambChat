from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import Protocol

from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    WriteResult,
)
from deepagents.backends.sandbox import BaseSandbox

from src.infra.logging import get_logger
from src.kernel.config import settings

PUBLIC_SANDBOX_ROOT = "/workspace"
logger = get_logger(__name__)


def public_sandbox_work_dir(session_id: str) -> str:
    """Return the stable provider-neutral workspace for a session."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_id).strip(".-")
    return f"{PUBLIC_SANDBOX_ROOT}/{safe[:80] or 'session'}"


class SandboxInitializationError(RuntimeError):
    """Provider-neutral error exposed when lazy initialization fails."""

    PUBLIC_MESSAGE = "Sandbox initialization failed; please retry later"

    def __init__(self) -> None:
        super().__init__(self.PUBLIC_MESSAGE)


class _SandboxManager(Protocol):
    async def get_or_create(
        self,
        *,
        session_id: str,
        user_id: str,
    ) -> tuple[CompositeBackend, str]: ...


class _SandboxPresenter(Protocol):
    async def emit_sandbox_starting(self) -> object: ...

    async def emit_sandbox_ready(self, sandbox_id: str, work_dir: str) -> object: ...

    async def emit_sandbox_error(self, error: str) -> object: ...


class LazySandboxBackend(BaseSandbox):
    """Run-scoped sandbox that obtains its provider on first async use."""

    def __init__(
        self,
        *,
        session_id: str,
        user_id: str,
        presenter: _SandboxPresenter,
        manager_factory: Callable[[], _SandboxManager],
    ) -> None:
        construction_started_at = time.perf_counter()
        self._session_id = session_id
        self._user_id = user_id
        self._presenter: _SandboxPresenter = presenter
        self._manager_factory = manager_factory
        self._platform = settings.SANDBOX_PLATFORM.lower()
        self._public_work_dir = public_sandbox_work_dir(session_id)
        self._actual_work_dir: str | None = None
        self._delegate: BaseSandbox | None = None
        self._initialization_task: asyncio.Task[BaseSandbox] | None = None
        self._lock = asyncio.Lock()
        self._event_lock = asyncio.Lock()
        self._waiters = 0
        self._closed = False
        self._suppress_events = False
        self._log_timing(
            "constructed",
            time.perf_counter() - construction_started_at,
        )

    @property
    def work_dir(self) -> str:
        return self._public_work_dir

    @property
    def id(self) -> str:
        return self._delegate.id if self._delegate is not None else "pending"

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        del command, timeout
        raise RuntimeError("Lazy sandbox is not initialized; use async operations first")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        del files
        raise RuntimeError("Lazy sandbox is not initialized; use async operations first")

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        del paths
        raise RuntimeError("Lazy sandbox is not initialized; use async operations first")

    def _to_provider_path(self, path: str) -> str:
        actual_work_dir = self._require_actual_work_dir()
        public_prefix = f"{self._public_work_dir}/"

        if path == self._public_work_dir:
            return actual_work_dir
        if path.startswith(public_prefix):
            return f"{actual_work_dir.rstrip('/')}/{path[len(public_prefix) :]}"
        if not path.startswith("/"):
            return f"{actual_work_dir.rstrip('/')}/{path}"
        return path

    def _to_public_path(self, path: str) -> str:
        actual_work_dir = self._require_actual_work_dir()
        actual_prefix = f"{actual_work_dir.rstrip('/')}/"

        if path == actual_work_dir:
            return self._public_work_dir
        if path.startswith(actual_prefix):
            return f"{self._public_work_dir}/{path[len(actual_prefix) :]}"
        return path

    def _require_actual_work_dir(self) -> str:
        if self._actual_work_dir is None:
            raise RuntimeError("Lazy sandbox is not initialized; use async operations first")
        return self._actual_work_dir

    def _log_timing(
        self,
        phase: str,
        duration_seconds: float,
        *,
        exception_category: str | None = None,
    ) -> None:
        details: dict[str, object] = {
            "lazy_sandbox_phase": phase,
            "sandbox_platform": self._platform,
            "duration_seconds": duration_seconds,
        }
        if exception_category is not None:
            details["exception_category"] = exception_category
        logger.info("lazy_sandbox_timing", extra=details)

    async def _attempt_event(
        self,
        event_name: str,
        emit: Callable[[], Awaitable[object]],
    ) -> None:
        async with self._event_lock:
            if self._suppress_events:
                return
            try:
                await emit()
            except Exception as exc:
                logger.warning(
                    "lazy_sandbox_event_emit_failed",
                    extra={
                        "event_name": event_name,
                        "sandbox_platform": self._platform,
                        "exception_category": type(exc).__name__,
                    },
                )

    async def _initialize(self, first_operation_at: float) -> BaseSandbox:
        initialization_started_at = time.perf_counter()
        self._log_timing(
            "initialization_started",
            initialization_started_at - first_operation_at,
        )
        await self._attempt_event(
            "starting",
            self._presenter.emit_sandbox_starting,
        )

        try:
            manager_started_at = time.perf_counter()
            try:
                manager = self._manager_factory()
                scoped_backend, actual_work_dir = await manager.get_or_create(
                    session_id=self._session_id,
                    user_id=self._user_id,
                )
            finally:
                self._log_timing(
                    "manager_completed",
                    time.perf_counter() - manager_started_at,
                )

            if not isinstance(scoped_backend, CompositeBackend):
                raise TypeError("sandbox manager returned an invalid backend")
            delegate = scoped_backend.default
            if not isinstance(delegate, BaseSandbox):
                raise TypeError("sandbox manager returned an invalid default backend")
            if not (
                isinstance(actual_work_dir, str)
                and actual_work_dir
                and PurePosixPath(actual_work_dir).is_absolute()
            ):
                raise ValueError("sandbox manager returned an invalid work directory")

            self._delegate = delegate
            self._actual_work_dir = actual_work_dir
            await self._attempt_event(
                "ready",
                lambda: self._presenter.emit_sandbox_ready(delegate.id, actual_work_dir),
            )
            self._log_timing(
                "ready",
                time.perf_counter() - initialization_started_at,
            )
            return delegate
        except Exception as exc:
            await self._attempt_event(
                "error",
                lambda: self._presenter.emit_sandbox_error(
                    SandboxInitializationError.PUBLIC_MESSAGE
                ),
            )
            self._log_timing(
                "failure",
                time.perf_counter() - initialization_started_at,
                exception_category=type(exc).__name__,
            )
            raise SandboxInitializationError() from exc

    @staticmethod
    def _consume_initialization_exception(task: asyncio.Task[BaseSandbox]) -> None:
        if not task.cancelled():
            task.exception()

    async def _get_initialization_task(self) -> asyncio.Task[BaseSandbox]:
        async with self._lock:
            if self._initialization_task is None:
                first_operation_at = time.perf_counter()
                task = asyncio.create_task(self._initialize(first_operation_at))
                task.add_done_callback(self._consume_initialization_exception)
                self._initialization_task = task
            return self._initialization_task

    async def _ensure_ready(self) -> BaseSandbox:
        initialization_task = self._initialization_task
        if initialization_task is not None and not initialization_task.done():
            return await asyncio.shield(initialization_task)
        if self._delegate is not None:
            return self._delegate
        task = await self._get_initialization_task()
        return await asyncio.shield(task)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        delegate = await self._ensure_ready()
        result = await delegate.awrite(self._to_provider_path(file_path), content)
        public_path = self._to_public_path(result.path) if result.path is not None else None
        return WriteResult(error=result.error, path=public_path)
