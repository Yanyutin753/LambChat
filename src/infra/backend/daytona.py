"""Daytona 沙箱后端

自定义实现，替代 langchain_daytona.DaytonaSandbox。
使用 Daytona 原生 FS API 进行文件操作，避免通过 execute() 跑 python3 脚本。
支持客户端侧强制超时，通过 DAYTONA_TIMEOUT 配置（settings > 环境变量 > 默认值）。

注意：
- Daytona SDK process.exec() 的 timeout 仅作为命令参数发给服务端，不控制 HTTP 请求超时。
- aexecute() 使用 asyncio.wait_for 在客户端侧兜底，确保超时一定能生效。
- 所有同步 SDK 调用通过 run_blocking_io 在线程池中执行，避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import os
import shlex
import uuid

import daytona
from daytona import FileDownloadRequest, FileUpload
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    GrepResult,
)
from deepagents.backends.sandbox import BaseSandbox

from src.infra.async_utils import run_blocking_io
from src.infra.backend.protocol_compat import (
    FileInfo,
    GlobResult,
    classify_upload_error,
    file_download_response,
    file_upload_response,
)
from src.infra.logging import get_logger
from src.infra.sandbox_grep import (
    build_grep_command,
    get_sandbox_grep_timeout,
    parse_grep_response,
)
from src.kernel.config import settings

logger = get_logger(__name__)

# 默认超时 30 分钟（秒）
_DEFAULT_TIMEOUT = 30 * 60

# 中文路径临时文件目录
_TEMP_DIR = "/tmp/__daytona_transfer__"
SANDBOX_DOWNLOAD_MAX_BYTES = 50 * 1024 * 1024
SANDBOX_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
SANDBOX_BATCH_FILES_LIMIT = 100
SANDBOX_GLOB_MAX_MATCHES = 1000
SANDBOX_GLOB_TIMEOUT_SECONDS = 15


def _needs_ascii_bridge(path: str) -> bool:
    """判断路径是否包含非 ASCII 字符，需要通过 ASCII 临时路径桥接。"""
    try:
        path.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def _temp_path(original: str) -> str:
    """为原始路径生成一个唯一的 ASCII 临时路径。"""
    return f"{_TEMP_DIR}/{uuid.uuid4().hex}"


class DaytonaBackend(BaseSandbox):
    """Daytona 沙箱后端

    仅 execute() 走 shell 命令，使用 Daytona 服务端超时。
    所有同步 SDK 调用通过 run_blocking_io 在线程池中执行，避免阻塞事件循环。
    """

    def __init__(
        self,
        sandbox: daytona.Sandbox,
        timeout: int | None = None,
        env_vars: dict[str, str] | None = None,
        work_dir: str | None = None,
    ):
        self._sandbox = sandbox
        self.env_vars = env_vars or {}
        self._work_dir_override = work_dir
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
        """获取沙箱工作目录（同步，仅在初始化时调用一次）"""
        if self._work_dir_override:
            return self._work_dir_override
        if not hasattr(self, "_work_dir"):
            self._work_dir = self._sandbox.get_work_dir()
        return self._work_dir

    def _with_work_dir(self, command: str) -> str:
        if command.lstrip().startswith("cd "):
            return command
        quoted_work_dir = shlex.quote(self.work_dir)
        return f"mkdir -p {quoted_work_dir} && cd {quoted_work_dir} && {command}"

    def _ensure_parent_dir(self, file_path: str) -> None:
        """Ensure the parent directory exists before uploading a file."""
        parent = os.path.dirname(file_path)
        if not parent:
            return
        self.execute(f"mkdir -p {shlex.quote(parent)}")

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        effective_timeout = min(timeout or self._timeout, self._timeout)

        try:
            kwargs: dict = {"timeout": effective_timeout}
            if self.env_vars:
                kwargs["env"] = self.env_vars
            result = self._sandbox.process.exec(self._with_work_dir(command), **kwargs)
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

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """异步执行命令（通过线程池 + asyncio.wait_for 超时保护）

        SDK 的 process.exec() 只把 timeout 作为命令参数发给服务端，但没有设置 HTTP
        请求级别的超时。当服务端未正确处理 timeout 时，客户端会无限等待。
        这里用 asyncio.wait_for 在客户端侧兜底，确保超时一定能生效。
        """
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

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        """Search file contents with a shorter default timeout than generic execute()."""
        timeout = get_sandbox_grep_timeout(settings)
        result = self.execute(build_grep_command(pattern, path, glob), timeout=timeout)
        parsed = parse_grep_response(result, timeout)
        if isinstance(parsed, str):
            return GrepResult(error=parsed)
        truncated = max_count is not None and len(parsed) > max_count
        matches = parsed[:max_count] if max_count is not None else parsed
        return GrepResult(matches=matches, truncated=truncated)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        """Async grep variant with client-side timeout protection."""
        timeout = get_sandbox_grep_timeout(settings)
        result = await self.aexecute(build_grep_command(pattern, path, glob), timeout=timeout)
        parsed = parse_grep_response(result, timeout)
        if isinstance(parsed, str):
            return GrepResult(error=parsed)
        truncated = max_count is not None and len(parsed) > max_count
        matches = parsed[:max_count] if max_count is not None else parsed
        return GrepResult(matches=matches, truncated=truncated)

    def _glob_via_command(self, pattern: str, search_path: str) -> GlobResult | None:
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
        return GlobResult(
            matches=matches,
            truncated=len(matches) >= SANDBOX_GLOB_MAX_MATCHES,
        )

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        requested_path = path or "/"
        search_path = self.work_dir if requested_path == "/" else requested_path
        command_result = self._glob_via_command(pattern, search_path)
        if command_result is not None:
            return command_result
        return BaseSandbox.glob(self, pattern, requested_path)

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        return await run_blocking_io(self.glob, pattern, path)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from the sandbox.

        对含中文的路径：先用 shell cp 到 ASCII 临时路径，通过 SDK 下载，再 rm 临时文件。
        纯 ASCII 路径直接走 SDK，不做任何额外处理。
        """
        if len(paths) > SANDBOX_BATCH_FILES_LIMIT:
            return [
                file_download_response(path=path, content=None, error="too_many_files")
                for path in paths
            ]

        oversized_paths = set()
        for path in paths:
            if not path.startswith("/"):
                continue
            size = self._file_size(path)
            if size is not None and size > SANDBOX_DOWNLOAD_MAX_BYTES:
                oversized_paths.add(path)
                logger.warning(
                    "Skipping Daytona download for large file %s: %s bytes > %s",
                    path,
                    size,
                    SANDBOX_DOWNLOAD_MAX_BYTES,
                )

        # 原始路径 -> 临时路径的映射（仅中文路径）
        bridge_map: dict[str, str] = {}
        # 最终传给 SDK 的路径（中文路径已被替换为临时路径）
        sdk_path_map: dict[str, str] = {}  # 原始路径 -> SDK 实际使用的路径

        for path in paths:
            if not path.startswith("/") or path in oversized_paths:
                continue
            if _needs_ascii_bridge(path):
                tmp = _temp_path(path)
                bridge_map[path] = tmp
                sdk_path_map[path] = tmp
            else:
                sdk_path_map[path] = path

        # 对中文路径，在沙箱内 cp 到临时位置
        copy_errors: set[str] = set()
        for original, tmp in bridge_map.items():
            result = self.execute(f'mkdir -p "{_TEMP_DIR}" && cp "{original}" "{tmp}"')
            if result.exit_code != 0:
                copy_errors.add(original)
                logger.error(f"Failed to copy {original} -> {tmp}: {result.output}")

        # 构建 SDK 下载请求
        download_requests: list[FileDownloadRequest] = []
        valid_paths: list[str] = []  # 没有在 cp 阶段失败的路径
        for path in paths:
            if not path.startswith("/") or path in copy_errors or path in oversized_paths:
                continue
            sdk_path = sdk_path_map[path]
            download_requests.append(FileDownloadRequest(source=sdk_path))
            valid_paths.append(path)

        # SDK 返回结果，key 是 SDK 使用的路径
        sdk_results: dict[str, FileDownloadResponse] = {}
        if download_requests:
            try:
                daytona_responses = self._sandbox.fs.download_files(download_requests)
                for resp in daytona_responses:
                    content = resp.result
                    if content is None:
                        sdk_results[resp.source] = FileDownloadResponse(
                            path=resp.source, content=None, error="file_not_found"
                        )
                    else:
                        content_bytes = content.encode() if isinstance(content, str) else content
                        sdk_results[resp.source] = FileDownloadResponse(
                            path=resp.source, content=content_bytes, error=None
                        )
            except Exception as e:
                logger.error(f"Daytona fs.download_files failed: {e}")
                for path in valid_paths:
                    sdk_path = sdk_path_map[path]
                    sdk_results[sdk_path] = FileDownloadResponse(
                        path=sdk_path, content=None, error="file_not_found"
                    )

        # 清理临时文件
        for tmp in bridge_map.values():
            self.execute(f'rm -f "{tmp}"')

        # 组装最终结果，还原原始中文路径
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            if path in oversized_paths:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
                continue
            if path in copy_errors:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
                continue
            sdk_path = sdk_path_map[path]
            cached_resp: FileDownloadResponse | None = sdk_results.get(sdk_path)
            if cached_resp is None:
                cached_resp = FileDownloadResponse(path=path, content=None, error="file_not_found")
            # cached_resp.error 已经是正确的类型，直接使用
            responses.append(
                FileDownloadResponse(
                    path=path,
                    content=cached_resp.content,
                    error=cached_resp.error,
                )
            )

        return responses

    def _file_size(self, path: str) -> int | None:
        result = self.execute(f"stat -c %s {shlex.quote(path)}", timeout=30)
        if result.exit_code != 0:
            return None
        try:
            return int(str(result.output).strip().splitlines()[0])
        except (IndexError, ValueError):
            return None

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """异步下载文件（通过线程池，避免阻塞事件循环）"""
        return await run_blocking_io(self.download_files, paths)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files into the sandbox.

        对含中文的路径：先通过 SDK 上传到 ASCII 临时路径，再用 shell mv 到中文路径。
        纯 ASCII 路径直接走 SDK，不做任何额外处理。
        """
        if len(files) > SANDBOX_BATCH_FILES_LIMIT:
            return [
                file_upload_response(path=path, error="too_many_files") for path, _content in files
            ]

        oversized_paths = {
            path
            for path, content in files
            if path.startswith("/") and len(content) > SANDBOX_UPLOAD_MAX_BYTES
        }

        for path, _content in files:
            if path.startswith("/") and path not in oversized_paths:
                self._ensure_parent_dir(path)

        # 原始路径 -> 临时路径的映射（仅中文路径）
        bridge_map: dict[str, str] = {}
        # 最终传给 SDK 的请求
        upload_requests: list[FileUpload] = []
        # 请求对应的原始路径
        request_original_paths: list[str] = []

        for path, content in files:
            if not path.startswith("/"):
                continue
            if path in oversized_paths:
                continue
            if _needs_ascii_bridge(path):
                tmp = _temp_path(path)
                bridge_map[path] = tmp
                upload_requests.append(FileUpload(source=content, destination=tmp))
            else:
                upload_requests.append(FileUpload(source=content, destination=path))
            request_original_paths.append(path)

        # 批量上传
        upload_errors: dict[str, str] = {}
        if upload_requests:
            try:
                self._sandbox.fs.upload_files(upload_requests)
            except Exception as e:
                logger.error(f"Daytona fs.upload_files failed: {e}")
                for orig_path in request_original_paths:
                    upload_errors[orig_path] = str(e)

        # 对中文路径执行 mv 还原
        rename_errors: dict[str, str] = {}
        for original, tmp in bridge_map.items():
            if original in upload_errors:
                # 上传失败，清理临时文件
                self.execute(f'rm -f "{tmp}"')
                continue
            # 确保父目录存在
            parent = os.path.dirname(original)
            result = self.execute(
                f"mkdir -p {shlex.quote(parent)} && mv {shlex.quote(tmp)} {shlex.quote(original)}"
            )
            if result.exit_code != 0:
                rename_errors[original] = f"rename failed: {result.output}"
                logger.warning(f"Failed to rename {tmp} -> {original}: {result.output}")
                # mv 失败，清理残留的临时文件
                self.execute(f'rm -f "{tmp}"')

        # 组装结果
        responses: list[FileUploadResponse] = []
        for path, _content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            if path in oversized_paths:
                responses.append(file_upload_response(path=path, error="file_too_large"))
                continue
            error_str = upload_errors.get(path) or rename_errors.get(path)
            final_error = classify_upload_error(error_str) if error_str else None
            responses.append(FileUploadResponse(path=path, error=final_error))

        return responses

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """异步上传文件（通过线程池，避免阻塞事件循环）"""
        return await run_blocking_io(self.upload_files, files)
