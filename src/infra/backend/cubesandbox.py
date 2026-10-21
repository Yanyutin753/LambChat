"""CubeSandbox backend adapter for deepagents sandbox protocol."""

from __future__ import annotations

import base64
import binascii
import os
import shlex
from collections.abc import AsyncGenerator
from typing import Any, Literal, cast

import httpx
from deepagents.backends.utils import create_file_data, slice_read_response

from src.infra.async_utils import run_long_blocking_io
from src.infra.backend.e2b import (
    SANDBOX_BATCH_FILES_LIMIT,
    SANDBOX_DOWNLOAD_MAX_BYTES,
    SANDBOX_READ_MAX_BYTES,
    SANDBOX_UPLOAD_MAX_BYTES,
    E2BBackend,
)
from src.infra.backend.protocol_compat import (
    FileDownloadResponse,
    FileUploadResponse,
    LsResult,
    ReadResult,
    WriteResult,
    file_download_response,
)
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)
_DEFAULT_TIMEOUT = 30 * 60

# envd HTTP 文件 API 的常量（cubesandbox._commands 私有）；SDK 结构漂移时
# 回落默认值，原始字节通道整体降级到 base64 命令通道。
try:  # pragma: no cover - 依赖 SDK 内部常量
    from cubesandbox._commands import DEFAULT_ENVD_USER, ENVD_PORT
except ImportError:  # pragma: no cover
    DEFAULT_ENVD_USER = "user"
    ENVD_PORT = 49983

# ── 二进制字节通道 ────────────────────────────────────────────────────
# Cube envd 的 files HTTP API 在 SDK 侧恒以 resp.text（utf-8 replace）返回，
# 二进制字节会被 U+FFFD 替换不可逆破坏（2026-10-14 生产事故：Word/PDF 经
# download_files 全损）。
#
# 主通道＝envd HTTP 原始字节直读：与 SDK files.read 同一条 wire，改取
# resp.content——无 base64 膨胀、单请求，大文件（几百 MB 量级）快且省内存。
# 兜底通道＝命令通道 base64：stdout 事件 replace 解码对纯 ASCII 无损，
# envd Connect 单信封上限 64MB，块上限 16MiB（base64 后 ~22MB）。
_B64_CHUNK_BYTES = 16 * 1024 * 1024
_B64_CHUNK_BS = 1024 * 1024  # dd 传输块单位；_B64_CHUNK_BYTES 必须是它的整数倍

# 无鉴权 Cube 代理部署（未配置 CUBE_API_KEY）也要能起 e2b wire 兼容的 async
# 客户端：e2b SDK 强制要求非空 api_key；占位值在 Cube 未开鉴权时被忽略，
# 开了鉴权会 401，走既有线程车道回落（与缺 key 旧行为一致，但不再恒灭）。
_CUBE_ASYNC_NOAUTH_KEY = "cube-noauth-placeholder"


def _text_looks_binary(content: str) -> bool:
    """在 lossy 解码文本上做二进制检测。

    NUL 与控制字符比例沿用 E2B 同款阈值；额外加 U+FFFD 替换率——Cube 的
    文本读取把非法 UTF-8 字节替换成 U+FFFD，压缩二进制（zip/docx/png）的
    替换率远高于正常文本。
    """
    if "\x00" in content:
        return True
    stripped = content.strip()
    if len(stripped) < 100:
        return False
    sample = stripped[:4096]
    non_text = sum(1 for c in sample if ord(c) < 32 and c not in "\t\n\r")
    if non_text / len(sample) > 0.3:
        return True
    return sample.count("\ufffd") / len(sample) > 0.02


def _b64_chunk_commands(path: str, size: int | None) -> list[str]:
    """按大小生成 base64 读取命令序列（小文件单发，大文件 dd 分块）。"""
    quoted = shlex.quote(path)
    if size is None or size <= _B64_CHUNK_BYTES:
        return [f"base64 -w0 {quoted}"]
    chunks = (size + _B64_CHUNK_BYTES - 1) // _B64_CHUNK_BYTES
    per_chunk = _B64_CHUNK_BYTES // _B64_CHUNK_BS
    return [
        f"dd if={quoted} bs={_B64_CHUNK_BS} skip={i * per_chunk} count={per_chunk} "
        "2>/dev/null | base64 -w0"
        for i in range(chunks)
    ]


def _decode_b64_pieces(pieces: list[str], expected_size: int | None) -> bytes:
    """解码分块 base64 并按已知大小校验完整性——绝不交付可疑字节。"""
    chunks: list[bytes] = []
    total = 0
    for piece in pieces:
        try:
            raw = base64.b64decode(piece, validate=True)
        except (binascii.Error, ValueError) as e:
            raise IOError(f"binary read produced invalid base64: {e}") from e
        chunks.append(raw)
        total += len(raw)
    if expected_size is not None and total != expected_size:
        raise IOError(f"binary read size mismatch: got {total} bytes, expected {expected_size}")
    return b"".join(chunks)


def _pieces_from_output(output: str | None) -> str:
    """execute() 会把 stderr 并入 output；剥掉全部空白（base64 输出不含空白）。"""
    return "".join((output or "").split())


class CubeSandboxBackend(E2BBackend):
    """Backend wrapper for the native CubeSandbox Python SDK.

    CubeSandbox intentionally exposes an E2B-like ``commands`` and ``files`` API,
    so LambChat can reuse the mature command, file, glob, upload, and download
    behavior from ``E2BBackend`` while keeping lifecycle/configuration native.

    例外是二进制读取：Cube 的 files.read 恒返回 lossy 解码文本（无 bytes
    通道），本类对 read/download 的二进制路径改走命令通道 base64（见
    ``_read_bytes``），文本路径保持 SDK 原生。
    """

    # Cube 的 wire 协议兼容 e2b SDK：异步命令共用 e2b async 客户端路径
    # （零线程占用）；个别部署不兼容时 aexecute 自动回落线程慢道。
    supports_async_sdk = True

    @staticmethod
    def _cube_async_api_key() -> str:
        return (
            os.environ.get("CUBE_API_KEY")
            or getattr(settings, "CUBE_API_KEY", "")
            or _CUBE_ASYNC_NOAUTH_KEY
        )

    def _register_async_init_failure(self, error: Exception) -> None:
        """Cube 控制面未实现 e2b async 握手端点（POST /v2/sandboxes/{id}/connect
        返回 404 空响应体 → SDK 抛 JSONDecodeError）是已知部署形态而非故障：
        一次失败即禁用 async 车道并降为 debug 日志，不刷 WARNING、不重试。
        其余错误沿用基类语义（2 次失败后禁用）。
        """
        if "Expecting value" in str(error):
            self._async_init_failures += 1
            self._async_disabled = True
            logger.debug(
                "[CubeSandbox] e2b async connect unavailable on this deployment "
                "(control plane lacks connect handshake); using thread lane: %s",
                type(error).__name__,
            )
            return
        super()._register_async_init_failure(error)

    def _async_connect_opts(self) -> dict:
        """e2b async 客户端指向 Cube API（wire 兼容）。"""
        opts: dict = {
            "timeout": self._timeout,
            "api_url": settings.CUBE_API_URL,
            "domain": settings.CUBE_SANDBOX_DOMAIN,
            "request_timeout": float(settings.CUBE_REQUEST_TIMEOUT),
            "api_key": self._cube_async_api_key(),
        }
        return opts

    def __init__(
        self,
        sandbox,
        timeout: int | None = None,
        env_vars: dict[str, str] | None = None,
        work_dir: str | None = None,
    ):
        super().__init__(
            sandbox=sandbox,
            timeout=timeout
            or settings.CUBE_TIMEOUT
            or int(os.environ.get("CUBE_TIMEOUT", _DEFAULT_TIMEOUT)),
            env_vars=env_vars,
            work_dir=work_dir,
        )
        self._ensured_parent_dirs: set[str] = set()

    def _wake_sandbox(self) -> None:
        """唤醒被空闲超时暂停的沙箱；Cube SDK 用显式 resume()（connect 亦可）。"""
        # self._sandbox 运行时是 CubeSandbox（E2B 签名是继承带来的假象），
        # resume 是 Cube 特有 API。
        cast(Any, self._sandbox).resume(timeout=self._timeout)

    def _files_read(self, path: str, format: Literal["text", "bytes"]) -> Any:
        # Cube 的 files.read 没有 format 参数（恒返回 lossy 解码 str），文本
        # 读取专用；二进制必须走 _read_bytes 字节通道。
        del format
        return self._sdk("files.read", lambda: self._sandbox.files.read(path))

    def get_info(self) -> dict[str, Any]:
        # cubesandbox>=0.7.0 的 SandboxInfo 是 dict 子类（dataclass），装的是
        # CubeAPI 原始 JSON（camelCase 键）；snake_case 只是类型化属性不是
        # dict 键。mypy 不认 dataclass 继承 dict，cast 明示运行时形态。
        try:
            info = cast(dict[str, Any], self._sandbox.get_info())
            return {
                "sandbox_id": info.get("sandboxID") or self.id,
                "state": str(info.get("state", "unknown")).lower(),
                "template": info.get("templateID"),
                "metadata": info.get("metadata") or {},
                "started_at": info.get("startedAt"),
                "end_at": info.get("endAt"),
            }
        except Exception as e:
            logger.warning("Failed to get CubeSandbox info: %s", e)
            return {"sandbox_id": self.id, "state": "unknown"}

    def pause(self) -> None:
        self._sandbox.pause()
        logger.info("[CubeSandbox] Paused sandbox %s", self.id)

    def _ensure_parent_dir(self, file_path: str) -> None:
        file_path = self._resolve_path(file_path)
        parent = os.path.dirname(file_path)
        if not parent or parent in self._ensured_parent_dirs:
            return
        self.execute(f"mkdir -p {shlex.quote(parent)}")
        self._ensured_parent_dirs.add(parent)

    def ls(self, path: str) -> LsResult:
        path = self._resolve_path(path)
        quoted = shlex.quote(path)
        command = (
            "python3 -c "
            + shlex.quote(
                "import json, os, sys\n"
                "path = sys.argv[1]\n"
                "items = []\n"
                "for name in sorted(os.listdir(path)):\n"
                "    full = os.path.join(path, name)\n"
                "    try:\n"
                "        st = os.lstat(full)\n"
                "    except OSError:\n"
                "        continue\n"
                "    item = {'path': full, 'size': st.st_size}\n"
                "    if os.path.isdir(full):\n"
                "        item['is_dir'] = True\n"
                "    items.append(item)\n"
                "print(json.dumps(items))\n"
            )
            + f" {quoted}"
        )
        result = self.execute(command)
        if result.exit_code != 0:
            return LsResult(error=result.output or f"Could not list {path}")
        try:
            import json

            return LsResult(entries=json.loads(result.output or "[]"))
        except Exception as e:
            logger.warning("Failed to parse CubeSandbox ls output for %s: %s", path, e)
            return LsResult(error=str(e))

    # ── 字节安全读取（主通道 envd HTTP 原始字节，兜底命令通道 base64）──

    def _read_bytes_via_envd_http(self, path: str) -> bytes:
        """envd /files 原始字节直读：复用 SDK 自己的 httpx client（代理路由/
        鉴权头与 SDK files.read 完全一致），只改取 resp.content 保真字节。"""
        files_api = self._sandbox.files
        ensure_client = getattr(files_api, "_ensure_client", None)
        if ensure_client is not None:
            ensure_client()
        client = getattr(self._sandbox, "_client", None)
        if client is None:
            raise IOError("sandbox http client unavailable")
        base_headers = getattr(files_api, "_base_headers", None)
        headers = base_headers() if callable(base_headers) else {}
        resp = client.get(
            f"http://{self._sandbox.get_host(ENVD_PORT)}/files",
            params={"path": path, "username": DEFAULT_ENVD_USER},
            headers=headers,
        )
        if resp.status_code != 200:
            raise IOError(f"envd raw read HTTP {resp.status_code}: {(resp.text or '')[:120]}")
        return resp.content

    async def _aiter_file_bytes(self, path: str) -> AsyncGenerator[bytes, None]:
        files_api = cast(Any, self._sandbox.files)
        sandbox = cast(Any, self._sandbox)
        config = sandbox._config
        url = httpx.URL(f"http://{sandbox.get_host(ENVD_PORT)}/files")
        headers = {**sandbox._traffic_token_headers(), **files_api._base_headers()}
        if config.proxy_node_ip:
            headers["Host"] = url.host
            url = url.copy_with(host=config.proxy_node_ip, port=config.proxy_port)
        started = False
        try:
            async with httpx.AsyncClient(
                headers=headers,
                trust_env=False,
                timeout=httpx.Timeout(config.request_timeout, read=60),
                follow_redirects=True,
            ) as client:
                async with client.stream(
                    "GET", url, params={"path": path, "username": DEFAULT_ENVD_USER}
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(chunk_size=256 * 1024):
                        started = True
                        yield chunk
                    return
        except Exception:
            if started:
                raise  # Never restart a partially delivered stream.
            logger.info("Cube binary stream using bounded command fallback: %s", path)
        size = await self._astat_size(path)
        if size is None:
            raise IOError("file_not_found")
        for command in _b64_chunk_commands(path, size):
            result = await self.aexecute(command)
            if result.exit_code != 0:
                raise IOError("binary read command failed")
            yield _decode_b64_pieces([_pieces_from_output(result.output)], None)

    def _read_bytes(self, path: str, size: int | None) -> bytes:
        """字节精确读取：HTTP 直读优先（快、无膨胀），失败回落 base64 命令通道。"""
        try:
            data = self._read_bytes_via_envd_http(path)
            if size is None or len(data) == size:
                return data
            raise IOError(f"envd raw read size mismatch: got {len(data)}, expected {size}")
        except Exception as e:
            logger.info(
                "CubeSandbox raw byte read fell back to command channel for %s: %s", path, e
            )
            return self._read_bytes_via_command(path, size)

    def _read_bytes_via_command(self, path: str, size: int | None) -> bytes:
        """兜底字节通道：base64 over 命令通道（files API 文本读取会破坏二进制）。"""
        pieces: list[str] = []
        for command in _b64_chunk_commands(path, size):
            result = self.execute(command)
            if result.exit_code != 0:
                raise IOError(f"binary read command failed (exit {result.exit_code})")
            pieces.append(_pieces_from_output(result.output))
        return _decode_b64_pieces(pieces, size)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:  # type: ignore[override]
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
            content = self._files_read(file_path, "text")
            if _text_looks_binary(str(content)):
                return self._read_as_base64(self._read_bytes(file_path, size))
            return slice_read_response(create_file_data(str(content)), offset, limit)
        except Exception as e:
            logger.warning("CubeSandbox files.read(%s) failed: %s", file_path, e)
            return ReadResult(error=str(e))

    def write(self, file_path: str, content: str) -> WriteResult:
        file_path = self._resolve_path(file_path)
        try:
            self._ensure_parent_dir(file_path)
            self._files_write(file_path, content)
            return WriteResult(path=file_path)
        except Exception as e:
            logger.error("CubeSandbox files.write(%s) failed: %s", file_path, e)
            return WriteResult(path=file_path, error="file_not_found")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        if len(files) > SANDBOX_BATCH_FILES_LIMIT:
            return [FileUploadResponse(path=path, error="too_many_files") for path, _ in files]

        responses: list[FileUploadResponse] = []
        for path, content in files:
            path = self._resolve_path(path)
            if len(content) > SANDBOX_UPLOAD_MAX_BYTES:
                responses.append(FileUploadResponse(path=path, error="file_too_large"))
                continue
            try:
                self._ensure_parent_dir(path)
                self._files_write(path, content)
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception as e:
                logger.error("CubeSandbox upload %s failed: %s", path, e)
                responses.append(FileUploadResponse(path=path, error="file_not_found"))
        return responses

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
                    responses.append(
                        file_download_response(path=path, content=None, error="file_not_found")
                    )
                    continue
                content_bytes = self._read_bytes(path, size)
                responses.append(file_download_response(path=path, content=content_bytes))
            except Exception as e:
                logger.error("CubeSandbox download %s failed: %s", path, e)
                responses.append(
                    file_download_response(path=path, content=None, error="file_not_found")
                )
        return responses

    # ── async 覆写：不走 e2b 客户端 files.read(bytes)（Cube envd 保真度
    # 不可验），二进制统一命令通道；文本优先 e2b 客户端，失败回落同步。───

    async def _astat_size(self, path: str) -> int | None:
        result = await self.aexecute(f"stat -c %s {shlex.quote(path)} 2>/dev/null", timeout=5)
        if result.exit_code != 0:
            return None
        try:
            return int((result.output or "").strip())
        except ValueError:
            return None

    async def _acube_text_read(self, path: str) -> str:
        sbx = await self._async_client_or_none()
        if sbx is None:
            return await run_long_blocking_io(self._files_read, path, "text")
        return await self._asdk("files.read", lambda: sbx.files.read(path=path, format="text"))

    async def _aread_bytes(self, path: str, size: int | None) -> bytes:
        """async 字节精确读取：HTTP 直读优先（单请求走慢道），失败回落命令通道。"""
        try:
            data = await run_long_blocking_io(self._read_bytes_via_envd_http, path)
            if size is None or len(data) == size:
                return data
            raise IOError(f"envd raw read size mismatch: got {len(data)}, expected {size}")
        except Exception as e:
            logger.info(
                "CubeSandbox async raw byte read fell back to command channel for %s: %s",
                path,
                e,
            )
            return await self._aread_bytes_via_command(path, size)

    async def _aread_bytes_via_command(self, path: str, size: int | None) -> bytes:
        pieces: list[str] = []
        for command in _b64_chunk_commands(path, size):
            result = await self.aexecute(command)
            if result.exit_code != 0:
                raise IOError(f"binary read command failed (exit {result.exit_code})")
            pieces.append(_pieces_from_output(result.output))
        return _decode_b64_pieces(pieces, size)

    async def aread(  # type: ignore[override]
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        resolved = self._resolve_path(file_path)
        try:
            size = await self._astat_size(resolved)
            if size is not None and size > SANDBOX_READ_MAX_BYTES:
                return ReadResult(
                    error=(
                        f"file too large to read directly: {size} bytes "
                        f"(limit {SANDBOX_READ_MAX_BYTES} bytes)"
                    )
                )
            text = await self._acube_text_read(resolved)
            if _text_looks_binary(str(text)):
                return self._read_as_base64(await self._aread_bytes(resolved, size))
            return slice_read_response(create_file_data(str(text)), offset, limit)
        except Exception as e:
            logger.warning(
                "CubeSandbox async files.read(%s) failed: %s, falling back to sync",
                file_path,
                e,
            )
            return await run_long_blocking_io(self.read, file_path, offset, limit)

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        if len(paths) > SANDBOX_BATCH_FILES_LIMIT:
            return [
                file_download_response(path=path, content=None, error="too_many_files")
                for path in paths
            ]

        responses: list[FileDownloadResponse] = []
        for path in paths:
            resolved = self._resolve_path(path)
            try:
                size = await self._astat_size(resolved)
                if size is not None and size > SANDBOX_DOWNLOAD_MAX_BYTES:
                    responses.append(
                        file_download_response(path=resolved, content=None, error="file_not_found")
                    )
                    continue
                content = await self._aread_bytes(resolved, size)
                responses.append(file_download_response(path=resolved, content=content))
            except Exception as e:
                logger.error("CubeSandbox async download %s failed: %s", resolved, e)
                responses.append(
                    file_download_response(path=resolved, content=None, error="file_not_found")
                )
        return responses

    def _file_size(self, path: str) -> int | None:
        command = f"stat -c %s {shlex.quote(path)} 2>/dev/null"
        result = self.execute(command, timeout=5)
        if result.exit_code != 0:
            return None
        try:
            return int((result.output or "").strip())
        except ValueError:
            return None
