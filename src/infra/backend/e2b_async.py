"""E2B 沙箱的 async 原生路径（零线程占用）。

命令与文件操作本质是 HTTP/WS 调用——同步 SDK 时代只能拿阻塞 IO 线程扛
整段时长；这里基于 e2b 官方 ``AsyncSandbox`` 客户端做纯 await 实现，
并发上限从线程数变成事件循环级。以 Mixin 形式并入 ``E2BBackend``。

语义与同步路径完全对齐：暂停/断连唤醒 + 单次重试（超时不重试防双执行）、
命令期间周期续期、大小上限、二进制检测、重建通知。客户端建不起来
（Cube 等平台不完全兼容 e2b 客户端时）自动回落线程慢道，不占快道。
"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from typing import TYPE_CHECKING, Any, Callable

from deepagents.backends.utils import create_file_data, slice_read_response

from src.infra.async_utils import run_long_blocking_io
from src.infra.backend.protocol_compat import (
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    LsResult,
    ReadResult,
    classify_upload_error,
    file_download_response,
    file_upload_response,
)
from src.infra.backend.sandbox_heal import SandboxHeal
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# 长命令期间续期的最小间隔（秒）；测试会改小。e2b.py 同步 keeper 从本模块
# 导入同一常量，两条路径共享节流语义。
_KEEPALIVE_MIN_INTERVAL = 30.0

# 单条命令的默认超时下限：沙箱 timeout（空闲回收节奏）调小不应钳住命令时长
_DEFAULT_COMMAND_TIMEOUT = 15 * 60

SANDBOX_READ_MAX_BYTES = 2 * 1024 * 1024
SANDBOX_DOWNLOAD_MAX_BYTES = 50 * 1024 * 1024
SANDBOX_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
SANDBOX_BATCH_FILES_LIMIT = 100


class _AsyncClientInitError(RuntimeError):
    """e2b async 客户端无法建立（平台不兼容/不可达），调用方回落线程路径。"""


class E2BAsyncMixin:
    """e2b 官方 async 客户端的命令与文件操作原生实现。

    宿主（E2BBackend）提供实例态与同步侧助手；本 Mixin 只做 async 原生
    路径与线程慢道回落，不触碰快道。
    """

    if TYPE_CHECKING:
        _timeout: int
        _heal: SandboxHeal
        env_vars: dict[str, str]
        supports_async_sdk: bool
        _async_client: Any
        _async_init_lock: asyncio.Lock
        _async_init_failures: int
        _async_disabled: bool
        _last_timeout_extend: float

        @property
        def id(self) -> str: ...

        def _with_work_dir(self, command: str) -> str: ...

        def _resolve_path(self, path: str) -> str: ...

        def _command_timeout(self, timeout: int | None) -> int: ...

        def _command_error_response(
            self, e: Exception, effective_timeout: int, command: str
        ) -> Any: ...

        def _read_as_base64(self, raw: bytes) -> ReadResult: ...

        def _is_entry_dir(self, entry: Any) -> bool: ...

        def _consume_startup_notice(self) -> str | None: ...

        def execute(self, command: str, *, timeout: int | None = None) -> Any: ...

        def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult: ...

        def ls(self, path: str) -> LsResult: ...

        def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]: ...

        def download_files(self, paths: list[str]) -> list[FileDownloadResponse]: ...

    async def _async_sandbox(self) -> Any:
        """懒连接 e2b 官方 async 客户端；connect 会自动恢复 paused 沙箱。"""
        if self._async_client is None:
            async with self._async_init_lock:
                if self._async_client is None:
                    from e2b import AsyncSandbox as AsyncE2BSandbox

                    self._async_client = await AsyncE2BSandbox.connect(
                        self.id, **self._async_connect_opts()
                    )
        return self._async_client

    def _async_connect_opts(self) -> dict:
        """e2b async 客户端连接参数；子类可覆写指向 e2b 兼容平台（如 Cube）。"""
        opts: dict = {
            "timeout": self._timeout,
            "api_key": settings.E2B_API_KEY or None,
            "domain": os.environ.get("E2B_DOMAIN") or "e2b.app",
            "request_timeout": float(os.environ.get("E2B_REQUEST_TIMEOUT", "120")),
        }
        api_url = os.environ.get("E2B_API_URL")
        if api_url:
            opts["api_url"] = api_url
        return opts

    async def _awake_sandbox_async(self) -> None:
        """async 唤醒：重连 async 客户端（connect 自动恢复 paused 并刷新 timeout）。"""
        self._async_client = None
        await self._async_sandbox()

    async def _amaybe_extend_timeout(self) -> None:
        """async 版周期续期；时间戳与同步路径共享同一个沙箱死限。"""
        interval = max(60.0, self._timeout / 3)
        now = time.monotonic()
        if now - self._last_timeout_extend < interval:
            return
        try:
            sbx = await self._async_sandbox()
            await sbx.set_timeout(self._timeout)
        except Exception as e:  # noqa: BLE001
            # 沙箱被回收后此处必报 not found，属生命周期正常事件，记 INFO
            logger.info("async keepalive set_timeout failed for %s: %s", self.id, e)
            return
        self._last_timeout_extend = now

    async def _asdk(self, op: str, fn: Callable[[], Any]) -> Any:
        """async SDK 调用：暂停/断连错误唤醒后单次重试。"""
        return await self._heal.arun(op, fn, self._awake_sandbox_async)

    async def _arun_command_with_keepalive(
        self, fn: Callable[[], Any], effective_timeout: int
    ) -> Any:
        """长命令期间用 asyncio task 周期续期，命令时长不受沙箱超时约束。"""
        if effective_timeout < self._timeout:
            return await fn()
        interval = max(_KEEPALIVE_MIN_INTERVAL, self._timeout / 4)
        stop = asyncio.Event()

        async def _keeper() -> None:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    try:
                        sbx = await self._async_sandbox()
                        await sbx.set_timeout(self._timeout)
                    except Exception as e:  # noqa: BLE001
                        logger.debug("async midflight keepalive failed: %s", e)

        task = asyncio.create_task(_keeper())
        try:
            return await fn()
        finally:
            stop.set()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        if self.supports_async_sdk and not self._async_disabled:
            try:
                return await self._aexecute_native(command, timeout=timeout)
            except _AsyncClientInitError as e:
                # async 客户端建不起来（平台不完全兼容/网络不可达）：
                # 回落线程慢道；连续失败后本实例禁用 async 路径。
                self._async_init_failures += 1
                if self._async_init_failures >= 2:
                    self._async_disabled = True
                logger.warning(
                    "async sandbox client unavailable for %s (%s); "
                    "falling back to thread lane (failures=%d)",
                    self.id,
                    e,
                    self._async_init_failures,
                )
                return await self._aexecute_via_thread(command, timeout=timeout)
        return await self._aexecute_via_thread(command, timeout=timeout)

    async def _aexecute_native(
        self, command: str, *, timeout: int | None = None
    ) -> ExecuteResponse:
        """e2b 官方 async SDK 路径：纯 await，零线程占用。

        命令本质是 HTTP/WS 调用，同步 SDK 时代只能拿线程扛整段命令时长；
        async 客户端后长命令不再占任何阻塞 IO 线程池，续期 keeper 也从
        专线线程退化为普通 asyncio task。Cube 等 e2b 兼容平台共用此路径，
        不兼容时由 aexecute 自动回落线程慢道。
        """
        effective_timeout = self._command_timeout(timeout)
        try:
            sbx = await self._async_sandbox()
        except Exception as e:
            raise _AsyncClientInitError(str(e)) from e
        await self._amaybe_extend_timeout()
        kwargs: dict = {"cmd": self._with_work_dir(command), "timeout": effective_timeout}
        if self.env_vars:
            kwargs["envs"] = self.env_vars
        try:
            result = await self._asdk(
                "commands.run",
                lambda: self._arun_command_with_keepalive(
                    lambda: sbx.commands.run(**kwargs), effective_timeout
                ),
            )
            output = result.stdout or ""
            if result.stderr:
                output = f"{output}\n{result.stderr}" if output else result.stderr
            result = ExecuteResponse(output=output, exit_code=result.exit_code, truncated=False)
        except Exception as e:
            result = self._command_error_response(e, effective_timeout, command)
        notice = self._consume_startup_notice()
        if notice:
            output = result.output or ""
            result = ExecuteResponse(
                output=f"{notice}\n{output}" if output else notice,
                exit_code=result.exit_code,
                truncated=result.truncated,
            )
        return result

    async def _aexecute_via_thread(
        self, command: str, *, timeout: int | None = None
    ) -> ExecuteResponse:
        """线程路径（Cube 等无 async SDK 的平台）：走慢道独立线程池。"""
        effective_timeout = self._command_timeout(timeout)
        try:
            result = await run_long_blocking_io(
                lambda: self.execute(command, timeout=timeout),
                timeout=effective_timeout + 15,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Client-side timeout after {effective_timeout}s: {command[:100]}...")
            result = ExecuteResponse(
                output=f"Command timed out after {effective_timeout} seconds",
                exit_code=-1,
                truncated=False,
            )
        notice = self._consume_startup_notice()
        if notice:
            output = result.output or ""
            result = ExecuteResponse(
                output=f"{notice}\n{output}" if output else notice,
                exit_code=result.exit_code,
                truncated=result.truncated,
            )
        return result

    async def als(self, path: str) -> LsResult:
        """原生 async files.list；客户端不可用时回落慢道（不占快道）。"""
        resolved = self._resolve_path(path)
        sbx = await self._async_client_or_none()
        if sbx is None:
            return await run_long_blocking_io(self.ls, path)
        try:
            entries = await self._asdk("files.list", lambda: sbx.files.list(path=resolved))
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
            logger.warning(f"E2B async files.list({path}) failed: {e}, falling back")
            return await run_long_blocking_io(self.ls, path)

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        """原生 async files.read：与同步 read 同款二进制检测/大小上限/切片。"""
        resolved = self._resolve_path(file_path)
        sbx = await self._async_client_or_none()
        if sbx is None:
            return await run_long_blocking_io(self.read, file_path, offset, limit)
        try:
            size = await self._afile_size(sbx, resolved)
            if size is not None and size > SANDBOX_READ_MAX_BYTES:
                return ReadResult(
                    error=(
                        f"file too large to read directly: {size} bytes "
                        f"(limit {SANDBOX_READ_MAX_BYTES} bytes)"
                    )
                )
            content = await self._asdk(
                "files.read", lambda: sbx.files.read(path=resolved, format="text")
            )
            if "\x00" in content:
                raw = await self._asdk(
                    "files.read", lambda: sbx.files.read(path=resolved, format="bytes")
                )
                return self._read_as_base64(bytes(raw))
            stripped = content.strip()
            if len(stripped) >= 100:
                sample = stripped[:4096]
                non_text = sum(1 for c in sample if ord(c) < 32 and c not in "\t\n\r")
                if non_text / len(sample) > 0.3:
                    raw = await self._asdk(
                        "files.read", lambda: sbx.files.read(path=resolved, format="bytes")
                    )
                    return self._read_as_base64(bytes(raw))
            return slice_read_response(create_file_data(content), offset, limit)
        except Exception as e:
            logger.warning(f"E2B async files.read({file_path}) failed: {e}, falling back")
            return await run_long_blocking_io(self.read, file_path, offset, limit)

    async def _afile_size(self, sbx: Any, path: str) -> int | None:
        parent = os.path.dirname(path) or "/"
        try:
            entries = await self._asdk("files.list", lambda: sbx.files.list(path=parent))
        except Exception as e:
            logger.debug("E2B async files.list(%s) size preflight failed: %s", parent, e)
            return None
        for entry in entries:
            if getattr(entry, "path", None) == path and hasattr(entry, "size"):
                try:
                    return int(entry.size)
                except (TypeError, ValueError):
                    return None
        return None

    async def _async_client_or_none(self) -> Any:
        """取 async 客户端；不可用时登记失败并返回 None（调用方走慢道）。"""
        if not self.supports_async_sdk or self._async_disabled:
            return None
        try:
            return await self._async_sandbox()
        except Exception as e:
            self._register_async_init_failure(e)
            return None

    def _register_async_init_failure(self, error: Exception) -> None:
        self._async_init_failures += 1
        if self._async_init_failures >= 2:
            self._async_disabled = True
        logger.warning(
            "async sandbox client unavailable for %s (%s); using thread lane (failures=%d)",
            self.id,
            error,
            self._async_init_failures,
        )

    # magic bytes → MIME
    _MAGIC: list[tuple[bytes, str]] = [
        (b"\x89PNG", "image/png"),
        (b"\xff\xd8", "image/jpeg"),
        (b"GIF8", "image/gif"),
        (b"RIFFWEBP", "image/webp"),
        (b"%PDF-", "application/pdf"),
    ]

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """原生 async files.write；父目录经 aexecute 建立；回落慢道。"""
        if len(files) > SANDBOX_BATCH_FILES_LIMIT:
            return [
                file_upload_response(path=path, error="too_many_files") for path, _content in files
            ]
        sbx = await self._async_client_or_none()
        if sbx is None:
            return await run_long_blocking_io(self.upload_files, files)

        responses: list[FileUploadResponse] = []
        for path, content in files:
            resolved = self._resolve_path(path)
            if len(content) > SANDBOX_UPLOAD_MAX_BYTES:
                responses.append(file_upload_response(path=resolved, error="file_too_large"))
                continue
            try:
                parent = os.path.dirname(resolved)
                if parent:
                    await self.aexecute(f"mkdir -p {shlex.quote(parent)}")

                async def _write_one(p: str = resolved, c: Any = content) -> Any:
                    return await sbx.files.write(path=p, data=c)

                await self._asdk("files.write", _write_one)
                responses.append(FileUploadResponse(path=resolved, error=None))
            except Exception as e:
                error_type = classify_upload_error(str(e))
                logger.error(f"Failed to upload {resolved}: {e}")
                responses.append(FileUploadResponse(path=resolved, error=error_type))
        return responses

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """原生 async files.read(bytes)；大小预检同同步版；回落慢道。"""
        if len(paths) > SANDBOX_BATCH_FILES_LIMIT:
            return [
                file_download_response(path=path, content=None, error="too_many_files")
                for path in paths
            ]
        sbx = await self._async_client_or_none()
        if sbx is None:
            return await run_long_blocking_io(self.download_files, paths)

        responses: list[FileDownloadResponse] = []
        for path in paths:
            resolved = self._resolve_path(path)
            try:
                size = await self._afile_size(sbx, resolved)
                if size is not None and size > SANDBOX_DOWNLOAD_MAX_BYTES:
                    logger.warning(
                        "Skipping async download for large file %s: %s bytes > %s",
                        resolved,
                        size,
                        SANDBOX_DOWNLOAD_MAX_BYTES,
                    )
                    responses.append(
                        FileDownloadResponse(path=resolved, content=None, error="file_not_found")
                    )
                    continue

                async def _read_bytes(p: str = resolved) -> Any:
                    return await sbx.files.read(path=p, format="bytes")

                raw = await self._asdk("files.read", _read_bytes)
                responses.append(
                    FileDownloadResponse(path=resolved, content=bytes(raw), error=None)
                )
            except Exception as e:
                logger.error(f"Failed to download {resolved}: {e}")
                responses.append(
                    file_download_response(path=resolved, content=None, error="file_not_found")
                )
        return responses
