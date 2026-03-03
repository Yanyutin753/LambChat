"""Daytona 沙箱后端

自定义实现，替代 langchain_daytona.DaytonaSandbox。
使用 Daytona 原生 FS API 进行文件操作，避免通过 execute() 跑 python3 脚本。
支持客户端侧强制超时，通过 DAYTONA_TIMEOUT 配置（settings > 环境变量 > 默认值）。
"""

import asyncio
import concurrent.futures
import logging
import os

import daytona
from daytona import FileDownloadRequest, FileUpload
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from deepagents.backends.sandbox import BaseSandbox

from src.kernel.config import settings

logger = logging.getLogger(__name__)

# 默认超时 30 分钟（秒）
_DEFAULT_TIMEOUT = 30 * 60


class DaytonaBackend(BaseSandbox):
    """Daytona 沙箱后端

    仅 execute() 走 shell 命令。客户端侧强制超时。
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
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    @property
    def id(self) -> str:
        return self._sandbox.id

    @property
    def work_dir(self) -> str:
        """获取沙箱工作目录"""
        if not hasattr(self, "_work_dir"):
            self._work_dir = self._sandbox.get_work_dir()
        return self._work_dir

    # ── execute (shell) ──────────────────────────────────────────────

    # 重试配置
    _EXECUTE_MAX_RETRIES = 3
    _EXECUTE_RETRY_DELAY = 2.0  # 秒

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        t = timeout if timeout is not None else self._timeout
        last_error = None

        for attempt in range(self._EXECUTE_MAX_RETRIES):
            try:

                def _run():
                    result = self._sandbox.process.exec(command, timeout=t)
                    return ExecuteResponse(output=result.result, exit_code=result.exit_code)

                future = self._pool.submit(_run)
                try:
                    return future.result(timeout=t)
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    return ExecuteResponse(output=f"Command timed out after {t}s", exit_code=124)
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # 检查是否是可重试的网络错误
                is_retryable = any(
                    pattern in error_str
                    for pattern in [
                        "remote end closed",
                        "connection reset",
                        "connection aborted",
                        "broken pipe",
                        "timed out",
                        "temporary failure",
                        "network is unreachable",
                    ]
                )

                if is_retryable and attempt < self._EXECUTE_MAX_RETRIES - 1:
                    logger.warning(
                        f"Execute command failed (attempt {attempt + 1}/{self._EXECUTE_MAX_RETRIES}): {e}. "
                        f"Retrying in {self._EXECUTE_RETRY_DELAY}s..."
                    )
                    import time

                    time.sleep(self._EXECUTE_RETRY_DELAY)
                    continue

                # 不可重试的错误，直接抛出
                raise

        # 如果所有重试都失败，返回错误响应
        return ExecuteResponse(
            output=f"Command execution failed after {self._EXECUTE_MAX_RETRIES} retries: {last_error}",
            exit_code=1,
        )

    # ── grep / glob / ls ─────────────────────────────────────────────

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """使用 Daytona FS find_files 搜索文件内容"""
        search_path = path or "."
        try:
            matches = self._sandbox.fs.find_files(search_path, pattern)
        except Exception as e:
            logger.warning("find_files failed: %s", e)
            return []

        results: list[GrepMatch] = []
        for m in matches:
            file_path = getattr(m, "file", "")
            # 如果指定了 glob 过滤，跳过不匹配的文件
            if glob and not self._match_glob(file_path, glob):
                continue
            results.append(
                {
                    "path": file_path,
                    "line": getattr(m, "line", 0),
                    "text": getattr(m, "content", ""),
                }
            )
        return results

    @staticmethod
    def _match_glob(file_path: str, pattern: str) -> bool:
        """简单 glob 匹配（支持 *.ext 格式）"""
        import fnmatch

        return fnmatch.fnmatch(os.path.basename(file_path), pattern)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """使用 Daytona FS search_files 搜索文件名"""
        try:
            result = self._sandbox.fs.search_files(path, pattern)
            # 安全获取 files 列表，处理 None 情况
            files = getattr(result, "files", None)
            if files is None:
                files = []
        except Exception as e:
            # Daytona API sometimes returns None for files instead of [], causing validation error
            # This is expected when no matches are found, so log at DEBUG level
            logger.debug("search_files failed (returning empty list): %s", e)
            return []

        return [{"path": f, "is_dir": f.endswith("/")} for f in files]

    # ── upload / download (binary) ───────────────────────────────────
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
                # Ensure content is bytes
                content_bytes: bytes = content.encode() if isinstance(content, str) else content
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

    # ── write (create new file) ───────────────────────────────────────

    def write(self, file_path: str, content: str) -> WriteResult:
        """Write content to a new file in the filesystem, error if file exists.

        Args:
            file_path: Absolute path where the file should be created. Must start with '/'.
            content: String content to write to the file.

        Returns:
            WriteResult
        """
        # Validate path
        if not file_path.startswith("/"):
            return WriteResult(error="invalid_path: path must start with '/'")

        try:
            # Check if file already exists
            existing = self._sandbox.fs.find_files(
                os.path.dirname(file_path) or "/", os.path.basename(file_path)
            )
            if existing:
                return WriteResult(error=f"File '{file_path}' already exists")

            # Upload the new file
            upload_request = FileUpload(source=content.encode("utf-8"), destination=file_path)
            self._sandbox.fs.upload_files([upload_request])

            return WriteResult(path=file_path, files_update=None)

        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return WriteResult(error=str(e))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        """Async version of write."""
        return await asyncio.to_thread(self.write, file_path, content)
