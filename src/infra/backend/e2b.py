"""E2B 沙箱后端

使用 E2B Python SDK 提供沙箱命令执行和文件操作。
支持 Firecracker microVM 隔离，~150ms 冷启动。

特性：
- 原生 Filesystem API：ls / read / write / glob 直接走 E2B SDK，不经过 shell
- Auto-Pause + Auto-Resume：超时自动暂停（保留状态），下次操作自动恢复
- Commands streaming：支持 on_stdout/on_stderr 回调实时输出
- Metadata 标记：创建沙箱时传入 user_id 用于可观测性
- 所有同步 SDK 调用通过 asyncio.to_thread 在线程池中执行，避免阻塞事件循环。
"""

import asyncio
import os
import shlex
from typing import TYPE_CHECKING, Any, Callable, Literal

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.backends.sandbox import BaseSandbox

from src.infra.logging import get_logger
from src.kernel.config import settings

if TYPE_CHECKING:
    from e2b import Sandbox as E2BSandbox

logger = get_logger(__name__)

# 默认超时 30 分钟（秒）
_DEFAULT_TIMEOUT = 30 * 60


class E2BBackend(BaseSandbox):
    """E2B 沙箱后端

    使用 e2b Python SDK 执行命令和操作文件。
    所有同步 SDK 调用通过 asyncio.to_thread 在线程池中执行，避免阻塞事件循环。

    文件操作 (ls, read, write, glob) 使用 E2B 原生 Filesystem API，
    绕过 shell 命令，性能更好且更安全。
    """

    def __init__(
        self,
        sandbox: "E2BSandbox",
        timeout: int | None = None,
        env_vars: dict[str, str] | None = None,
    ):
        self._sandbox = sandbox
        self.env_vars = env_vars or {}
        self._timeout = (
            timeout or settings.E2B_TIMEOUT or int(os.environ.get("E2B_TIMEOUT", _DEFAULT_TIMEOUT))
        )

    @property
    def id(self) -> str:
        return self._sandbox.sandbox_id

    @property
    def work_dir(self) -> str:
        return "/home/user"

    def _ensure_parent_dir(self, file_path: str) -> None:
        """Ensure the parent directory exists before writing a file."""
        parent = os.path.dirname(file_path)
        if not parent:
            return
        self.execute(f"mkdir -p {shlex.quote(parent)}")

    # =========================================================================
    # Command execution
    # =========================================================================

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        effective_timeout = min(timeout or self._timeout, self._timeout)

        try:
            kwargs: dict = {"cmd": command, "timeout": effective_timeout}
            if self.env_vars:
                kwargs["envs"] = self.env_vars
            result = self._sandbox.commands.run(**kwargs)
            output = result.stdout or ""
            if result.stderr:
                output = f"{output}\n{result.stderr}" if output else result.stderr
            return ExecuteResponse(
                output=output,
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

    def execute_with_callbacks(
        self,
        command: str,
        *,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """执行命令并实时流式输出 stdout/stderr

        Args:
            command: 要执行的命令
            on_stdout: stdout 行回调
            on_stderr: stderr 行回调
            timeout: 命令超时（秒）

        Returns:
            ExecuteResponse（包含完整输出）
        """
        effective_timeout = min(timeout or self._timeout, self._timeout)
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        def _on_stdout(line: str) -> None:
            stdout_parts.append(line)
            if on_stdout:
                on_stdout(line)

        def _on_stderr(line: str) -> None:
            stderr_parts.append(line)
            if on_stderr:
                on_stderr(line)

        try:
            kwargs: dict = {
                "cmd": command,
                "timeout": effective_timeout,
                "on_stdout": _on_stdout,
                "on_stderr": _on_stderr,
            }
            if self.env_vars:
                kwargs["envs"] = self.env_vars
            result = self._sandbox.commands.run(**kwargs)
            output = "\n".join(stdout_parts)
            if stderr_parts:
                output = (
                    f"{output}\n{chr(10).join(stderr_parts)}" if output else "\n".join(stderr_parts)
                )
            return ExecuteResponse(
                output=output,
                exit_code=result.exit_code,
                truncated=False,
            )
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return ExecuteResponse(
                    output=f"Command timed out after {effective_timeout} seconds",
                    exit_code=-1,
                    truncated=False,
                )
            return ExecuteResponse(
                output=f"Command failed: {e}",
                exit_code=-1,
                truncated=False,
            )

    # =========================================================================
    # Native Filesystem API (override BaseSandbox shell-based defaults)
    # =========================================================================

    def _is_entry_dir(self, entry: Any) -> bool:
        """判断 E2B 文件条目是否为目录（兼容 type 和 is_dir 两种 API）"""
        from e2b import FileType

        if hasattr(entry, "type") and entry.type == FileType.DIR:
            return True
        if hasattr(entry, "is_dir") and entry.is_dir:
            return True
        return False

    def ls(self, path: str) -> LsResult:
        """使用 E2B 原生 files.list() 列出目录"""
        try:
            entries = self._sandbox.files.list(path=path)
            result: list[FileInfo] = []
            for entry in entries:
                info: FileInfo = {"path": entry.path}
                if self._is_entry_dir(entry):
                    info["is_dir"] = True
                if hasattr(entry, "size"):
                    info["size"] = entry.size
                result.append(info)
            return LsResult(entries=result)
        except Exception as e:
            logger.warning(f"E2B files.list({path}) failed: {e}, falling back to execute()")
            return super().ls(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """使用 E2B 原生 files.read() 读取文件，middleware 负责行号格式化和截断"""
        try:
            content = self._sandbox.files.read(path=file_path, format="text")
            if offset > 0:
                lines = content.split("\n")
                content = "\n".join(lines[offset:])
            return ReadResult(file_data={"content": content, "encoding": "utf-8"})
        except Exception as e:
            logger.warning(f"E2B files.read({file_path}) failed: {e}, falling back to execute()")
            return super().read(file_path, offset, limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        """使用 E2B 原生 files.write() 写入文件"""
        try:
            self._ensure_parent_dir(file_path)
            self._sandbox.files.write(path=file_path, data=content)
            return WriteResult(path=file_path)
        except Exception as e:
            error_msg = str(e).lower()
            error: str | None = None
            if "permission" in error_msg:
                error = "permission_denied"
            elif "directory" in error_msg:
                error = "is_directory"
            else:
                error = "file_not_found"
            logger.error(f"E2B files.write({file_path}) failed: {e}")
            return WriteResult(path=file_path, error=error)

    def glob(self, pattern: str, path: str = "/", *, _max_depth: int = 10) -> GlobResult:
        """使用 E2B 原生 files.list() 递归搜索匹配 glob 模式的文件

        E2B 没有 glob API，所以用 list 递归列出后在 Python 端过滤。
        使用 _max_depth 限制递归深度，防止深层目录结构导致长时间阻塞。
        """
        try:
            import fnmatch

            entries = self._sandbox.files.list(path=path)
            result: list[FileInfo] = []

            def _match_glob(entries_list: list[Any], current_path: str, depth: int) -> None:
                if depth > _max_depth:
                    logger.warning(f"E2B glob reached max depth {_max_depth} at {current_path}")
                    return
                for entry in entries_list:
                    full_path = entry.path
                    name = os.path.basename(full_path)
                    is_dir = self._is_entry_dir(entry)
                    if fnmatch.fnmatch(name, pattern):
                        info: FileInfo = {"path": full_path}
                        if is_dir:
                            info["is_dir"] = True
                        if hasattr(entry, "size"):
                            info["size"] = entry.size
                        result.append(info)
                    if is_dir:
                        try:
                            sub_entries = self._sandbox.files.list(path=full_path)
                            _match_glob(sub_entries, full_path, depth + 1)
                        except Exception:
                            pass

            _match_glob(entries, path, 0)
            return GlobResult(matches=result)
        except Exception as e:
            logger.warning(f"E2B glob({pattern}) failed: {e}, falling back to execute()")
            return super().glob(pattern, path)

    # =========================================================================
    # File upload / download (already native, no change needed to logic)
    # =========================================================================

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            try:
                self._ensure_parent_dir(path)
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

    # =========================================================================
    # Sandbox lifecycle helpers
    # =========================================================================

    def get_info(self) -> dict[str, Any]:
        """获取沙箱信息 (sandbox_id, state, template, metadata, started_at, end_at)"""
        try:
            info = self._sandbox.get_info()
            return {
                "sandbox_id": info.sandbox_id,
                "state": info.state.name.lower()
                if hasattr(info.state, "name")
                else str(info.state),
                "template": info.template_id,
                "metadata": info.metadata,
                "started_at": info.started_at.isoformat() if info.started_at else None,
                "end_at": info.end_at.isoformat() if info.end_at else None,
            }
        except Exception as e:
            logger.warning(f"Failed to get sandbox info: {e}")
            return {"sandbox_id": self.id, "state": "unknown"}

    def get_metrics(self) -> list[dict[str, Any]]:
        """获取沙箱资源使用指标 (CPU, memory, disk)"""
        try:
            metrics = self._sandbox.get_metrics()
            return [
                {
                    "timestamp": m.timestamp.isoformat()
                    if hasattr(m, "timestamp") and m.timestamp
                    else None,
                    "cpu_percent": getattr(m, "cpu_percent", None),
                    "memory_usage_bytes": getattr(m, "memory_usage_bytes", None),
                    "disk_usage_bytes": getattr(m, "disk_usage_bytes", None),
                }
                for m in metrics
            ]
        except Exception as e:
            logger.warning(f"Failed to get sandbox metrics: {e}")
            return []

    def snapshot(self) -> str:
        """创建沙箱快照（保留文件系统和内存状态）

        Returns:
            snapshot_id
        """
        result = self._sandbox.snapshot()
        return result.snapshot_id

    def pause(self) -> None:
        """暂停沙箱（保留文件系统和内存状态，可随时恢复）"""
        self._sandbox.pause()
        logger.info(f"[E2B] Paused sandbox {self.id}")
