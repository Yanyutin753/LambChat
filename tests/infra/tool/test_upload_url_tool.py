from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
from deepagents.backends.sandbox import BaseSandbox

from src.infra.backend.lazy_sandbox import LazySandboxBackend
from src.infra.tool import upload_url_tool


class _Runtime:
    def __init__(self, backend: object, base_url: str = "https://app.example.com") -> None:
        self.config = {"configurable": {"backend": backend, "base_url": base_url}}


class _RecordingSandbox(BaseSandbox):
    def __init__(self, *, work_dir: str) -> None:
        self.work_dir = work_dir
        self.commands: list[str] = []

    @property
    def id(self) -> str:
        return "sandbox-1"

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        del timeout
        self.commands.append(command)
        return ExecuteResponse(output="", exit_code=0)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path) for path, _content in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [FileDownloadResponse(path=path, content=b"") for path in paths]


class _Presenter:
    async def emit_sandbox_starting(self) -> None:
        return None

    async def emit_sandbox_ready(self, sandbox_id: str, work_dir: str) -> None:
        return None

    async def emit_sandbox_error(self, error: str) -> None:
        return None


class _Manager:
    def __init__(self, provider: BaseSandbox, *, actual_work_dir: str) -> None:
        self.provider = provider
        self.actual_work_dir = actual_work_dir
        self.calls: list[tuple[str, str]] = []

    async def get_or_create(self, *, session_id: str, user_id: str):
        self.calls.append((session_id, user_id))
        return CompositeBackend(default=self.provider, routes={}), self.actual_work_dir


class _BlockingOnlySpooledFile:
    def __init__(self, *args, **kwargs) -> None:
        self.data = bytearray()
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def write(self, chunk: bytes) -> int:
        if not getattr(upload_url_tool, "_inside_fake_blocking_io", False):
            raise AssertionError("fallback spool writes must run in blocking IO executor")
        self.data.extend(chunk)
        self.position += len(chunk)
        return len(chunk)

    def seek(self, position: int) -> int:
        if not getattr(upload_url_tool, "_inside_fake_blocking_io", False):
            raise AssertionError("fallback spool seek must run in blocking IO executor")
        self.position = position
        return position

    def read(self) -> bytes:
        if not getattr(upload_url_tool, "_inside_fake_blocking_io", False):
            raise AssertionError("fallback spool read must run in blocking IO executor")
        return bytes(self.data)


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_offloads_invalid_path_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(upload_url_tool, "run_blocking_io", fake_run_blocking_io)

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://files.example.com/input.txt",
            file_path="relative/input.txt",
            runtime=_Runtime(object()),
        )
    )

    assert result["success"] is False
    assert "absolute path" in result["error"]
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_resolves_lazy_public_path_before_download() -> None:
    actual_work_dir = "/remote/session-1"
    provider = _RecordingSandbox(work_dir=actual_work_dir)
    manager = _Manager(provider, actual_work_dir=actual_work_dir)
    lazy = LazySandboxBackend(
        session_id="session-1",
        user_id="user-1",
        presenter=_Presenter(),
        manager_factory=lambda: manager,
    )
    runtime_backend = CompositeBackend(default=lazy, routes={})
    public_path = "/workspace/session-1/input.txt"

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://files.example.com/input.txt",
            file_path=public_path,
            runtime=_Runtime(runtime_backend),
        )
    )

    assert result == {"success": True, "path": public_path, "source": "sandbox"}
    assert manager.calls == [("session-1", "user-1")]
    assert len(provider.commands) == 1
    assert f"{actual_work_dir}/input.txt" in provider.commands[0]
    assert public_path not in provider.commands[0]


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_uses_direct_backend_async_path_resolver() -> None:
    class _ResolvingBackend(_RecordingSandbox):
        async def aresolve_path(self, path: str) -> str:
            assert path == "/workspace/session-1/input.txt"
            return "/remote/session-1/input.txt"

    backend = _ResolvingBackend(work_dir="/remote/session-1")
    public_path = "/workspace/session-1/input.txt"

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://files.example.com/input.txt",
            file_path=public_path,
            runtime=_Runtime(backend),
        )
    )

    assert result == {"success": True, "path": public_path, "source": "sandbox"}
    assert len(backend.commands) == 1
    assert "/remote/session-1/input.txt" in backend.commands[0]
    assert public_path not in backend.commands[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_kind", "expected_category"),
    [("nonzero_exit", "exit_code=17"), ("exception", "execution_error")],
)
async def test_upload_url_to_sandbox_redacts_provider_path_from_failure_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure_kind: str,
    expected_category: str,
) -> None:
    actual_path = "/remote/session-1/input.txt"
    public_path = "/workspace/session-1/input.txt"

    class _FailingSandbox(_RecordingSandbox):
        def __init__(self) -> None:
            super().__init__(work_dir="/remote/session-1")
            self.uploaded: list[tuple[str, bytes]] = []

        async def aresolve_path(self, path: str) -> str:
            return actual_path

        async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
            del command, timeout
            if failure_kind == "exception":
                raise RuntimeError(f"provider failed at {actual_path}")
            return ExecuteResponse(output=f"could not write {actual_path}", exit_code=17)

        async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
            self.uploaded.extend(files)
            return [FileUploadResponse(path=path) for path, _content in files]

    class _FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"fallback"

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            return _FakeResponse()

    monkeypatch.setattr(upload_url_tool.httpx, "AsyncClient", lambda **_kwargs: _FakeHttpClient())
    backend = _FailingSandbox()

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://files.example.com/input.txt",
            file_path=public_path,
            runtime=_Runtime(backend),
        )
    )

    assert result == {"success": True, "path": public_path, "size": 8}
    assert backend.uploaded == [(public_path, b"fallback")]
    assert expected_category in caplog.text
    assert actual_path not in caplog.text


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_redacts_provider_path_from_success_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actual_path = "/remote/session-1/input.txt"
    public_path = "/workspace/session-1/input.txt"

    class _SuccessfulSandbox(_RecordingSandbox):
        async def aresolve_path(self, path: str) -> str:
            return actual_path

        async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
            del command, timeout
            return ExecuteResponse(output=f"downloaded to {actual_path}", exit_code=0)

    caplog.set_level(logging.INFO)

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://files.example.com/input.txt",
            file_path=public_path,
            runtime=_Runtime(_SuccessfulSandbox(work_dir="/remote/session-1")),
        )
    )

    assert result == {"success": True, "path": public_path, "source": "sandbox"}
    assert actual_path not in caplog.text


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_prefers_sandbox_side_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class _FakeBackend:
        def __init__(self) -> None:
            self.commands: list[str] = []

        async def aexecute(self, command: str):
            self.commands.append(command)
            return SimpleNamespace(exit_code=0, output="")

        async def aupload_files(self, files):
            raise AssertionError("sandbox-capable backends should download inside the sandbox")

    class _FailHttpClient:
        async def __aenter__(self):
            raise AssertionError("API process should not stream when sandbox can fetch URL")

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(upload_url_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(
        upload_url_tool.httpx,
        "AsyncClient",
        lambda **_kwargs: _FailHttpClient(),
    )

    backend = _FakeBackend()
    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="/api/upload/file/input.txt",
            file_path="/workspace/input.txt",
            runtime=_Runtime(backend),
        )
    )

    assert result == {"success": True, "path": "/workspace/input.txt", "source": "sandbox"}
    assert len(backend.commands) == 1
    assert "https://app.example.com/api/upload/file/input.txt" in backend.commands[0]
    assert "/workspace/input.txt" in backend.commands[0]
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_wraps_sync_execute_in_blocking_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class _FakeBackend:
        def execute(self, command: str):
            calls.append(("execute", command))
            return SimpleNamespace(exit_code=0, output="")

        async def aupload_files(self, files):
            raise AssertionError("sandbox-capable backends should download inside the sandbox")

    async def fake_run_blocking_io(func, *args, **kwargs):
        del kwargs
        calls.append(("run_blocking_io", ""))
        return func(*args)

    monkeypatch.setattr(upload_url_tool, "run_blocking_io", fake_run_blocking_io)

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://files.example.com/input.txt",
            file_path="/workspace/input.txt",
            runtime=_Runtime(_FakeBackend()),
        )
    )

    assert result == {"success": True, "path": "/workspace/input.txt", "source": "sandbox"}
    assert calls[0][0] == "run_blocking_io"
    assert calls[1][0] == "execute"


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_streams_download(monkeypatch: pytest.MonkeyPatch) -> None:
    uploaded: list[tuple[str, bytes]] = []

    class _FakeBackend:
        async def aupload_files(self, files):
            uploaded.extend(files)
            return [SimpleNamespace(error=None)]

    class _FakeResponse:
        @property
        def content(self):
            raise AssertionError("upload_url_to_sandbox should stream downloads")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"hello "
            yield b"world"

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            assert method == "GET"
            assert request_url == "https://app.example.com/api/upload/file/input.txt"
            return _FakeResponse()

    monkeypatch.setattr(
        upload_url_tool.httpx,
        "AsyncClient",
        lambda **_kwargs: _FakeHttpClient(),
    )

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="/api/upload/file/input.txt",
            file_path="/workspace/input.txt",
            runtime=_Runtime(_FakeBackend()),
        )
    )

    assert result == {"success": True, "path": "/workspace/input.txt", "size": 11}
    assert uploaded == [("/workspace/input.txt", b"hello world")]


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_offloads_api_fallback_spool_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    uploaded: list[tuple[str, bytes]] = []

    class _FakeBackend:
        async def aupload_files(self, files):
            uploaded.extend(files)
            return [SimpleNamespace(error=None)]

    class _FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"hello "
            yield b"world"

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            return _FakeResponse()

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        monkeypatch.setattr(upload_url_tool, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(upload_url_tool, "_inside_fake_blocking_io", False, raising=False)

    monkeypatch.setattr(upload_url_tool, "SpooledTemporaryFile", _BlockingOnlySpooledFile)
    monkeypatch.setattr(upload_url_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(upload_url_tool, "_inside_fake_blocking_io", False, raising=False)
    monkeypatch.setattr(
        upload_url_tool.httpx,
        "AsyncClient",
        lambda **_kwargs: _FakeHttpClient(),
    )

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://files.example.com/input.txt",
            file_path="/workspace/input.txt",
            runtime=_Runtime(_FakeBackend()),
        )
    )

    assert result == {"success": True, "path": "/workspace/input.txt", "size": 11}
    assert uploaded == [("/workspace/input.txt", b"hello world")]
    assert calls == ["write", "write", "seek", "read", "dumps"]


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_stops_streaming_when_size_limit_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeBackend:
        async def aupload_files(self, files):
            raise AssertionError("oversized downloads should not upload")

    class _FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"x" * (upload_url_tool._MAX_FILE_SIZE + 1)

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            return _FakeResponse()

    monkeypatch.setattr(
        upload_url_tool.httpx,
        "AsyncClient",
        lambda **_kwargs: _FakeHttpClient(),
    )

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://files.example.com/huge.bin",
            file_path="/workspace/huge.bin",
            runtime=_Runtime(_FakeBackend()),
        )
    )

    assert result["success"] is False
    assert "File too large" in result["error"]


@pytest.mark.asyncio
async def test_upload_url_to_sandbox_rejects_large_bytes_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeBackend:
        async def aupload_files(self, files):
            raise AssertionError("large fallback downloads should not be uploaded as bytes")

    class _FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"x" * (upload_url_tool._FALLBACK_UPLOAD_MAX_BYTES + 1)

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            return _FakeResponse()

    monkeypatch.setattr(
        upload_url_tool.httpx,
        "AsyncClient",
        lambda **_kwargs: _FakeHttpClient(),
    )

    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://files.example.com/large.bin",
            file_path="/workspace/large.bin",
            runtime=_Runtime(_FakeBackend()),
        )
    )

    assert result["success"] is False
    assert "sandbox-side download" in result["error"]
