"""E2B 沙箱后端

使用 E2B Python SDK 提供沙箱命令执行和文件操作。
支持 Firecracker microVM 隔离，~150ms 冷启动。

注意：
- E2B sandbox 有 timeout，需要在工作期间定期调 set_timeout() 续期。
- 所有同步 SDK 调用通过 asyncio.to_thread 在线程池中执行，避免阻塞事件循环。
"""

import asyncio
import os
from typing import Literal

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# 默认超时 30 分钟（秒）
_DEFAULT_TIMEOUT = 30 * 60


class E2BBackend(BaseSandbox):
    """E2B 沙箱后端

    使用 e2b Python SDK 执行命令和操作文件。
    所有同步 SDK 调用通过 asyncio.to_thread 在线程池中执行，避免阻塞事件循环。
    """

    def __init__(
        self,
        sandbox: object,  # e2b.Sandbox — 避免 top-level import
        timeout: int | None = None,
    ):
        self._sandbox = sandbox
        self._timeout = (
            timeout or settings.E2B_TIMEOUT or int(os.environ.get("E2B_TIMEOUT", _DEFAULT_TIMEOUT))
        )

    @property
    def id(self) -> str:
        return self._sandbox.sandbox_id

    @property
    def work_dir(self) -> str:
        return "/home/user"

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        effective_timeout = min(timeout or self._timeout, self._timeout)

        try:
            result = self._sandbox.commands.run(
                cmd=command,
                timeout=effective_timeout,
            )
            return ExecuteResponse(
                output=result.stdout or "",
                exit_code=result.exit_code,
                truncated=False,
            )
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                logger.warning(f"Command timed out after {effective_timeout}s: {command[:100]}...")
                return ExecuteResponse(
                    output=f"Command timed out after {effective_timeout} seconds",
                    exit_code=-1,
                    truncated=False,
                )
            logger.error(f"Command failed: {e}")
            return ExecuteResponse(
                output=f"Command failed: {e}",
                exit_code=-1,
                truncated=False,
            )

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        effective_timeout = min(timeout or self._timeout, self._timeout)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.execute, command, timeout=timeout),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Client-side timeout after {effective_timeout}s: {command[:100]}...")
            return ExecuteResponse(
                output=f"Command timed out after {effective_timeout} seconds",
                exit_code=-1,
                truncated=False,
            )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            try:
                self._sandbox.files.write(path=path, data=content)
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception as e:
                error_type: (
                    Literal["file_not_found", "permission_denied", "is_directory", "invalid_path"]
                    | None
                ) = None
                if "permission" in str(e).lower():
                    error_type = "permission_denied"
                elif "directory" in str(e).lower():
                    error_type = "is_directory"
                else:
                    error_type = "file_not_found"
                logger.error(f"Failed to upload {path}: {e}")
                responses.append(FileUploadResponse(path=path, error=error_type))
        return responses

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return await asyncio.to_thread(self.upload_files, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            try:
                content = self._sandbox.files.read(path, format="bytes")
                responses.append(
                    FileDownloadResponse(path=path, content=bytes(content), error=None)
                )
            except Exception as e:
                logger.error(f"Failed to download {path}: {e}")
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
        return responses

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await asyncio.to_thread(self.download_files, paths)
