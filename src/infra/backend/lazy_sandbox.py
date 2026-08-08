from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any, Protocol, cast

from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    WriteResult,
)
from deepagents.backends.sandbox import BaseSandbox

PUBLIC_SANDBOX_ROOT = "/workspace"


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


class LazySandboxBackend(BaseSandbox):
    """Run-scoped sandbox that obtains its provider on first async use."""

    def __init__(
        self,
        *,
        session_id: str,
        user_id: str,
        presenter: Any,
        manager_factory: Callable[[], _SandboxManager],
    ) -> None:
        self._session_id = session_id
        self._user_id = user_id
        self._presenter = presenter
        self._manager_factory = manager_factory
        self._public_work_dir = public_sandbox_work_dir(session_id)
        self._actual_work_dir: str | None = None
        self._delegate: BaseSandbox | None = None
        self._initialization_task: asyncio.Task[BaseSandbox] | None = None
        self._lock = asyncio.Lock()
        self._event_lock = asyncio.Lock()
        self._waiters = 0
        self._closed = False
        self._suppress_events = False

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

    async def _ensure_ready(self) -> BaseSandbox:
        if self._delegate is None:
            manager = self._manager_factory()
            scoped_backend, actual_work_dir = await manager.get_or_create(
                session_id=self._session_id,
                user_id=self._user_id,
            )
            self._delegate = cast(BaseSandbox, scoped_backend.default)
            self._actual_work_dir = actual_work_dir
        return self._delegate

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        delegate = await self._ensure_ready()
        result = await delegate.awrite(self._to_provider_path(file_path), content)
        public_path = self._to_public_path(result.path) if result.path is not None else None
        return WriteResult(error=result.error, path=public_path)
