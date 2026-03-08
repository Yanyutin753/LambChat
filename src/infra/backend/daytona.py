"""Daytona 沙箱后端

自定义实现，替代 langchain_daytona.DaytonaSandbox。
使用 Daytona 原生 FS API 进行文件操作，避免通过 execute() 跑 python3 脚本。
支持客户端侧强制超时，通过 DAYTONA_TIMEOUT 配置（settings > 环境变量 > 默认值）。
"""

import logging
import os

import daytona
from daytona import FileDownloadRequest, FileUpload
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

from src.kernel.config import settings

logger = logging.getLogger(__name__)

# 默认超时 30 分钟（秒）
_DEFAULT_TIMEOUT = 30 * 60


class DaytonaBackend(BaseSandbox):
    """Daytona 沙箱后端

    仅 execute() 走 shell 命令，使用 Daytona 服务端超时。
    """

    def __init__(
        self,
        sandbox: daytona.Sandbox,
        timeout: int | None = None,
    ):
        self._sandbox = sandbox
        # 优先级：参数 > settings > 环境变量 > 默认值
        self._timeout = (
            timeout
            or settings.DAYTONA_TIMEOUT
            or int(os.environ.get("DAYTONA_TIMEOUT", _DEFAULT_TIMEOUT))
        )

    @property
    def id(self) -> str:
        return self._sandbox.id

    @property
    def work_dir(self) -> str:
        """获取沙箱工作目录"""
        if not hasattr(self, "_work_dir"):
            self._work_dir = self._sandbox.get_work_dir()
        return self._work_dir

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        effective_timeout = min(timeout or self._timeout, self._timeout)

        try:
            result = self._sandbox.process.exec(command, timeout=effective_timeout)
            return ExecuteResponse(
                output=result.result,
                exit_code=result.exit_code,
                truncated=False,
            )
        except Exception as e:
            # Daytona SDK 异常类型未公开，使用通用异常处理
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

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from the sandbox."""
        download_requests: list[FileDownloadRequest] = []
        responses: list[FileDownloadResponse] = []

        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            download_requests.append(FileDownloadRequest(source=path))
            responses.append(FileDownloadResponse(path=path, content=None, error=None))

        if not download_requests:
            return responses

        daytona_responses = self._sandbox.fs.download_files(download_requests)

        mapped_responses: list[FileDownloadResponse] = []
        for resp in daytona_responses:
            content = resp.result
            if content is None:
                mapped_responses.append(
                    FileDownloadResponse(
                        path=resp.source,
                        content=None,
                        error="file_not_found",
                    )
                )
            else:
                # Ensure content is bytes (Daytona SDK may return str | bytes)
                content_bytes = content.encode() if isinstance(content, str) else content
                mapped_responses.append(
                    FileDownloadResponse(
                        path=resp.source,
                        content=content_bytes,
                        error=None,
                    )
                )

        mapped_iter = iter(mapped_responses)
        for i, path in enumerate(paths):
            if not path.startswith("/"):
                continue
            responses[i] = next(
                mapped_iter,
                FileDownloadResponse(path=path, content=None, error="file_not_found"),
            )

        return responses

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files into the sandbox."""
        upload_requests: list[FileUpload] = []
        responses: list[FileUploadResponse] = []

        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            upload_requests.append(FileUpload(source=content, destination=path))
            responses.append(FileUploadResponse(path=path, error=None))

        if upload_requests:
            self._sandbox.fs.upload_files(upload_requests)

        return responses
