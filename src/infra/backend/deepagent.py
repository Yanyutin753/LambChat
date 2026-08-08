"""
DeepAgent Backend 构建模块

为 DeepAgent 创建不同模式的具体 Backend 实例。

Skills 路径现在使用 SkillsStoreBackend，支持 LLM 直接读写 skills 到 MongoDB。
"""

import re
from typing import Any, cast

from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
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

from src.infra.logging import get_logger

logger = get_logger(__name__)


def _safe_session_id(session_id: str | None) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_id or "").strip(".-")
    return safe[:80] if safe else "session"


def _prefix_file_info_path(info: FileInfo, workspace_path: str) -> FileInfo:
    prefixed: dict[str, object] = dict(info)
    path = str(prefixed.get("path", ""))
    if path.startswith("/"):
        prefixed["path"] = f"{workspace_path}{path}"
    return cast(FileInfo, prefixed)


class WorkflowScopedBackend(BackendProtocol):
    """Expose a session workflow path while storing files under a scoped backend root."""

    def __init__(self, backend: BackendProtocol, workspace_path: str) -> None:
        self._backend = backend
        self.workspace_path = workspace_path.rstrip("/")

    def _strip_path(self, path: str | None) -> str:
        if path is None or path == "/":
            return "/"
        if path == self.workspace_path:
            return "/"
        prefix = f"{self.workspace_path}/"
        if path.startswith(prefix):
            return "/" + path[len(prefix) :]
        return path

    def _prefix_path(self, path: str) -> str:
        if path.startswith(self.workspace_path):
            return path
        if path.startswith("/"):
            return f"{self.workspace_path}{path}"
        return f"{self.workspace_path}/{path}"

    def ls(self, path: str) -> LsResult:
        result = self._backend.ls(self._strip_path(path))
        if result.error:
            return result
        return LsResult(
            entries=[
                _prefix_file_info_path(info, self.workspace_path) for info in (result.entries or [])
            ]
        )

    async def als(self, path: str) -> LsResult:
        result = await self._backend.als(self._strip_path(path))
        if result.error:
            return result
        return LsResult(
            entries=[
                _prefix_file_info_path(info, self.workspace_path) for info in (result.entries or [])
            ]
        )

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return self._backend.read(self._strip_path(file_path), offset, limit)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return await self._backend.aread(self._strip_path(file_path), offset, limit)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        result = self._backend.grep(
            pattern,
            self._strip_path(path),
            glob,
            max_count=max_count,
        )
        if result.error:
            return result
        return GrepResult(
            matches=[
                GrepMatch(**{**match, "path": self._prefix_path(match["path"])})
                for match in (result.matches or [])
            ],
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
        result = await self._backend.agrep(
            pattern,
            self._strip_path(path),
            glob,
            max_count=max_count,
        )
        if result.error:
            return result
        return GrepResult(
            matches=[
                GrepMatch(**{**match, "path": self._prefix_path(match["path"])})
                for match in (result.matches or [])
            ],
            truncated=result.truncated,
        )

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        result = self._backend.glob(pattern, self._strip_path(path))
        if result.error:
            return result
        return GlobResult(
            matches=[
                _prefix_file_info_path(info, self.workspace_path) for info in (result.matches or [])
            ],
            truncated=result.truncated,
        )

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        result = await self._backend.aglob(pattern, self._strip_path(path))
        if result.error:
            return result
        return GlobResult(
            matches=[
                _prefix_file_info_path(info, self.workspace_path) for info in (result.matches or [])
            ],
            truncated=result.truncated,
        )

    def write(self, file_path: str, content: str) -> WriteResult:
        result = self._backend.write(self._strip_path(file_path), content)
        path = self._prefix_path(result.path) if result.path is not None else None
        return WriteResult(error=result.error, path=path)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        result = await self._backend.awrite(self._strip_path(file_path), content)
        path = self._prefix_path(result.path) if result.path is not None else None
        return WriteResult(error=result.error, path=path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = self._backend.edit(
            self._strip_path(file_path), old_string, new_string, replace_all
        )
        path = self._prefix_path(result.path) if result.path is not None else None
        return EditResult(error=result.error, path=path, occurrences=result.occurrences)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = await self._backend.aedit(
            self._strip_path(file_path),
            old_string,
            new_string,
            replace_all,
        )
        path = self._prefix_path(result.path) if result.path is not None else None
        return EditResult(error=result.error, path=path, occurrences=result.occurrences)

    def delete(self, file_path: str) -> DeleteResult:
        result = self._backend.delete(self._strip_path(file_path))
        if result.path is None:
            return result
        return DeleteResult(path=self._prefix_path(result.path))

    async def adelete(self, file_path: str) -> DeleteResult:
        result = await self._backend.adelete(self._strip_path(file_path))
        if result.path is None:
            return result
        return DeleteResult(path=self._prefix_path(result.path))

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        results = self._backend.upload_files(
            [(self._strip_path(path), content) for path, content in files]
        )
        return [
            FileUploadResponse(path=self._prefix_path(result.path), error=result.error)
            for result in results
        ]

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        results = await self._backend.aupload_files(
            [(self._strip_path(path), content) for path, content in files]
        )
        return [
            FileUploadResponse(path=self._prefix_path(result.path), error=result.error)
            for result in results
        ]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        results = self._backend.download_files([self._strip_path(path) for path in paths])
        return [
            FileDownloadResponse(
                path=self._prefix_path(result.path),
                content=result.content,
                error=result.error,
            )
            for result in results
        ]

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        results = await self._backend.adownload_files([self._strip_path(path) for path in paths])
        return [
            FileDownloadResponse(
                path=self._prefix_path(result.path),
                content=result.content,
                error=result.error,
            )
            for result in results
        ]


def _create_routes(
    assistant_id: str,
    user_id: str,
) -> dict[str, BackendProtocol]:
    """创建通用的 backend 路由（skills + memories）"""
    from src.infra.backend.skills_store import create_skills_backend

    skills_backend = create_skills_backend(user_id=user_id)

    return {
        "/skills/": skills_backend,
        "/memories/": StoreBackend(namespace=lambda _rt: (assistant_id, "memories")),
    }


def create_memory_backend(
    assistant_id: str,
    user_id: str | None = None,
) -> CompositeBackend:
    """创建基于内存的具体 Backend（不使用长期存储）。"""
    from src.infra.backend.skills_store import create_skills_backend

    skills_backend = create_skills_backend(user_id=user_id or "default")
    return CompositeBackend(
        default=StateBackend(),
        routes={"/skills/": skills_backend},
    )


def create_persistent_backend(
    assistant_id: str,
    user_id: str | None = None,
    session_id: str | None = None,
) -> CompositeBackend:
    """创建基于 Store 的具体 Backend（PostgreSQL / MongoDB 通用）。

    底层 Store 由 create_deep_agent 传入，此处只负责 namespace 路由。
    """
    routes = _create_routes(assistant_id, user_id or "default")
    workflow_session_id = _safe_session_id(session_id)
    workspace_path = f"/workflow/{workflow_session_id}"
    filesystem_backend = StoreBackend(
        namespace=lambda _rt: (assistant_id, "workflow", workflow_session_id)
    )

    return CompositeBackend(
        default=WorkflowScopedBackend(filesystem_backend, workspace_path),
        routes=routes,
    )


def create_sandbox_backend(
    sandbox_backend: Any,
    assistant_id: str,
    user_id: str | None = None,
) -> CompositeBackend:
    """创建基于沙箱的具体 Backend。"""
    routes = _create_routes(assistant_id, user_id or "default")

    return CompositeBackend(
        default=sandbox_backend,
        routes=routes,
        # Anchor offloaded artifacts (conversation history, large tool
        # results) at the sandbox work_dir. The CompositeBackend default of
        # '/' is not writable by the non-root sandbox user, which made the
        # summarization middleware offload fail with an empty exit-code-1
        # error (issue #195).
        artifacts_root=getattr(sandbox_backend, "work_dir", "/home/user"),
    )
