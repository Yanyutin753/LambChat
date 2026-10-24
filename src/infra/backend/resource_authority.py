"""Enforce resource capabilities at the shared composite file boundary."""

from __future__ import annotations

import mimetypes
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    SandboxBackendProtocol,
    WriteResult,
)

from src.infra.async_utils.loop_bridge import run_coro_sync
from src.infra.auth import tool_authority

_trusted_paths: ContextVar[frozenset[tuple[int, str]]] = ContextVar(
    "backend_server_paths", default=frozenset()
)


@contextmanager
def trusted_backend_io(backend: Any, *paths: str):
    """Server-owned evidence/handoff I/O only; never span model or tool invocation."""
    scoped = {(id(backend), path) for path in paths}
    if any(
        path == root or path.startswith(root + "/")
        for _, path in scoped
        for root in ("/skills", "/memories")
    ):
        raise ValueError("Trusted artifact I/O cannot access personal resource mounts")
    token = _trusted_paths.set(_trusted_paths.get() | scoped)
    try:
        yield
    finally:
        _trusted_paths.reset(token)


class AuthorizedCompositeBackend(CompositeBackend):
    def __init__(self, default, routes, *, user_id: str | None, artifacts_root: str = "/"):
        super().__init__(default=default, routes=routes, artifacts_root=artifacts_root)
        self._authority_user_id = user_id
        self._sandbox_mode = isinstance(default, SandboxBackendProtocol)

    async def _authorize(self, paths: list[str], action: str) -> str | None:
        unchecked = []
        for path in paths:
            if ".." in path.replace("\\", "/").split("/") or "\x00" in path:
                return "Permission denied: invalid resource path"
            if (id(self), path) not in _trusted_paths.get():
                unchecked.append(path)
        if not unchecked:
            return None
        user = await tool_authority.resolve_tool_user(self._authority_user_id)
        if not user:
            return "Permission denied: active account required"
        permissions = set(user.permissions)
        for path in unchecked:
            resource = next(
                (
                    name
                    for name in ("skills", "memories", "evidence")
                    if path == "/" + name or path.startswith("/" + name + "/")
                ),
                None,
            )
            if resource == "evidence":
                if action != "read":
                    return "Permission denied: evidence is server-managed"
                required = "session:read"
            elif resource in {"skills", "memories"}:
                name = "skill" if resource == "skills" else "memory"
                required = f"{name}:{'write' if action == 'upload' else action}"
            elif self._sandbox_mode:
                required = "sandbox:read" if action == "read" else "sandbox:execute"
            elif action in {"write", "upload"}:
                mime = mimetypes.guess_type(path)[0] or "text/plain"
                category = mime.split("/", 1)[0]
                if category not in {"image", "video", "audio"}:
                    category = "document"
                required = "file:upload"
                if f"file:upload:{category}" in permissions:
                    continue
            else:
                required = f"file:{action}"
            if required not in permissions:
                return f"Permission denied: {required} required"
        return None

    def _read_paths(self, path: str | None) -> list[str]:
        return ["/", *self.routes] if path is None or path == "/" else [path]

    def ls(self, path: str) -> LsResult:
        return run_coro_sync(self.als(path))

    async def als(self, path: str) -> LsResult:
        denied = await self._authorize(self._read_paths(path), "read")
        if denied:
            return LsResult(error=denied)
        return await super().als(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return run_coro_sync(self.aread(file_path, offset, limit))

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        denied = await self._authorize([file_path], "read")
        if denied:
            return ReadResult(error=denied)
        return await super().aread(file_path, offset, limit)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return run_coro_sync(self.agrep(pattern, path, glob, max_count=max_count))

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        denied = await self._authorize(self._read_paths(path), "read")
        if denied:
            return GrepResult(error=denied)
        return await super().agrep(pattern, path, glob, max_count=max_count)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        return run_coro_sync(self.aglob(pattern, path))

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        denied = await self._authorize(self._read_paths(path), "read")
        if denied:
            return GlobResult(error=denied)
        return await super().aglob(pattern, path)

    def write(self, file_path: str, content: str) -> WriteResult:
        return run_coro_sync(self.awrite(file_path, content))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        denied = await self._authorize([file_path], "write")
        if denied:
            return WriteResult(error=denied)
        return await super().awrite(file_path, content)

    def edit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult:
        return run_coro_sync(self.aedit(file_path, old_string, new_string, replace_all))

    async def aedit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult:
        denied = await self._authorize([file_path], "write")
        if denied:
            return EditResult(error=denied)
        return await super().aedit(file_path, old_string, new_string, replace_all)

    def delete(self, file_path: str) -> DeleteResult:
        return run_coro_sync(self.adelete(file_path))

    async def adelete(self, file_path: str) -> DeleteResult:
        denied = await self._authorize([file_path], "delete")
        if denied:
            return DeleteResult(error=denied)
        return await super().adelete(file_path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return run_coro_sync(self.aupload_files(files))

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        denied = await self._authorize([path for path, _ in files], "upload")
        if denied:
            return [FileUploadResponse(path=path, error="permission_denied") for path, _ in files]
        return await super().aupload_files(files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return run_coro_sync(self.adownload_files(paths))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        denied = await self._authorize(paths, "read")
        if denied:
            return [FileDownloadResponse(path=path, error="permission_denied") for path in paths]
        return await super().adownload_files(paths)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return run_coro_sync(self.aexecute(command, timeout=timeout))

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        user = await tool_authority.resolve_tool_user(self._authority_user_id)
        if not user or "sandbox:execute" not in user.permissions:
            return ExecuteResponse(
                output="Permission denied: sandbox:execute required", exit_code=1
            )
        return await super().aexecute(command, timeout=timeout)


class _ServerArtifactBackend(CompositeBackend):
    """Sidecar for server-only history I/O; never supply it to model file tools."""

    def __init__(self, backend: AuthorizedCompositeBackend):
        super().__init__(default=backend, routes={}, artifacts_root=backend.artifacts_root)
        self._backend = backend
        root = self.artifacts_root.rstrip("/")
        self._prefixes = (root + "/conversation_history/", root + "/large_tool_results/")

    @contextmanager
    def _scope(self, paths):
        if any(not path.startswith(self._prefixes) for path in paths):
            raise ValueError("Server artifact I/O is limited to history and tool results")
        with trusted_backend_io(self._backend, *paths):
            yield

    def write(self, file_path, content):
        with self._scope([file_path]):
            return self._backend.write(file_path, content)

    async def awrite(self, file_path, content):
        with self._scope([file_path]):
            return await self._backend.awrite(file_path, content)

    def edit(self, file_path, old_string, new_string, replace_all=False):
        with self._scope([file_path]):
            return self._backend.edit(file_path, old_string, new_string, replace_all)

    async def aedit(self, file_path, old_string, new_string, replace_all=False):
        with self._scope([file_path]):
            return await self._backend.aedit(file_path, old_string, new_string, replace_all)

    def upload_files(self, files):
        with self._scope([path for path, _ in files]):
            return self._backend.upload_files(files)

    async def aupload_files(self, files):
        with self._scope([path for path, _ in files]):
            return await self._backend.aupload_files(files)

    def download_files(self, paths):
        with self._scope(paths):
            return self._backend.download_files(paths)

    async def adownload_files(self, paths):
        with self._scope(paths):
            return await self._backend.adownload_files(paths)


def server_artifact_backend(backend):
    return (
        _ServerArtifactBackend(backend)
        if isinstance(backend, AuthorizedCompositeBackend)
        else backend
    )


def protect_server_artifact_eviction(middleware):
    """Give only internal eviction methods a sidecar; model tools keep the guarded backend."""
    import copy
    import inspect

    backend = getattr(middleware, "backend", None)
    if not isinstance(backend, AuthorizedCompositeBackend) or getattr(
        middleware, "_authority_eviction", False
    ):
        return middleware

    def wrap(method, receives_backend):
        def scoped_arguments(args, kwargs):
            if not receives_backend:
                return args, kwargs
            if len(args) >= 2:
                args = (args[0], server_artifact_backend(args[1]), *args[2:])
            elif "resolved_backend" in kwargs:
                kwargs = {
                    **kwargs,
                    "resolved_backend": server_artifact_backend(kwargs["resolved_backend"]),
                }
            return args, kwargs

        def scoped_instance():
            scoped = copy.copy(middleware)
            scoped.backend = server_artifact_backend(backend)
            return scoped

        if inspect.iscoroutinefunction(method):

            async def asynchronous(*args, **kwargs):
                args, kwargs = scoped_arguments(args, kwargs)
                return await method(scoped_instance(), *args, **kwargs)

            return asynchronous

        def synchronous(*args, **kwargs):
            args, kwargs = scoped_arguments(args, kwargs)
            return method(scoped_instance(), *args, **kwargs)

        return synchronous

    for name, receives_backend in (
        ("_evict_and_truncate_messages", False),
        ("_aevict_and_truncate_messages", False),
        ("_process_large_message", True),
        ("_aprocess_large_message", True),
    ):
        method = getattr(type(middleware), name, None)
        if method is not None:
            setattr(middleware, name, wrap(method, receives_backend))
    middleware._authority_eviction = True
    return middleware
