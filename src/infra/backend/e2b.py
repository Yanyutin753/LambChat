"""E2B 沙箱后端

使用 E2B Python SDK 提供沙箱命令执行和文件操作。
支持 Firecracker microVM 隔离，~150ms 冷启动。

特性：
- 原生 Filesystem API：ls / read / write / glob 直接走 E2B SDK，不经过 shell
- Auto-Pause + Auto-Resume：超时自动暂停（保留状态），下次操作自动恢复
- Commands streaming：支持 on_stdout/on_stderr 回调实时输出
- Metadata 标记：创建沙箱时传入 user_id 用于可观测性
- 所有同步 SDK 调用通过 run_blocking_io 在线程池中执行，避免阻塞事件循环。
"""

import asyncio
import base64
import os
import shlex
from typing import TYPE_CHECKING, Any, Callable, Literal, cast

from deepagents.backends.sandbox import BaseSandbox
from deepagents.backends.utils import (
    create_file_data,
    format_content_with_line_numbers,
)

from src.infra.async_utils import run_blocking_io
from src.infra.backend.protocol_compat import (
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    LsResult,
    ReadResult,
    WriteResult,
    file_download_response,
    file_upload_response,
    is_read_result,
    read_result_to_string,
)
from src.infra.logging import get_logger
from src.infra.sandbox_grep import (
    build_grep_command,
    get_sandbox_grep_timeout,
    parse_grep_response,
)
from src.kernel.config import settings

if TYPE_CHECKING:
    from e2b import Sandbox as E2BSandbox

logger = get_logger(__name__)

# 默认超时 30 分钟（秒）
_DEFAULT_TIMEOUT = 30 * 60
SANDBOX_READ_MAX_BYTES = 2 * 1024 * 1024
SANDBOX_DOWNLOAD_MAX_BYTES = 50 * 1024 * 1024
SANDBOX_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
SANDBOX_BATCH_FILES_LIMIT = 100
SANDBOX_GLOB_MAX_MATCHES = 1000
SANDBOX_GLOB_TIMEOUT_SECONDS = 15


def _slice_file_data(content: str, offset: int, limit: int):
    try:
        from deepagents.backends.utils import slice_read_response

        return slice_read_response(create_file_data(content), offset, limit)
    except ImportError:
        lines = content.splitlines(keepends=True)
        if offset >= len(lines):
            return ReadResult(
                error=f"Line offset {offset} exceeds file length ({len(lines)} lines)"
            )
        return "".join(lines[offset : offset + limit]) if limit >= 0 else "".join(lines[offset:])


def _slice_text_read(content: str, offset: int, limit: int) -> str | ReadResult:
    if not content:
        return ""
    sliced = _slice_file_data(content, offset, limit)
    if is_read_result(sliced):
        error = getattr(sliced, "error", None)
        return ReadResult(error=str(error) if error is not None else read_result_to_string(sliced))
    return format_content_with_line_numbers(sliced, start_line=offset + 1)  # type: ignore[arg-type]


def _slice_text_content(content: str, offset: int, limit: int) -> str | ReadResult:
    if not content:
        return ""
    sliced = _slice_file_data(content, offset, limit)
    if is_read_result(sliced):
        error = getattr(sliced, "error", None)
        return ReadResult(error=str(error) if error is not None else read_result_to_string(sliced))
    return cast(str, sliced)


class E2BBackend(BaseSandbox):
    """E2B 沙箱后端

    使用 e2b Python SDK 执行命令和操作文件。
    所有同步 SDK 调用通过 run_blocking_io 在线程池中执行，避免阻塞事件循环。

    文件操作 (ls, read, write, glob) 使用 E2B 原生 Filesystem API，
    绕过 shell 命令，性能更好且更安全。
    """

    def __init__(
        self,
        sandbox: "E2BSandbox",
        timeout: int | None = None,
        env_vars: dict[str, str] | None = None,
        work_dir: str | None = None,
    ):
        self._sandbox = sandbox
        self.env_vars = env_vars or {}
        self._work_dir = work_dir or "/home/user"
        self._timeout = (
            timeout or settings.E2B_TIMEOUT or int(os.environ.get("E2B_TIMEOUT", _DEFAULT_TIMEOUT))
        )

    @property
    def id(self) -> str:
        return self._sandbox.sandbox_id

    @property
    def work_dir(self) -> str:
        return self._work_dir

    def _with_work_dir(self, command: str) -> str:
        if command.lstrip().startswith("cd "):
            return command
        quoted_work_dir = shlex.quote(self.work_dir)
        return f"mkdir -p {quoted_work_dir} && cd {quoted_work_dir} && {command}"

    def _resolve_path(self, path: str) -> str:
        if path == "/":
            return self.work_dir
        if path.startswith("/"):
            return path
        return f"{self.work_dir.rstrip('/')}/{path}"

    def _ensure_parent_dir(self, file_path: str) -> None:
        """Ensure the parent directory exists before writing a file."""
        file_path = self._resolve_path(file_path)
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
            kwargs: dict = {"cmd": self._with_work_dir(command), "timeout": effective_timeout}
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
            return await run_blocking_io(
                lambda: self.execute(command, timeout=timeout),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Client-side timeout after {effective_timeout}s: {command[:100]}...")
            return ExecuteResponse(
                output=f"Command timed out after {effective_timeout} seconds",
                exit_code=-1,
                truncated=False,
            )

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Search file contents with a shorter default timeout than generic execute()."""
        timeout = get_sandbox_grep_timeout(settings)
        result = self.execute(build_grep_command(pattern, path, glob), timeout=timeout)
        return parse_grep_response(result, timeout)

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Async grep variant that preserves backend-specific timeout handling."""
        timeout = get_sandbox_grep_timeout(settings)
        result = await self.aexecute(build_grep_command(pattern, path, glob), timeout=timeout)
        return parse_grep_response(result, timeout)

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
                "cmd": self._with_work_dir(command),
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
        if hasattr(entry, "is_dir") and entry.is_dir:
            return True
        if hasattr(entry, "type"):
            try:
                from e2b import FileType

                if entry.type == FileType.DIR:
                    return True
            except Exception as e:
                logger.debug("E2B FileType 判定失败: %s", e)
        return False

    def ls_info(self, path: str) -> list[FileInfo]:
        """使用 E2B 原生 files.list() 列出目录"""
        path = self._resolve_path(path)
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
            return result
        except Exception as e:
            logger.warning(f"E2B files.list({path}) failed: {e}, falling back to execute()")
            # 直接调用 BaseSandbox.ls 避免 super().ls_info -> self.ls -> self.ls_info 的无限递归
            ls_result = BaseSandbox.ls(self, path)
            return ls_result.entries or []

    async def als_info(self, path: str) -> list[FileInfo]:
        return await run_blocking_io(self.ls_info, path)

    def ls(self, path: str) -> LsResult:
        return LsResult(entries=self.ls_info(path))

    async def als(self, path: str) -> LsResult:
        return LsResult(entries=await self.als_info(path))

    # magic bytes → MIME
    _MAGIC: list[tuple[bytes, str]] = [
        (b"\x89PNG", "image/png"),
        (b"\xff\xd8", "image/jpeg"),
        (b"GIF8", "image/gif"),
        (b"RIFFWEBP", "image/webp"),
        (b"%PDF-", "application/pdf"),
    ]

    @staticmethod
    def _guess_mime_type(path: str, data: bytes) -> str:
        """根据扩展名 + magic bytes 猜测 MIME 类型"""
        import mimetypes

        mime, _ = mimetypes.guess_type(path)
        if mime:
            return mime
        head = data[:12]
        for sig, mt in E2BBackend._MAGIC:
            if head.startswith(sig):
                return mt
        return "application/octet-stream"

    def _read_as_data_uri(self, file_path: str, raw: bytes) -> ReadResult:
        """将二进制数据包装为 data URI 返回"""
        mime = self._guess_mime_type(file_path, raw)
        data_uri = f"data:{mime};base64,{base64.standard_b64encode(raw).decode()}"
        return ReadResult(
            file_data={"content": data_uri, "encoding": "data_uri"},
            rendered_content=data_uri,
        )

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:  # type: ignore[override]
        """使用 E2B 原生 files.read() 读取文件，middleware 负责行号格式化和截断

        自动检测二进制文件，返回 data URI 而非裸 base64。
        """
        file_path = self._resolve_path(file_path)
        try:
            size = self._file_size(file_path)
            if size is not None and size > SANDBOX_READ_MAX_BYTES:
                return ReadResult(
                    error=(
                        f"file too large to read directly: {size} bytes "
                        f"(limit {SANDBOX_READ_MAX_BYTES} bytes)"
                    )
                )
            # 先尝试文本读取
            content = self._sandbox.files.read(path=file_path, format="text")

            # 二进制检测：null bytes 或高比例不可打印字符
            if "\x00" in content:
                raw = self._sandbox.files.read(path=file_path, format="bytes")
                return self._read_as_data_uri(file_path, bytes(raw))

            # 长文本且几乎全是 base64 字符 → 可能是裸 base64 的二进制文件
            stripped = content.strip()
            if len(stripped) >= 100:
                sample = stripped[:4096]
                non_text = sum(1 for c in sample if ord(c) < 32 and c not in "\t\n\r")
                if non_text / len(sample) > 0.3:
                    raw = self._sandbox.files.read(path=file_path, format="bytes")
                    return self._read_as_data_uri(file_path, bytes(raw))

            sliced_content = _slice_text_content(content, offset, limit)
            if is_read_result(sliced_content):
                return sliced_content  # type: ignore[return-value]
            rendered = _slice_text_read(content, offset, limit)
            if is_read_result(rendered):
                return rendered  # type: ignore[return-value]
            return ReadResult(
                file_data={"content": cast(str, sliced_content), "encoding": "utf-8"},
                rendered_content=cast(str, rendered),
            )
        except Exception as e:
            logger.warning(f"E2B files.read({file_path}) failed: {e}, falling back to execute()")
            return ReadResult(error=str(e))

    def write(self, file_path: str, content: str) -> WriteResult:
        """使用 E2B 原生 files.write() 写入文件"""
        file_path = self._resolve_path(file_path)
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

    def _glob_info_via_command(self, pattern: str, search_path: str) -> list[FileInfo] | None:
        """Prefer shell tools for glob search; return None when command search is unavailable."""
        quoted_path = shlex.quote(search_path)
        quoted_pattern = shlex.quote(pattern)
        max_matches = SANDBOX_GLOB_MAX_MATCHES
        command = (
            f"if command -v rg >/dev/null 2>&1; then "
            f"printf '__LAMBCHAT_GLOB_MODE__:rg\\n'; "
            f"rg --files --hidden --glob {quoted_pattern} {quoted_path} | head -n {max_matches}; "
            f"else "
            f"printf '__LAMBCHAT_GLOB_MODE__:find\\n'; "
            f"find {quoted_path} -xdev "
            f"\\( -path /proc -o -path /sys -o -path /dev \\) -prune -o "
            f"-print | head -n {max_matches * 5}; "
            f"fi"
        )
        response = self.execute(command, timeout=SANDBOX_GLOB_TIMEOUT_SECONDS)
        if response.exit_code != 0:
            return None

        import re

        # glob.translate() is Python 3.13+; this is the 3.12-compatible equivalent.
        parts = pattern.split("**")
        segments: list[str] = []
        for idx, part in enumerate(parts):
            if idx > 0:
                if part.startswith("/"):
                    segments.append("(?:|.*/)")
                    part = part[1:]
                else:
                    segments.append(".*")
            segments.append(re.escape(part).replace(r"\*", "[^/]*").replace(r"\?", "[^/]"))
        glob_regex = re.compile("^" + "".join(segments) + "$")

        def _matches_find_result(full_path: str) -> bool:
            relative_path = os.path.relpath(full_path, search_path)
            return glob_regex.match(relative_path) is not None

        matches: list[FileInfo] = []
        seen: set[str] = set()
        mode = "find"
        for raw_line in (response.output or "").splitlines():
            full_path = raw_line.strip()
            if full_path.startswith("__LAMBCHAT_GLOB_MODE__:"):
                mode = full_path.rsplit(":", 1)[-1]
                continue
            if not full_path or full_path in seen:
                continue
            if any(full_path.startswith(prefix) for prefix in ("/proc", "/sys", "/dev")):
                continue

            if mode != "rg":
                if not _matches_find_result(full_path):
                    continue

            seen.add(full_path)
            info: FileInfo = {"path": full_path}
            if full_path.endswith("/"):
                info["is_dir"] = True
            matches.append(info)
            if len(matches) >= SANDBOX_GLOB_MAX_MATCHES:
                break
        return matches

    def glob_info(self, pattern: str, path: str = "/", *, _max_depth: int = 10) -> list[FileInfo]:
        """优先使用 rg/find 搜索匹配 glob 模式的文件

        命令搜索通常比逐级调用 E2B files.list() 更快；命令不可用时 fallback 到原生 API。
        使用 _max_depth 和结果数限制，防止大目录导致长时间阻塞和内存增长。
        """
        try:
            import fnmatch

            search_path = self._resolve_path(path)
            command_matches = self._glob_info_via_command(pattern, search_path)
            if command_matches is not None:
                return command_matches

            entries = self._sandbox.files.list(path=search_path)
            result: list[FileInfo] = []

            visited: set[str] = set()
            _skip_prefixes = ("/proc", "/sys", "/dev")

            def _match_glob(entries_list: list[Any], current_path: str, depth: int) -> None:
                if len(result) >= SANDBOX_GLOB_MAX_MATCHES:
                    return
                if depth > _max_depth:
                    logger.warning(f"E2B glob reached max depth {_max_depth} at {current_path}")
                    return
                if current_path in visited:
                    return
                visited.add(current_path)
                for entry in entries_list:
                    full_path = entry.path
                    if any(full_path.startswith(p) for p in _skip_prefixes):
                        continue
                    name = os.path.basename(full_path)
                    is_dir = self._is_entry_dir(entry)
                    if is_dir and full_path != current_path and os.path.islink(full_path):
                        continue
                    if fnmatch.fnmatch(name, pattern):
                        info: FileInfo = {"path": full_path}
                        if is_dir:
                            info["is_dir"] = True
                        if hasattr(entry, "size"):
                            info["size"] = entry.size
                        result.append(info)
                        if len(result) >= SANDBOX_GLOB_MAX_MATCHES:
                            return
                    if is_dir:
                        try:
                            sub_entries = self._sandbox.files.list(path=full_path)
                            _match_glob(sub_entries, full_path, depth + 1)
                            if len(result) >= SANDBOX_GLOB_MAX_MATCHES:
                                return
                        except Exception as e:
                            logger.debug("E2B glob 递归遍历子目录失败 %s: %s", full_path, e)

            _match_glob(entries, search_path, 0)
            return result
        except Exception as e:
            logger.warning(f"E2B glob({pattern}) failed: {e}, falling back to execute()")
            return super().glob_info(pattern, path)

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return await run_blocking_io(self.glob_info, pattern, path)

    def glob(self, pattern: str, path: str | None = None, *, _max_depth: int = 10) -> GlobResult:
        return GlobResult(matches=self.glob_info(pattern, path or "/", _max_depth=_max_depth))

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        return GlobResult(matches=await self.aglob_info(pattern, path or "/"))

    # =========================================================================
    # File upload / download (already native, no change needed to logic)
    # =========================================================================

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        if len(files) > SANDBOX_BATCH_FILES_LIMIT:
            return [
                file_upload_response(path=path, error="too_many_files") for path, _content in files
            ]

        responses: list[FileUploadResponse] = []
        for path, content in files:
            path = self._resolve_path(path)
            if len(content) > SANDBOX_UPLOAD_MAX_BYTES:
                responses.append(file_upload_response(path=path, error="file_too_large"))
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
        return await run_blocking_io(self.upload_files, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        if len(paths) > SANDBOX_BATCH_FILES_LIMIT:
            return [
                file_download_response(path=path, content=None, error="too_many_files")
                for path in paths
            ]

        responses: list[FileDownloadResponse] = []
        for path in paths:
            path = self._resolve_path(path)
            try:
                size = self._file_size(path)
                if size is not None and size > SANDBOX_DOWNLOAD_MAX_BYTES:
                    logger.warning(
                        "Skipping E2B download for large file %s: %s bytes > %s",
                        path,
                        size,
                        SANDBOX_DOWNLOAD_MAX_BYTES,
                    )
                    responses.append(
                        FileDownloadResponse(path=path, content=None, error="file_not_found")
                    )
                    continue
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

    def _file_size(self, path: str) -> int | None:
        parent = os.path.dirname(path) or "/"
        try:
            entries = self._sandbox.files.list(path=parent)
        except Exception as e:
            logger.debug("E2B files.list(%s) size preflight failed: %s", parent, e)
            return None
        for entry in entries:
            if getattr(entry, "path", None) == path and hasattr(entry, "size"):
                try:
                    return int(entry.size)
                except (TypeError, ValueError):
                    return None
        return None

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await run_blocking_io(self.download_files, paths)

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
        result = self._sandbox.create_snapshot()
        return result.snapshot_id

    def pause(self) -> None:
        """暂停沙箱（保留文件系统和内存状态，可随时恢复）"""
        self._sandbox.pause()
        logger.info(f"[E2B] Paused sandbox {self.id}")
