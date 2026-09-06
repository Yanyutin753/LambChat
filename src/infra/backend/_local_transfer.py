"""本地沙箱结构化传输通道：fs_upload / fs_download（upload/download 的主路径）。

exec 命令往返（base64 塞 argv）在 win32 撞 cmd.exe 8191 字符命令行上限
（>~6KB 文件必败，2026-09-06 生产事故根因）、对二进制内容天然脆弱，且下载
受 daemon stdout 截断牵制；结构化 op 直接走中继 JSON 载荷，无命令行长限制、
二进制安全。协议按字节 offset 定位、每块独立幂等（daemon 侧
``client/lambchat_sandbox/fsops.py`` 的 fs_upload/fs_download 文档），中继
瞬断按块重试一次安全。

老 daemon 不认识这两个 op 时回 ``unsupported op`` → 这里抛
:class:`FsTransferUnsupportedError` 并在实例上粘滞能力位，调用方降级
exec 旧链路（daemon 自更新后重建 backend 即恢复新通道）。

两个 Mixin：
- :class:`LocalFsTransferMixin` — 通道原语（LocalSandboxBackend 组入）；
- :class:`WorkspaceAliasTransferMixin` — 别名层的 upload/download 整批分流
  （WorkspaceAliasBackend 组入；``super()`` 按 MRO 落到 LocalSandboxBackend
  的 exec 旧链路）。
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

from src.infra.backend._local_compat import _run_coro_sync
from src.infra.backend.lazy_sandbox import PUBLIC_SHARED_DIR
from src.infra.backend.protocol_compat import (
    FileDownloadResponse,
    FileUploadResponse,
    file_download_response,
    file_upload_response,
)
from src.infra.logging import get_logger
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.kernel.config import settings
from src.kernel.errors import AppError

logger = get_logger(__name__)

# 结构化传输通道（fs_upload/fs_download）分块：单块原始字节 1MiB
# （b64 ~1.37MB），与 daemon 侧 fsops.FS_TRANSFER_MAX_BYTES=2MB 的单 op
# 上限留足余量；更大文件按 offset 分块多 op 完成。
FS_TRANSFER_CHUNK_BYTES = 1024 * 1024


class FsTransferUnsupportedError(Exception):
    """老 daemon 不认识 fs_upload/fs_download（回 ``unsupported op``）。

    调用方据此降级 exec 旧链路；能力位在 backend 实例上粘滞，同一会话内
    不再逐批探测（daemon 自更新后重建 backend 即恢复新通道）。
    """


def _download_max_bytes() -> int:
    """下载单文件上限：与 reveal/S3 内部上传共用同一个环境变量旋钮。

    ``S3_INTERNAL_UPLOAD_MAX_SIZE``（默认 1GB，见 kernel.config）统一控制
    reveal 文件、本地沙箱下载与 S3 内部上传三处上限，不各自写死；超限在
    首片回 size 后即报显式 ``file_too_large``，不继续整读。
    """
    configured = int(getattr(settings, "S3_INTERNAL_UPLOAD_MAX_SIZE", 0) or 0)
    return configured if configured > 0 else 1


class LocalFsTransferMixin:
    """fs_upload/fs_download 通道原语。

    依赖宿主（LocalSandboxBackend）实例属性：``_user_id`` / ``_machine_id`` /
    ``_exec_timeout`` / ``_fs_transfer_supported``。通道方法显式收 ``cwd``
    （虚拟工作区路径），不读取宿主的 work_dir。
    """

    _user_id: str
    _machine_id: str | None
    _exec_timeout: int
    _fs_transfer_supported: bool | None

    async def _afs_transfer_call(self, op: str, payload: dict[str, Any]) -> dict:
        """发一个传输 fs op 并取回 ``result`` 体（文件级错误在 result 里）。"""
        try:
            resp = await dispatch_local_call(
                self._user_id,
                op,
                payload,
                timeout=float(self._exec_timeout),
                machine_id=self._machine_id,
            )
        except AppError as exc:
            detail = str(exc.args_data.get("detail") or exc.message)
            if "unsupported op" in detail:
                self._fs_transfer_supported = False
                raise FsTransferUnsupportedError(op) from exc
            raise
        result = resp.get("result")
        return result if isinstance(result, dict) else {}

    async def _afs_transfer_call_with_retry(self, op: str, payload: dict[str, Any]) -> dict:
        """中继瞬断（超时/离线抖动）立即重试一次——传输 op 按 offset 幂等，重发安全。"""
        last_exc: AppError | None = None
        for _attempt in range(2):
            try:
                return await self._afs_transfer_call(op, payload)
            except FsTransferUnsupportedError:
                raise
            except AppError as exc:
                last_exc = exc
        raise last_exc  # type: ignore[misc]  # 循环必已赋值

    async def _aupload_via_fs(self, path: str, content: bytes, *, cwd: str) -> str | None:
        """经 fs_upload 分块写文件；返回错误码/错误文本或 None（成功）。

        首块 truncate 创建（daemon 建父目录），后续块按 offset 定位写；
        空文件也发首块（truncate 即创建空文件）。
        """
        offset = 0
        first = True
        while offset < len(content) or first:
            chunk = content[offset : offset + FS_TRANSFER_CHUNK_BYTES]
            data = await self._afs_transfer_call_with_retry(
                "fs_upload",
                {
                    "cwd": cwd,
                    "path": path,
                    "content_b64": base64.b64encode(chunk).decode("ascii"),
                    "offset": offset,
                    "truncate": first,
                },
            )
            if "error" in data:
                return str(data["error"])
            offset += len(chunk)
            first = False
        return None

    async def _adownload_via_fs(self, path: str, *, cwd: str) -> bytes | str:
        """经 fs_download 分片循环读到 eof；返回内容字节或错误文本。

        首片响应携带全文件 ``size``——据此执行统一上限预检
        （S3_INTERNAL_UPLOAD_MAX_SIZE，与 exec 路径同语义），超限即报显式
        ``file_too_large``，不继续整读。
        """
        chunks: list[bytes] = []
        offset = 0
        first = True
        while True:
            data = await self._afs_transfer_call_with_retry(
                "fs_download",
                {"cwd": cwd, "path": path, "offset": offset, "length": FS_TRANSFER_CHUNK_BYTES},
            )
            if "error" in data:
                return str(data["error"])
            if first:
                try:
                    size = int(data.get("size") or 0)
                except (TypeError, ValueError):
                    size = 0
                max_bytes = _download_max_bytes()
                if size > max_bytes:
                    return (
                        f"file_too_large: {size} bytes exceeds {max_bytes} limit "
                        "(S3_INTERNAL_UPLOAD_MAX_SIZE)"
                    )
                first = False
            try:
                raw = base64.b64decode(str(data.get("content_b64") or ""))
            except (ValueError, TypeError):
                logger.warning("local fs_download(%s) got non-base64 output", path)
                return f"invalid_download_output: {str(data.get('content_b64'))[:80]!r}"
            chunks.append(raw)
            offset += len(raw)
            if data.get("eof") or not raw:
                return b"".join(chunks)


class WorkspaceAliasTransferMixin:
    """别名层的 upload/download 整批分流：相对路径走结构化通道，其余降级 exec。

    依赖宿主（WorkspaceAliasBackend / LocalSandboxBackend）：``work_dir`` /
    ``_fs_transfer_supported`` / ``_strip_path``；``super()`` 按 MRO 落到
    LocalSandboxBackend 的 exec 旧链路。
    """

    work_dir: str
    _fs_transfer_supported: bool | None

    if TYPE_CHECKING:

        def _strip_path(self, path: str | None) -> str | None: ...

        async def _aupload_via_fs(self, path: str, content: bytes, *, cwd: str) -> str | None: ...

        async def _adownload_via_fs(self, path: str, *, cwd: str) -> bytes | str: ...

    def _transfer_rebase(self, path: str) -> tuple[str, str]:
        """传输 op 的 cwd/path 重定位：.shared 别名剥成 cwd=/workspace/.shared + 纯相对路径
        （fs op 路径不得逃出工作区，与 _afs_call 的重定位同则）。"""
        if path == "../.shared" or path.startswith("../.shared/"):
            return PUBLIC_SHARED_DIR, path[len("../.shared") :].lstrip("/") or "."
        return self.work_dir, path

    def _fs_transfer_eligible(self, stripped: str) -> bool:
        """该（已剥离别名的）路径能否走结构化通道：须是工作区内相对路径。

        绝对路径与 ``../`` 上溯（.shared 除外）是 exec 旧链路的既有语义
        （fs op 锁死工作区会拒绝），保持分流不改变行为。
        """
        if stripped.startswith("/"):
            return False
        if stripped == "../.shared" or stripped.startswith("../.shared/"):
            return True
        return not stripped.startswith("../")

    async def _aupload_one_via_fs(self, stripped: str, content: bytes) -> FileUploadResponse:
        cwd, path = self._transfer_rebase(stripped)
        error = await self._aupload_via_fs(path, content, cwd=cwd)
        return file_upload_response(path=stripped, error=error)  # type: ignore[arg-type]

    async def _adownload_one_via_fs(self, stripped: str) -> FileDownloadResponse:
        cwd, path = self._transfer_rebase(stripped)
        outcome = await self._adownload_via_fs(path, cwd=cwd)
        if isinstance(outcome, str):
            return file_download_response(path=stripped, content=None, error=outcome)
        return FileDownloadResponse(path=stripped, content=outcome, error=None)

    async def _aupload_dispatch(
        self, stripped: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        """整批分流：相对路径走 fs_upload，其余（含降级）走 exec 旧链路。"""
        results: list[FileUploadResponse | None] = [None] * len(stripped)
        if self._fs_transfer_supported is not False:
            for i, (path, content) in enumerate(stripped):
                if not self._fs_transfer_eligible(path):
                    continue
                try:
                    results[i] = await self._aupload_one_via_fs(path, content)
                except FsTransferUnsupportedError:
                    break  # 老 daemon：本批剩余与后续批次直接 exec
        pending = [i for i, result in enumerate(results) if result is None]
        if pending:
            legacy = await super().aupload_files([stripped[i] for i in pending])  # type: ignore[misc]
            for i, resp in zip(pending, legacy, strict=True):
                results[i] = resp
        return [result for result in results if result is not None]  # None 槽位已全被 legacy 填充

    async def _adownload_dispatch(self, stripped: list[str]) -> list[FileDownloadResponse]:
        results: list[FileDownloadResponse | None] = [None] * len(stripped)
        if self._fs_transfer_supported is not False:
            for i, path in enumerate(stripped):
                if not self._fs_transfer_eligible(path):
                    continue
                try:
                    results[i] = await self._adownload_one_via_fs(path)
                except FsTransferUnsupportedError:
                    break
        pending = [i for i, result in enumerate(results) if result is None]
        if pending:
            legacy = await super().adownload_files([stripped[i] for i in pending])  # type: ignore[misc]
            for i, resp in zip(pending, legacy, strict=True):
                results[i] = FileDownloadResponse(
                    path=stripped[i], content=resp.content, error=resp.error
                )
        return [result for result in results if result is not None]  # 同上

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        stripped = [(self._strip_path(path) or path, content) for path, content in files]
        results = _run_coro_sync(self._aupload_dispatch(stripped))
        return [
            FileUploadResponse(path=path, error=result.error)
            for (path, _), result in zip(files, results, strict=True)
        ]

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        stripped = [(self._strip_path(path) or path, content) for path, content in files]
        results = await self._aupload_dispatch(stripped)
        return [
            FileUploadResponse(path=path, error=result.error)
            for (path, _), result in zip(files, results, strict=True)
        ]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        stripped = [self._strip_path(path) or path for path in paths]
        results = _run_coro_sync(self._adownload_dispatch(stripped))
        return [
            FileDownloadResponse(path=path, content=result.content, error=result.error)
            for path, result in zip(paths, results, strict=True)
        ]

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        stripped = [self._strip_path(path) or path for path in paths]
        results = await self._adownload_dispatch(stripped)
        return [
            FileDownloadResponse(path=path, content=result.content, error=result.error)
            for path, result in zip(paths, results, strict=True)
        ]
