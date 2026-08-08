from __future__ import annotations

import asyncio
import gc
import logging
import shlex
from typing import Any

import pytest
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
from deepagents.middleware.filesystem import FilesystemMiddleware

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
    enable_capture_offload = True

    def __init__(
        self,
        *,
        work_dir: str,
        write_result_path: str | None = None,
    ) -> None:
        self._work_dir = work_dir
        self._write_result_path = write_result_path
        self.write_calls: list[tuple[str, str]] = []
        self.calls: list[tuple[Any, ...]] = []
        self.commands: list[tuple[str, int | None, str]] = []
        self.offload_calls: list[tuple[str, str, int, int | None, int | None]] = []
        self.env_vars: dict[str, str] = {"PROVIDER": "cached"}
        self.files: dict[str, bytes] = {}

    @property
    def id(self) -> str:
        return "provider-sandbox-1"

    @property
    def work_dir(self) -> str:
        return self._work_dir

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        self.commands.append((command, timeout, self.work_dir))
        return ExecuteResponse(output="complete output", exit_code=7, truncated=True)

    def ls(self, path: str) -> LsResult:
        self.calls.append(("ls", path))
        entries: list[FileInfo] = [
            {
                "path": f"{path.rstrip('/')}/report.txt",
                "is_dir": False,
                "size": 17,
                "modified_at": "2026-08-08T10:11:12Z",
            }
        ]
        return LsResult(entries=entries)

    async def als(self, path: str) -> LsResult:
        return self.ls(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        self.calls.append(("read", file_path, offset, limit))
        content = self.files.get(file_path, b"line two").decode()
        return ReadResult(
            file_data={
                "content": content,
                "encoding": "utf-8",
                "created_at": "2026-08-08T10:00:00Z",
                "modified_at": "2026-08-08T10:11:12Z",
            },
            total_lines=4,
            start_line=2,
            end_line=2,
            next_offset=2,
        )

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        return self.read(file_path, offset, limit)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        self.calls.append(("grep", pattern, path, glob, max_count))
        match: GrepMatch = {
            "path": f"{(path or self.work_dir).rstrip('/')}/report.txt",
            "line": 2,
            "text": "needle",
            "context_before": [{"line": 1, "text": "before"}],
            "context_after": [{"line": 3, "text": "after"}],
        }
        return GrepResult(matches=[match], truncated=True)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return self.grep(pattern, path, glob, max_count=max_count)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        self.calls.append(("glob", pattern, path))
        matches: list[FileInfo] = [
            {
                "path": f"{(path or self.work_dir).rstrip('/')}/report.txt",
                "is_dir": False,
                "size": 17,
                "modified_at": "2026-08-08T10:11:12Z",
            }
        ]
        return GlobResult(matches=matches, truncated=True)

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        return self.glob(pattern, path)

    def write(self, file_path: str, content: str) -> WriteResult:
        self.calls.append(("write", file_path, content))
        self.write_calls.append((file_path, content))
        self.files[file_path] = content.encode()
        return WriteResult(path=self._write_result_path or file_path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        self.calls.append(("edit", file_path, old_string, new_string, replace_all))
        return EditResult(path=file_path, occurrences=3)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return self.edit(file_path, old_string, new_string, replace_all)

    def delete(self, file_path: str) -> DeleteResult:
        self.calls.append(("delete", file_path))
        return DeleteResult(path=file_path)

    async def adelete(self, file_path: str) -> DeleteResult:
        return self.delete(file_path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        self.calls.append(("upload_files", files))
        responses = []
        for index, (path, content) in enumerate(files):
            if index == 0:
                self.files[path] = content
            responses.append(
                FileUploadResponse(
                    path=path,
                    error=None if index == 0 else "permission_denied",
                )
            )
        return responses

    async def aupload_files(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[FileUploadResponse]:
        return self.upload_files(files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        self.calls.append(("download_files", paths))
        return [
            FileDownloadResponse(
                path=path,
                content=self.files.get(path) if index == 0 else None,
                error=None if index == 0 else "file_not_found",
            )
            for index, path in enumerate(paths)
        ]

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self.download_files(paths)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return self.write(file_path, content)

    def execute_with_offload(
        self,
        command: str,
        capture_path: str,
        *,
        max_inline_bytes: int,
        max_capture_bytes: int | None = None,
        timeout: int | None = None,
    ) -> ExecuteOffloadResult:
        self.offload_calls.append(
            (command, capture_path, max_inline_bytes, max_capture_bytes, timeout)
        )
        response = self.execute(command, timeout=timeout)
        if not self.enable_capture_offload:
            return ExecuteOffloadResult(offloaded=False, response=response)
        self.files[capture_path] = b"complete captured provider output"
        return ExecuteOffloadResult(
            offloaded=True,
            response=ExecuteResponse(
                output="provider output preview",
                exit_code=response.exit_code,
                truncated=response.truncated,
            ),
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
        return self.execute_with_offload(
            command,
            capture_path,
            max_inline_bytes=max_inline_bytes,
            max_capture_bytes=max_capture_bytes,
            timeout=timeout,
        )


class _E2BShapedSandbox(_RecordingSandbox):
    pass


class _CubeSandboxShapedSandbox(_RecordingSandbox):
    pass


class _DaytonaShapedSandbox(_RecordingSandbox):
    pass


class _Manager:
    def __init__(
        self,
        provider: _RecordingSandbox,
        *,
        entered: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
        failure: Exception | None = None,
        actual_work_dir: str | None = None,
    ) -> None:
        self._provider = provider
        self._entered = entered
        self._release = release
        self._failure = failure
        self._actual_work_dir = actual_work_dir
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
            self._actual_work_dir or self._provider.work_dir,
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
async def test_relative_provider_result_path_maps_to_public_workspace() -> None:
    provider = _RecordingSandbox(
        work_dir="/remote/home/sessions/session-1",
        write_result_path="reports/result.txt",
    )
    backend = _lazy(_Manager(provider))

    result = await backend.awrite("/tmp/request.txt", "ok")

    assert result.path == "/workspace/session-1/reports/result.txt"


def test_protocol_shape_explicitly_overrides_every_delegated_method() -> None:
    delegated_methods = {
        "ls",
        "als",
        "read",
        "aread",
        "grep",
        "agrep",
        "glob",
        "aglob",
        "write",
        "awrite",
        "edit",
        "aedit",
        "delete",
        "adelete",
        "upload_files",
        "aupload_files",
        "download_files",
        "adownload_files",
        "execute",
        "aexecute",
        "execute_with_offload",
        "aexecute_with_offload",
        "resolve_path",
        "aresolve_path",
    }

    assert delegated_methods <= LazySandboxBackend.__dict__.keys()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    [
        "als",
        "aread",
        "agrep",
        "aglob",
        "awrite",
        "aedit",
        "adelete",
        "aupload_files",
        "adownload_files",
        "aexecute",
    ],
)
async def test_async_protocol_delegates_with_path_mapping_and_complete_results(
    method_name: str,
) -> None:
    actual = "/remote/home/sessions/session-1"
    provider = _RecordingSandbox(work_dir=actual)
    provider.files[f"{actual}/download.txt"] = b"downloaded bytes"
    backend = _lazy(_Manager(provider))

    if method_name == "als":
        result = await backend.als("/workspace/session-1/reports")
        assert result == LsResult(
            entries=[
                {
                    "path": "/workspace/session-1/reports/report.txt",
                    "is_dir": False,
                    "size": 17,
                    "modified_at": "2026-08-08T10:11:12Z",
                }
            ]
        )
        assert provider.calls[-1] == ("ls", f"{actual}/reports")
    elif method_name == "aread":
        result = await backend.aread("/workspace/session-1/report.txt", 1, 1)
        assert result == ReadResult(
            file_data={
                "content": "line two",
                "encoding": "utf-8",
                "created_at": "2026-08-08T10:00:00Z",
                "modified_at": "2026-08-08T10:11:12Z",
            },
            total_lines=4,
            start_line=2,
            end_line=2,
            next_offset=2,
        )
        assert provider.calls[-1] == ("read", f"{actual}/report.txt", 1, 1)
    elif method_name == "agrep":
        result = await backend.agrep(
            "needle",
            "/workspace/session-1/reports",
            "*.txt",
            max_count=5,
        )
        assert result == GrepResult(
            matches=[
                {
                    "path": "/workspace/session-1/reports/report.txt",
                    "line": 2,
                    "text": "needle",
                    "context_before": [{"line": 1, "text": "before"}],
                    "context_after": [{"line": 3, "text": "after"}],
                }
            ],
            truncated=True,
        )
        assert provider.calls[-1] == (
            "grep",
            "needle",
            f"{actual}/reports",
            "*.txt",
            5,
        )
    elif method_name == "aglob":
        result = await backend.aglob("*.txt", "/workspace/session-1/reports")
        assert result == GlobResult(
            matches=[
                {
                    "path": "/workspace/session-1/reports/report.txt",
                    "is_dir": False,
                    "size": 17,
                    "modified_at": "2026-08-08T10:11:12Z",
                }
            ],
            truncated=True,
        )
        assert provider.calls[-1] == ("glob", "*.txt", f"{actual}/reports")
    elif method_name == "awrite":
        result = await backend.awrite("/workspace/session-1/new.txt", "new content")
        assert result == WriteResult(path="/workspace/session-1/new.txt")
        assert provider.calls[-1] == ("write", f"{actual}/new.txt", "new content")
    elif method_name == "aedit":
        result = await backend.aedit(
            "/workspace/session-1/report.txt",
            "old",
            "new",
            replace_all=True,
        )
        assert result == EditResult(
            path="/workspace/session-1/report.txt",
            occurrences=3,
        )
        assert provider.calls[-1] == (
            "edit",
            f"{actual}/report.txt",
            "old",
            "new",
            True,
        )
    elif method_name == "adelete":
        result = await backend.adelete("/workspace/session-1/report.txt")
        assert result == DeleteResult(path="/workspace/session-1/report.txt")
        assert provider.calls[-1] == ("delete", f"{actual}/report.txt")
    elif method_name == "aupload_files":
        result = await backend.aupload_files(
            [
                ("/workspace/session-1/ok.bin", b"ok"),
                ("/workspace/session-1/denied.bin", b"denied"),
            ]
        )
        assert result == [
            FileUploadResponse(path="/workspace/session-1/ok.bin"),
            FileUploadResponse(
                path="/workspace/session-1/denied.bin",
                error="permission_denied",
            ),
        ]
        assert provider.calls[-1] == (
            "upload_files",
            [(f"{actual}/ok.bin", b"ok"), (f"{actual}/denied.bin", b"denied")],
        )
    elif method_name == "adownload_files":
        result = await backend.adownload_files(
            [
                "/workspace/session-1/download.txt",
                "/workspace/session-1/missing.txt",
            ]
        )
        assert result == [
            FileDownloadResponse(
                path="/workspace/session-1/download.txt",
                content=b"downloaded bytes",
            ),
            FileDownloadResponse(
                path="/workspace/session-1/missing.txt",
                error="file_not_found",
            ),
        ]
        assert provider.calls[-1] == (
            "download_files",
            [f"{actual}/download.txt", f"{actual}/missing.txt"],
        )
    else:
        result = await backend.aexecute("printf async", timeout=23)
        assert result == ExecuteResponse(
            output="complete output",
            exit_code=7,
            truncated=True,
        )
        assert provider.commands[-1] == (
            f"export LAMBCHAT_WORKSPACE={shlex.quote(actual)}; printf async",
            23,
            actual,
        )


@pytest.mark.asyncio
async def test_write_error_preserves_error_and_none_path() -> None:
    class _WriteErrorSandbox(_RecordingSandbox):
        async def awrite(self, file_path: str, content: str) -> WriteResult:
            self.calls.append(("awrite", file_path, content))
            return WriteResult(error="already exists", path=None)

    provider = _WriteErrorSandbox(work_dir="/remote/session-1")
    backend = _lazy(_Manager(provider))

    result = await backend.awrite("/workspace/session-1/report.txt", "ignored")

    assert result == WriteResult(error="already exists", path=None)


def _call_sync_method(backend: LazySandboxBackend, method_name: str) -> object:
    if method_name == "ls":
        return backend.ls("/workspace/session-1/reports")
    if method_name == "read":
        return backend.read("/workspace/session-1/report.txt", 1, 1)
    if method_name == "grep":
        return backend.grep(
            "needle",
            "/workspace/session-1/reports",
            "*.txt",
            max_count=5,
        )
    if method_name == "glob":
        return backend.glob("*.txt", "/workspace/session-1/reports")
    if method_name == "write":
        return backend.write("/workspace/session-1/new.txt", "new content")
    if method_name == "edit":
        return backend.edit("/workspace/session-1/report.txt", "old", "new", True)
    if method_name == "delete":
        return backend.delete("/workspace/session-1/report.txt")
    if method_name == "upload_files":
        return backend.upload_files([("/workspace/session-1/new.bin", b"new")])
    if method_name == "download_files":
        return backend.download_files(["/workspace/session-1/new.bin"])
    if method_name == "execute":
        return backend.execute("printf sync", timeout=19)
    if method_name == "execute_with_offload":
        return backend.execute_with_offload(
            "printf offload",
            "/workspace/session-1/large_tool_results/sync",
            max_inline_bytes=8,
            max_capture_bytes=64,
            timeout=17,
        )
    return backend.resolve_path("/workspace/session-1/report.txt")


@pytest.mark.parametrize(
    "method_name",
    [
        "ls",
        "read",
        "grep",
        "glob",
        "write",
        "edit",
        "delete",
        "upload_files",
        "download_files",
        "execute",
        "execute_with_offload",
        "resolve_path",
    ],
)
def test_sync_protocol_fails_clearly_before_readiness(method_name: str) -> None:
    provider = _RecordingSandbox(work_dir="/remote/session-1")
    backend = _lazy(_Manager(provider))

    with pytest.raises(
        RuntimeError,
        match="Lazy sandbox is not initialized; use async operations first",
    ):
        _call_sync_method(backend, method_name)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    [
        "ls",
        "read",
        "grep",
        "glob",
        "write",
        "edit",
        "delete",
        "upload_files",
        "download_files",
        "execute",
        "execute_with_offload",
        "resolve_path",
    ],
)
async def test_sync_protocol_delegates_after_async_readiness(method_name: str) -> None:
    actual = "/remote/session-1"
    provider = _RecordingSandbox(work_dir=actual)
    backend = _lazy(_Manager(provider))
    await backend.aresolve_path("/workspace/session-1")

    result = _call_sync_method(backend, method_name)

    assert result is not None
    if method_name == "resolve_path":
        assert result == f"{actual}/report.txt"
    elif method_name == "execute":
        assert result == ExecuteResponse("complete output", exit_code=7, truncated=True)
    elif method_name == "execute_with_offload":
        assert isinstance(result, ExecuteOffloadResult)
        assert result.offloaded is True


@pytest.mark.asyncio
async def test_shared_provider_commands_use_isolated_workspace_env_without_mutation() -> None:
    provider = _RecordingSandbox(work_dir="/remote/provider-cwd")
    backend_a = _lazy(
        _Manager(provider, actual_work_dir="/remote/user sessions/a"),
        session_id="a",
    )
    backend_b = _lazy(
        _Manager(provider, actual_work_dir="/remote/user sessions/b"),
        session_id="b",
    )

    result_a, result_b = await asyncio.gather(
        backend_a.aexecute("printf session-a"),
        backend_b.aexecute("printf session-b"),
    )

    assert result_a.output == "complete output"
    assert result_b.output == "complete output"
    command_records = {
        command.rsplit("; ", 1)[-1]: (command, cwd) for command, _, cwd in provider.commands
    }
    assert command_records == {
        "printf session-a": (
            "export LAMBCHAT_WORKSPACE='/remote/user sessions/a'; printf session-a",
            "/remote/provider-cwd",
        ),
        "printf session-b": (
            "export LAMBCHAT_WORKSPACE='/remote/user sessions/b'; printf session-b",
            "/remote/provider-cwd",
        ),
    }
    assert provider.env_vars == {"PROVIDER": "cached"}
    assert provider.work_dir == "/remote/provider-cwd"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_type",
    [_E2BShapedSandbox, _CubeSandboxShapedSandbox, _DaytonaShapedSandbox],
)
async def test_offload_maps_capture_and_returns_public_readable_pointer(
    provider_type: type[_RecordingSandbox],
) -> None:
    actual = "/remote/session with spaces"
    provider = provider_type(work_dir=actual)
    lazy = _lazy(_Manager(provider))
    composite = CompositeBackend(
        default=lazy,
        routes={},
        artifacts_root=lazy.work_dir,
    )
    middleware = FilesystemMiddleware(
        backend=composite,
        tool_token_limit_before_evict=2,
    )
    public_capture = f"{lazy.work_dir}/large_tool_results/tool-call-1"

    assert isinstance(lazy, BaseSandbox)
    assert middleware._large_tool_results_prefix == (  # noqa: SLF001
        f"{lazy.work_dir}/large_tool_results"
    )
    result = await lazy.aexecute_with_offload(
        "python generate.py",
        public_capture,
        max_inline_bytes=8,
        max_capture_bytes=128,
        timeout=31,
    )
    tool_content = middleware._interpret_capture_output(  # noqa: SLF001
        result,
        public_capture,
        "tool-call-1",
    )
    read_result = await lazy.aread(public_capture)

    expected_command = f"export LAMBCHAT_WORKSPACE={shlex.quote(actual)}; python generate.py"
    assert provider.offload_calls == [
        (expected_command, f"{actual}/large_tool_results/tool-call-1", 8, 128, 31)
    ]
    assert provider.commands == [(expected_command, 31, actual)]
    assert public_capture in tool_content
    assert actual not in tool_content
    assert read_result.file_data is not None
    assert read_result.file_data["content"] == "complete captured provider output"
    assert provider.env_vars == {"PROVIDER": "cached"}


@pytest.mark.asyncio
async def test_disabled_provider_capture_offload_executes_command_once() -> None:
    actual = "/remote/session-1"
    provider = _RecordingSandbox(work_dir=actual)
    provider.enable_capture_offload = False
    lazy = _lazy(_Manager(provider))
    public_capture = f"{lazy.work_dir}/large_tool_results/tool-call-disabled"

    result = await lazy.aexecute_with_offload(
        "printf full",
        public_capture,
        max_inline_bytes=4,
    )

    expected_command = f"export LAMBCHAT_WORKSPACE={actual}; printf full"
    assert result == ExecuteOffloadResult(
        offloaded=False,
        response=ExecuteResponse(
            output="complete output",
            exit_code=7,
            truncated=True,
        ),
    )
    assert provider.offload_calls == [
        (expected_command, f"{actual}/large_tool_results/tool-call-disabled", 4, None, None)
    ]
    assert provider.commands == [(expected_command, None, actual)]
    assert f"{actual}/large_tool_results/tool-call-disabled" not in provider.files


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
async def test_cancelling_one_initialization_waiter_keeps_shared_creation_alive() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider, entered=entered, release=release)
    backend = _lazy(manager)

    cancelled = asyncio.create_task(backend.awrite("cancelled.txt", "cancelled"))
    surviving = asyncio.create_task(backend.awrite("surviving.txt", "surviving"))
    await entered.wait()
    await asyncio.sleep(0)

    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release.set()

    result = await surviving
    later = await backend.awrite("later.txt", "later")

    assert result.path == "/workspace/session-1/surviving.txt"
    assert later.path == "/workspace/session-1/later.txt"
    assert manager.calls == [("session-1", "user-1")]
    assert provider.write_calls == [
        ("/remote/home/sessions/session-1/surviving.txt", "surviving"),
        ("/remote/home/sessions/session-1/later.txt", "later"),
    ]


@pytest.mark.asyncio
async def test_cancelling_sole_waiter_rechecks_waiters_after_event_barrier() -> None:
    manager_entered = asyncio.Event()
    release_manager = asyncio.Event()
    event_entered = asyncio.Event()
    release_event = asyncio.Event()
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider, entered=manager_entered, release=release_manager)
    presenter = _Presenter()
    backend = _lazy(manager, presenter=presenter)

    async def gated_event() -> None:
        event_entered.set()
        await release_event.wait()

    cancelled = asyncio.create_task(backend.awrite("cancelled.txt", "cancelled"))
    await manager_entered.wait()
    inflight_event = asyncio.create_task(
        backend._attempt_event("gated", gated_event)  # noqa: SLF001
    )
    await event_entered.wait()

    cancelled.cancel()
    await asyncio.sleep(0)
    surviving = asyncio.create_task(backend.awrite("surviving.txt", "surviving"))
    await asyncio.sleep(0)

    assert not cancelled.done()
    assert not surviving.done()
    assert manager.calls == [("session-1", "user-1")]

    release_event.set()
    await inflight_event
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release_manager.set()

    result = await surviving

    assert result.path == "/workspace/session-1/surviving.txt"
    assert manager.calls == [("session-1", "user-1")]
    assert provider.write_calls == [("/remote/home/sessions/session-1/surviving.txt", "surviving")]
    assert presenter.attempts == [
        ("starting",),
        (
            "ready",
            "provider-sandbox-1",
            "/remote/home/sessions/session-1",
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("manager_failure", [None, RuntimeError("provider failed")])
async def test_cancelling_sole_waiter_abandons_wrapper_and_consumes_manager_outcome(
    manager_failure: Exception | None,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    event_entered = asyncio.Event()
    release_event = asyncio.Event()
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(
        provider,
        entered=entered,
        release=release,
        failure=manager_failure,
    )
    presenter = _Presenter()
    backend = _lazy(manager, presenter=presenter)
    unobserved_contexts: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    previous_exception_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: unobserved_contexts.append(context))

    async def gated_event() -> None:
        event_entered.set()
        await release_event.wait()

    try:
        operation = asyncio.create_task(backend.awrite("cancelled.txt", "cancelled"))
        await entered.wait()
        inflight_event = asyncio.create_task(
            backend._attempt_event("gated", gated_event)  # noqa: SLF001
        )
        await event_entered.wait()
        operation.cancel()
        await asyncio.sleep(0)
        assert not operation.done()

        release_event.set()
        await inflight_event
        with pytest.raises(asyncio.CancelledError):
            await operation

        with pytest.raises(RuntimeError, match="Lazy sandbox is closed"):
            await asyncio.wait_for(backend.awrite("later.txt", "later"), timeout=0.1)

        release.set()
        initialization_task = backend._initialization_task  # noqa: SLF001
        assert initialization_task is not None
        for _ in range(20):
            if initialization_task.done():
                break
            await asyncio.sleep(0)
        assert initialization_task.done()

        assert manager.calls == [("session-1", "user-1")]
        assert provider.write_calls == []
        assert presenter.attempts == [("starting",)]

        del initialization_task, inflight_event, operation, backend
        gc.collect()
        await asyncio.sleep(0)
        assert unobserved_contexts == []
    finally:
        loop.set_exception_handler(previous_exception_handler)


@pytest.mark.asyncio
async def test_aclose_before_initialization_is_idempotent_and_never_calls_manager() -> None:
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider)
    backend = _lazy(manager)

    await backend.aclose()
    await backend.aclose()

    with pytest.raises(RuntimeError, match="Lazy sandbox is closed"):
        await backend.awrite("later.txt", "later")
    assert manager.calls == []
    assert provider.write_calls == []


@pytest.mark.asyncio
async def test_aclose_during_initialization_returns_without_waiting_for_manager() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider, entered=entered, release=release)
    presenter = _Presenter()
    backend = _lazy(manager, presenter=presenter)

    operation = asyncio.create_task(backend.awrite("waiting.txt", "waiting"))
    await entered.wait()

    await asyncio.wait_for(backend.aclose(), timeout=0.1)
    assert not operation.done()
    assert manager.calls == [("session-1", "user-1")]

    release.set()
    with pytest.raises(RuntimeError, match="Lazy sandbox is closed"):
        await operation
    with pytest.raises(RuntimeError, match="Lazy sandbox is closed"):
        await backend.awrite("later.txt", "later")

    assert provider.write_calls == []
    assert presenter.attempts == [("starting",)]


@pytest.mark.asyncio
async def test_aclose_serializes_inflight_event_and_suppresses_event_queued_behind_it() -> None:
    event_entered = asyncio.Event()
    release_event = asyncio.Event()
    event_attempts: list[str] = []
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    backend = _lazy(_Manager(provider))
    await backend.awrite("before-close.txt", "before")

    async def gated_event() -> None:
        event_attempts.append("inflight-started")
        event_entered.set()
        await release_event.wait()
        event_attempts.append("inflight-finished")

    async def queued_event() -> None:
        event_attempts.append("queued-emitted")

    inflight_event = asyncio.create_task(
        backend._attempt_event("gated", gated_event)  # noqa: SLF001
    )
    await event_entered.wait()
    close_task = asyncio.create_task(backend.aclose())
    await asyncio.sleep(0)

    assert not close_task.done()
    during_close = await backend.awrite("during-close.txt", "during")
    queued_event_task = asyncio.create_task(
        backend._attempt_event("queued", queued_event)  # noqa: SLF001
    )
    await asyncio.sleep(0)

    assert during_close.path == "/workspace/session-1/during-close.txt"
    assert not queued_event_task.done()

    release_event.set()
    await inflight_event
    await close_task
    await queued_event_task
    with pytest.raises(RuntimeError, match="Lazy sandbox is closed"):
        await backend.awrite("after-close.txt", "after")

    assert event_attempts == ["inflight-started", "inflight-finished"]
    assert provider.write_calls == [
        ("/remote/home/sessions/session-1/before-close.txt", "before"),
        ("/remote/home/sessions/session-1/during-close.txt", "during"),
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
async def test_sync_operation_is_rejected_until_ready_event_attempt_finishes() -> None:
    ready_entered = asyncio.Event()
    release_ready = asyncio.Event()

    class _GatedReadyPresenter(_Presenter):
        async def emit_sandbox_ready(self, sandbox_id: str, work_dir: str) -> dict[str, Any]:
            self.attempts.append(("ready", sandbox_id, work_dir))
            ready_entered.set()
            await release_ready.wait()
            return {}

    actual = "/remote/home/sessions/session-1"
    provider = _RecordingSandbox(work_dir=actual)
    backend = _lazy(_Manager(provider), presenter=_GatedReadyPresenter())

    initialization = asyncio.create_task(backend.awrite("first.txt", "first"))
    await ready_entered.wait()

    try:
        with pytest.raises(
            RuntimeError,
            match="Lazy sandbox is not initialized; use async operations first",
        ):
            backend.execute("printf too-early")
        assert provider.commands == []
    finally:
        release_ready.set()
        result = await initialization

    assert result.path == "/workspace/session-1/first.txt"
    assert backend.execute("printf ready") == ExecuteResponse(
        output="complete output",
        exit_code=7,
        truncated=True,
    )
    assert provider.commands == [
        (f"export LAMBCHAT_WORKSPACE={actual}; printf ready", None, actual)
    ]


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
