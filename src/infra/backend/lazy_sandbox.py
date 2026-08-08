from __future__ import annotations

import asyncio
import re
import shlex
import time
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import Protocol, cast

from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    ExecuteOffloadResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
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
        self.enable_capture_offload = False
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

    def _require_ready_delegate(self) -> BaseSandbox:
        if self._closed:
            raise RuntimeError("Lazy sandbox is closed")
        if self._delegate is None:
            raise RuntimeError("Lazy sandbox is not initialized; use async operations first")
        return self._delegate

    def _with_workspace_env(self, command: str) -> str:
        actual_work_dir = shlex.quote(self._require_actual_work_dir())
        return f"export LAMBCHAT_WORKSPACE={actual_work_dir}; {command}"

    def _to_public_file_info(self, info: FileInfo) -> FileInfo:
        return cast(FileInfo, {**info, "path": self._to_public_path(info["path"])})

    def _to_public_grep_match(self, match: GrepMatch) -> GrepMatch:
        return cast(
            GrepMatch,
            {**match, "path": self._to_public_path(match["path"])},
        )

    def ls(self, path: str) -> LsResult:
        delegate = self._require_ready_delegate()
        result = delegate.ls(self._to_provider_path(path))
        return LsResult(
            error=result.error,
            entries=(
                [self._to_public_file_info(info) for info in result.entries]
                if result.entries is not None
                else None
            ),
        )

    async def als(self, path: str) -> LsResult:
        delegate = await self._ensure_ready()
        result = await delegate.als(self._to_provider_path(path))
        return LsResult(
            error=result.error,
            entries=(
                [self._to_public_file_info(info) for info in result.entries]
                if result.entries is not None
                else None
            ),
        )

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        delegate = self._require_ready_delegate()
        result = delegate.read(self._to_provider_path(file_path), offset, limit)
        return ReadResult(
            error=result.error,
            file_data=result.file_data,
            total_lines=result.total_lines,
            start_line=result.start_line,
            end_line=result.end_line,
            next_offset=result.next_offset,
            no_lines_requested=result.no_lines_requested,
        )

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        delegate = await self._ensure_ready()
        result = await delegate.aread(self._to_provider_path(file_path), offset, limit)
        return ReadResult(
            error=result.error,
            file_data=result.file_data,
            total_lines=result.total_lines,
            start_line=result.start_line,
            end_line=result.end_line,
            next_offset=result.next_offset,
            no_lines_requested=result.no_lines_requested,
        )

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        delegate = self._require_ready_delegate()
        provider_path = self._to_provider_path(path) if path is not None else None
        result = delegate.grep(
            pattern,
            provider_path,
            glob,
            max_count=max_count,
        )
        return GrepResult(
            error=result.error,
            matches=(
                [self._to_public_grep_match(match) for match in result.matches]
                if result.matches is not None
                else None
            ),
            truncated=result.truncated,
        )

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        delegate = await self._ensure_ready()
        provider_path = self._to_provider_path(path) if path is not None else None
        result = await delegate.agrep(
            pattern,
            provider_path,
            glob,
            max_count=max_count,
        )
        return GrepResult(
            error=result.error,
            matches=(
                [self._to_public_grep_match(match) for match in result.matches]
                if result.matches is not None
                else None
            ),
            truncated=result.truncated,
        )

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        delegate = self._require_ready_delegate()
        provider_path = self._to_provider_path(path) if path is not None else None
        result = delegate.glob(pattern, provider_path)
        return GlobResult(
            error=result.error,
            matches=(
                [self._to_public_file_info(info) for info in result.matches]
                if result.matches is not None
                else None
            ),
            truncated=result.truncated,
        )

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        delegate = await self._ensure_ready()
        provider_path = self._to_provider_path(path) if path is not None else None
        result = await delegate.aglob(pattern, provider_path)
        return GlobResult(
            error=result.error,
            matches=(
                [self._to_public_file_info(info) for info in result.matches]
                if result.matches is not None
                else None
            ),
            truncated=result.truncated,
        )

    def write(self, file_path: str, content: str) -> WriteResult:
        delegate = self._require_ready_delegate()
        result = delegate.write(self._to_provider_path(file_path), content)
        public_path = self._to_public_path(result.path) if result.path is not None else None
        return WriteResult(error=result.error, path=public_path)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        delegate = await self._ensure_ready()
        result = await delegate.awrite(self._to_provider_path(file_path), content)
        public_path = self._to_public_path(result.path) if result.path is not None else None
        return WriteResult(error=result.error, path=public_path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        delegate = self._require_ready_delegate()
        result = delegate.edit(
            self._to_provider_path(file_path),
            old_string,
            new_string,
            replace_all,
        )
        public_path = self._to_public_path(result.path) if result.path is not None else None
        return EditResult(
            error=result.error,
            path=public_path,
            occurrences=result.occurrences,
        )

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        delegate = await self._ensure_ready()
        result = await delegate.aedit(
            self._to_provider_path(file_path),
            old_string,
            new_string,
            replace_all,
        )
        public_path = self._to_public_path(result.path) if result.path is not None else None
        return EditResult(
            error=result.error,
            path=public_path,
            occurrences=result.occurrences,
        )

    def delete(self, file_path: str) -> DeleteResult:
        delegate = self._require_ready_delegate()
        result = delegate.delete(self._to_provider_path(file_path))
        public_path = self._to_public_path(result.path) if result.path is not None else None
        return DeleteResult(error=result.error, path=public_path)

    async def adelete(self, file_path: str) -> DeleteResult:
        delegate = await self._ensure_ready()
        result = await delegate.adelete(self._to_provider_path(file_path))
        public_path = self._to_public_path(result.path) if result.path is not None else None
        return DeleteResult(error=result.error, path=public_path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        delegate = self._require_ready_delegate()
        results = delegate.upload_files(
            [(self._to_provider_path(path), content) for path, content in files]
        )
        return [
            FileUploadResponse(
                path=self._to_public_path(result.path),
                error=result.error,
            )
            for result in results
        ]

    async def aupload_files(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[FileUploadResponse]:
        delegate = await self._ensure_ready()
        results = await delegate.aupload_files(
            [(self._to_provider_path(path), content) for path, content in files]
        )
        return [
            FileUploadResponse(
                path=self._to_public_path(result.path),
                error=result.error,
            )
            for result in results
        ]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        delegate = self._require_ready_delegate()
        results = delegate.download_files([self._to_provider_path(path) for path in paths])
        return [
            FileDownloadResponse(
                path=self._to_public_path(result.path),
                content=result.content,
                error=result.error,
            )
            for result in results
        ]

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        delegate = await self._ensure_ready()
        results = await delegate.adownload_files([self._to_provider_path(path) for path in paths])
        return [
            FileDownloadResponse(
                path=self._to_public_path(result.path),
                content=result.content,
                error=result.error,
            )
            for result in results
        ]

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        delegate = self._require_ready_delegate()
        return delegate.execute(self._with_workspace_env(command), timeout=timeout)

    async def aexecute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        delegate = await self._ensure_ready()
        return await delegate.aexecute(
            self._with_workspace_env(command),
            timeout=timeout,
        )

    def execute_with_offload(
        self,
        command: str,
        capture_path: str,
        *,
        max_inline_bytes: int,
        max_capture_bytes: int | None = None,
        timeout: int | None = None,
    ) -> ExecuteOffloadResult:
        delegate = self._require_ready_delegate()
        return delegate.execute_with_offload(
            self._with_workspace_env(command),
            self._to_provider_path(capture_path),
            max_inline_bytes=max_inline_bytes,
            max_capture_bytes=max_capture_bytes,
            timeout=timeout,
        )

    async def aexecute_with_offload(
        self,
        command: str,
        capture_path: str,
        *,
        max_inline_bytes: int,
        max_capture_bytes: int | None = None,
        timeout: int | None = None,
    ) -> ExecuteOffloadResult:
        delegate = await self._ensure_ready()
        return await delegate.aexecute_with_offload(
            self._with_workspace_env(command),
            self._to_provider_path(capture_path),
            max_inline_bytes=max_inline_bytes,
            max_capture_bytes=max_capture_bytes,
            timeout=timeout,
        )

    def resolve_path(self, path: str) -> str:
        self._require_ready_delegate()
        return self._to_provider_path(path)

    async def aresolve_path(self, path: str) -> str:
        await self._ensure_ready()
        return self._to_provider_path(path)

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
        if not path.startswith("/"):
            return f"{self._public_work_dir}/{path}"
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

            await self._attempt_event(
                "ready",
                lambda: self._presenter.emit_sandbox_ready(delegate.id, actual_work_dir),
            )
            async with self._lock:
                if not self._closed:
                    self._delegate = delegate
                    self._actual_work_dir = actual_work_dir
                    self.enable_capture_offload = delegate.enable_capture_offload
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

    async def aclose(self) -> None:
        async with self._lock:
            self._closed = True
            self._suppress_events = True

        async with self._event_lock:
            pass

    async def _acquire_initialization_task(self) -> asyncio.Task[BaseSandbox]:
        async with self._lock:
            if self._closed:
                raise RuntimeError("Lazy sandbox is closed")
            if self._initialization_task is None:
                first_operation_at = time.perf_counter()
                task = asyncio.create_task(self._initialize(first_operation_at))
                task.add_done_callback(self._consume_initialization_exception)
                self._initialization_task = task
            self._waiters += 1
            return self._initialization_task

    async def _release_initialization_waiter(self, *, cancelled: bool) -> None:
        abandoned = False
        async with self._lock:
            self._waiters -= 1
            if cancelled and self._waiters == 0:
                self._closed = True
                self._suppress_events = True
                abandoned = True

        if abandoned:
            async with self._event_lock:
                pass

    async def _complete_initialization_waiter(self) -> bool:
        async with self._lock:
            self._waiters -= 1
            return self._closed

    async def _ensure_ready(self) -> BaseSandbox:
        async with self._lock:
            if self._closed:
                raise RuntimeError("Lazy sandbox is closed")
            if self._delegate is not None:
                return self._delegate

        task = await self._acquire_initialization_task()
        try:
            delegate = await asyncio.shield(task)
            closed = await self._complete_initialization_waiter()
        except asyncio.CancelledError:
            await self._release_initialization_waiter(cancelled=True)
            raise
        except BaseException:
            await self._release_initialization_waiter(cancelled=False)
            raise

        if closed:
            raise RuntimeError("Lazy sandbox is closed")
        return delegate
