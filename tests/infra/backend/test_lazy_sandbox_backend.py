from __future__ import annotations

from typing import Any

import pytest
from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    WriteResult,
)
from deepagents.backends.sandbox import BaseSandbox

from src.infra.backend.lazy_sandbox import LazySandboxBackend


class _Presenter:
    async def emit_sandbox_starting(self) -> dict[str, Any]:
        return {}

    async def emit_sandbox_ready(self, sandbox_id: str, work_dir: str) -> dict[str, Any]:
        del sandbox_id, work_dir
        return {}

    async def emit_sandbox_error(self, error: str) -> dict[str, Any]:
        del error
        return {}


class _RecordingSandbox(BaseSandbox):
    def __init__(
        self,
        *,
        work_dir: str,
        write_result_path: str | None = None,
    ) -> None:
        self._work_dir = work_dir
        self._write_result_path = write_result_path
        self.write_calls: list[tuple[str, str]] = []

    @property
    def id(self) -> str:
        return "provider-sandbox-1"

    @property
    def work_dir(self) -> str:
        return self._work_dir

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        del command, timeout
        return ExecuteResponse(output="", exit_code=0)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path) for path, _content in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [FileDownloadResponse(path=path, content=b"") for path in paths]

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        self.write_calls.append((file_path, content))
        return WriteResult(path=self._write_result_path or file_path)


class _Manager:
    def __init__(self, provider: _RecordingSandbox) -> None:
        self._provider = provider
        self.calls: list[tuple[str, str]] = []

    async def get_or_create(self, *, session_id: str, user_id: str) -> tuple[CompositeBackend, str]:
        self.calls.append((session_id, user_id))
        return (
            CompositeBackend(default=self._provider, routes={}),
            self._provider.work_dir,
        )


def _lazy(
    manager: _Manager,
    *,
    session_id: str = "session-1",
) -> LazySandboxBackend:
    def manager_factory() -> _Manager:
        return manager

    return LazySandboxBackend(
        session_id=session_id,
        user_id="user-1",
        presenter=_Presenter(),
        manager_factory=manager_factory,
    )


def test_construction_does_not_obtain_manager_and_exposes_public_workspace() -> None:
    calls = 0

    def manager_factory() -> _Manager:
        nonlocal calls
        calls += 1
        raise AssertionError("manager must stay lazy")

    backend = LazySandboxBackend(
        session_id="session / one",
        user_id="user-1",
        presenter=_Presenter(),
        manager_factory=manager_factory,
    )

    assert calls == 0
    assert backend.work_dir == "/workspace/session-one"
    assert backend.id == "pending"
    assert isinstance(backend, BaseSandbox)


@pytest.mark.asyncio
async def test_first_file_operation_maps_public_workspace_and_result() -> None:
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider)
    backend = _lazy(manager)

    result = await backend.awrite("/workspace/session-1/report.txt", "ok")

    assert manager.calls == [("session-1", "user-1")]
    assert provider.write_calls == [("/remote/home/sessions/session-1/report.txt", "ok")]
    assert result.path == "/workspace/session-1/report.txt"
    assert backend.id == "provider-sandbox-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested_path", "provider_path", "public_result_path"),
    [
        (
            "/workspace/session-1",
            "/remote/home/sessions/session-1",
            "/workspace/session-1",
        ),
        (
            "/workspace/session-1/reports/summary.txt",
            "/remote/home/sessions/session-1/reports/summary.txt",
            "/workspace/session-1/reports/summary.txt",
        ),
        (
            "reports/summary.txt",
            "/remote/home/sessions/session-1/reports/summary.txt",
            "/workspace/session-1/reports/summary.txt",
        ),
        (
            "/workspace/session-10/report.txt",
            "/workspace/session-10/report.txt",
            "/workspace/session-10/report.txt",
        ),
        (
            "/tmp/external-report.txt",
            "/tmp/external-report.txt",
            "/tmp/external-report.txt",
        ),
    ],
)
async def test_write_maps_workspace_paths_with_segment_boundaries(
    requested_path: str,
    provider_path: str,
    public_result_path: str,
) -> None:
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    backend = _lazy(_Manager(provider))

    result = await backend.awrite(requested_path, "ok")

    assert provider.write_calls == [(provider_path, "ok")]
    assert result.path == public_result_path


@pytest.mark.asyncio
async def test_provider_result_mapping_is_segment_aware() -> None:
    provider = _RecordingSandbox(
        work_dir="/remote/home/sessions/session-1",
        write_result_path="/remote/home/sessions/session-10/report.txt",
    )
    backend = _lazy(_Manager(provider))

    result = await backend.awrite("/tmp/request.txt", "ok")

    assert result.path == "/remote/home/sessions/session-10/report.txt"
