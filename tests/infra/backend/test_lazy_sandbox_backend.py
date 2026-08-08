from __future__ import annotations

import asyncio
import logging
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

from src.infra.backend.lazy_sandbox import (
    LazySandboxBackend,
    SandboxInitializationError,
)


class _Presenter:
    def __init__(self, *, failures: set[str] | None = None) -> None:
        self.attempts: list[tuple[str, ...]] = []
        self._failures = failures or set()

    async def emit_sandbox_starting(self) -> dict[str, Any]:
        self.attempts.append(("starting",))
        if "starting" in self._failures:
            raise RuntimeError("starting emitter failed with event-secret")
        return {}

    async def emit_sandbox_ready(self, sandbox_id: str, work_dir: str) -> dict[str, Any]:
        self.attempts.append(("ready", sandbox_id, work_dir))
        if "ready" in self._failures:
            raise RuntimeError("ready emitter failed with event-secret")
        return {}

    async def emit_sandbox_error(self, error: str) -> dict[str, Any]:
        self.attempts.append(("error", error))
        if "error" in self._failures:
            raise RuntimeError("error emitter failed with event-secret")
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
    def __init__(
        self,
        provider: _RecordingSandbox,
        *,
        entered: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
        failure: Exception | None = None,
    ) -> None:
        self._provider = provider
        self._entered = entered
        self._release = release
        self._failure = failure
        self.calls: list[tuple[str, str]] = []

    async def get_or_create(self, *, session_id: str, user_id: str) -> tuple[CompositeBackend, str]:
        self.calls.append((session_id, user_id))
        if self._entered is not None:
            self._entered.set()
        if self._release is not None:
            await self._release.wait()
        if self._failure is not None:
            raise self._failure
        return (
            CompositeBackend(default=self._provider, routes={}),
            self._provider.work_dir,
        )


def _lazy(
    manager: _Manager,
    *,
    session_id: str = "session-1",
    presenter: _Presenter | None = None,
) -> LazySandboxBackend:
    def manager_factory() -> _Manager:
        return manager

    return LazySandboxBackend(
        session_id=session_id,
        user_id="user-1",
        presenter=presenter or _Presenter(),
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


@pytest.mark.asyncio
async def test_single_flight_concurrent_first_operations_initialize_once() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider, entered=entered, release=release)
    presenter = _Presenter()
    factory_calls = 0

    def manager_factory() -> _Manager:
        nonlocal factory_calls
        factory_calls += 1
        return manager

    backend = LazySandboxBackend(
        session_id="session-1",
        user_id="user-1",
        presenter=presenter,
        manager_factory=manager_factory,
    )

    first = asyncio.create_task(backend.awrite("a.txt", "first"))
    second = asyncio.create_task(backend.awrite("b.txt", "second"))
    await entered.wait()
    await asyncio.sleep(0)
    release.set()

    first_result, second_result = await asyncio.gather(first, second)

    assert factory_calls == 1
    assert manager.calls == [("session-1", "user-1")]
    assert set(provider.write_calls) == {
        ("/remote/home/sessions/session-1/a.txt", "first"),
        ("/remote/home/sessions/session-1/b.txt", "second"),
    }
    assert first_result.path == "/workspace/session-1/a.txt"
    assert second_result.path == "/workspace/session-1/b.txt"
    assert presenter.attempts == [
        ("starting",),
        (
            "ready",
            "provider-sandbox-1",
            "/remote/home/sessions/session-1",
        ),
    ]


@pytest.mark.asyncio
async def test_starting_event_failure_does_not_stop_initialization_or_retry() -> None:
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider)
    presenter = _Presenter(failures={"starting"})
    backend = _lazy(manager, presenter=presenter)

    result = await backend.awrite("report.txt", "ok")

    assert result.path == "/workspace/session-1/report.txt"
    assert manager.calls == [("session-1", "user-1")]
    assert presenter.attempts == [
        ("starting",),
        (
            "ready",
            "provider-sandbox-1",
            "/remote/home/sessions/session-1",
        ),
    ]


@pytest.mark.asyncio
async def test_ready_event_failure_does_not_replace_provider_success() -> None:
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider)
    presenter = _Presenter(failures={"ready"})
    backend = _lazy(manager, presenter=presenter)

    result = await backend.awrite("report.txt", "ok")

    assert result.path == "/workspace/session-1/report.txt"
    assert provider.write_calls == [("/remote/home/sessions/session-1/report.txt", "ok")]
    assert presenter.attempts == [
        ("starting",),
        (
            "ready",
            "provider-sandbox-1",
            "/remote/home/sessions/session-1",
        ),
    ]


@pytest.mark.asyncio
async def test_concurrent_operation_waits_for_ready_event_attempt_to_complete() -> None:
    ready_entered = asyncio.Event()
    release_ready = asyncio.Event()

    class _GatedReadyPresenter(_Presenter):
        async def emit_sandbox_ready(self, sandbox_id: str, work_dir: str) -> dict[str, Any]:
            self.attempts.append(("ready", sandbox_id, work_dir))
            ready_entered.set()
            await release_ready.wait()
            return {}

    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider)
    presenter = _GatedReadyPresenter()
    backend = _lazy(manager, presenter=presenter)

    first = asyncio.create_task(backend.awrite("first.txt", "first"))
    await ready_entered.wait()
    second = asyncio.create_task(backend.awrite("second.txt", "second"))
    await asyncio.sleep(0)

    try:
        assert provider.write_calls == []
        assert not first.done()
        assert not second.done()
    finally:
        release_ready.set()
        await asyncio.gather(first, second)


@pytest.mark.asyncio
async def test_provider_failure_attempts_public_error_after_starting_event_failure() -> None:
    provider_error = RuntimeError("provider failed with private details")
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider, failure=provider_error)
    presenter = _Presenter(failures={"starting"})
    backend = _lazy(manager, presenter=presenter)

    with pytest.raises(SandboxInitializationError) as exc_info:
        await backend.awrite("report.txt", "never-written")

    assert str(exc_info.value) == SandboxInitializationError.PUBLIC_MESSAGE
    assert exc_info.value.__cause__ is provider_error
    assert provider.write_calls == []
    assert presenter.attempts == [
        ("starting",),
        ("error", SandboxInitializationError.PUBLIC_MESSAGE),
    ]


@pytest.mark.asyncio
async def test_initialization_failure_is_shared_and_never_retried() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(
        provider,
        entered=entered,
        release=release,
        failure=RuntimeError("provider unavailable"),
    )
    presenter = _Presenter()
    factory_calls = 0

    def manager_factory() -> _Manager:
        nonlocal factory_calls
        factory_calls += 1
        return manager

    backend = LazySandboxBackend(
        session_id="session-1",
        user_id="user-1",
        presenter=presenter,
        manager_factory=manager_factory,
    )

    first = asyncio.create_task(backend.awrite("a.txt", "first"))
    second = asyncio.create_task(backend.awrite("b.txt", "second"))
    await entered.wait()
    await asyncio.sleep(0)
    release.set()
    failures = await asyncio.gather(first, second, return_exceptions=True)

    assert len(failures) == 2
    assert all(isinstance(error, SandboxInitializationError) for error in failures)
    assert [str(error) for error in failures] == [
        SandboxInitializationError.PUBLIC_MESSAGE,
        SandboxInitializationError.PUBLIC_MESSAGE,
    ]
    assert failures[0] is failures[1]

    with pytest.raises(SandboxInitializationError) as retry_info:
        await backend.awrite("c.txt", "third")

    assert retry_info.value is failures[0]
    assert factory_calls == 1
    assert manager.calls == [("session-1", "user-1")]
    assert presenter.attempts == [
        ("starting",),
        ("error", SandboxInitializationError.PUBLIC_MESSAGE),
    ]


@pytest.mark.asyncio
async def test_failure_does_not_leak_provider_details_to_events_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_details = [
        "sk-provider-token",
        "user-sensitive-42",
        "sandbox-private-17",
        "/home/provider/private/session",
    ]
    provider_error = RuntimeError(" ".join(private_details))
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider, failure=provider_error)
    presenter = _Presenter()
    backend = _lazy(manager, presenter=presenter)

    with caplog.at_level(logging.INFO, logger="src.infra.backend.lazy_sandbox"):
        with pytest.raises(SandboxInitializationError):
            await backend.awrite("report.txt", "never-written")

    event_payloads = repr(presenter.attempts)
    captured_logs = "\n".join(record.getMessage() for record in caplog.records)
    for private_detail in private_details:
        assert private_detail not in event_payloads
        assert private_detail not in captured_logs
    assert presenter.attempts == [
        ("starting",),
        ("error", SandboxInitializationError.PUBLIC_MESSAGE),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scoped_backend", "actual_work_dir"),
    [
        (object(), "/remote/home/sessions/session-1"),
        (CompositeBackend(default=object(), routes={}), "/remote/session-1"),  # type: ignore[arg-type]
        (
            CompositeBackend(default=_RecordingSandbox(work_dir="/remote/session-1"), routes={}),
            "",
        ),
        (
            CompositeBackend(default=_RecordingSandbox(work_dir="/remote/session-1"), routes={}),
            "relative/session-1",
        ),
    ],
)
async def test_initialization_failure_rejects_invalid_manager_results(
    scoped_backend: object,
    actual_work_dir: str,
) -> None:
    class _InvalidManager:
        async def get_or_create(self, *, session_id: str, user_id: str) -> tuple[Any, str]:
            del session_id, user_id
            return scoped_backend, actual_work_dir

    presenter = _Presenter()
    backend = LazySandboxBackend(
        session_id="session-1",
        user_id="user-1",
        presenter=presenter,
        manager_factory=_InvalidManager,
    )

    with pytest.raises(SandboxInitializationError) as exc_info:
        await backend.awrite("report.txt", "never-written")

    assert str(exc_info.value) == SandboxInitializationError.PUBLIC_MESSAGE
    assert presenter.attempts == [
        ("starting",),
        ("error", SandboxInitializationError.PUBLIC_MESSAGE),
    ]


@pytest.mark.asyncio
async def test_event_logs_record_safe_initialization_timings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider)
    presenter = _Presenter()

    with caplog.at_level(logging.INFO, logger="src.infra.backend.lazy_sandbox"):
        backend = _lazy(manager, presenter=presenter)
        await backend.awrite("report.txt", "ok")

    timing_records = [
        record
        for record in caplog.records
        if getattr(record, "lazy_sandbox_phase", None) is not None
    ]
    assert [getattr(record, "lazy_sandbox_phase") for record in timing_records] == [
        "constructed",
        "initialization_started",
        "manager_completed",
        "ready",
    ]
    assert all(getattr(record, "sandbox_platform") for record in timing_records)
    assert all(getattr(record, "duration_seconds") >= 0 for record in timing_records)
