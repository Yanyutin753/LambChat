"""本地沙箱后端：命令经中继落到用户本机 daemon 执行（spec §3.3）。

文件操作（ls/read/write/edit/glob/grep）由 deepagents BaseSandbox 基于
execute()/aexecute() 自动继承，无需在本类重写；upload/download 是
BaseSandbox 的抽象成员，这里以单条 python3 + base64 命令往返实现，
仍走同一条中继链路（daemon 协议在 M1 仅有 exec 一个 op）。

注意（与 E2BBackend 相反的方向）：本后端的原生原语是异步的
（dispatch_local_call 轮询 Redis），因此 aexecute 是主路径，同步
execute 通过 asyncio.run 桥接（照 _skills_path_utils._run_async 模式）；
run_blocking_io 接收同步可调用对象，无法用于这里的异步→同步桥接。
"""

import asyncio
import base64
import posixpath
import shlex
from typing import Any, Coroutine, TypeVar

from deepagents.backends.sandbox import BaseSandbox

from src.infra.backend.protocol_compat import (
    ExecuteResponse,
    ExtendedFileError,
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

T = TypeVar("T")


def _run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """在同步上下文中运行异步协程（照 _skills_path_utils._run_async 模式）。

    没有运行中的事件循环（如 asyncio.to_thread 的 worker 线程）时用
    asyncio.run；若在运行中的事件循环内被同步调用则报错，要求改用异步 API。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError(
        "LocalSandboxBackend.execute() cannot run inside an active event loop; use aexecute()."
    )


def _classify_file_error(text: str) -> ExtendedFileError:
    """把 daemon 返回的错误文本映射为标准 FileOperationError 字面量。"""
    lowered = text.lower()
    if "permission" in lowered:
        return "permission_denied"
    if "directory" in lowered:
        return "is_directory"
    return "file_not_found"


class LocalSandboxBackend(BaseSandbox):
    """本地沙箱后端：命令经中继（Redis 请求/结果通道）落到用户本机 daemon。

    cwd 固定为 `/workspace/{session_id}`（spec §3.3），由 daemon 负责创建与
    切换；执行超时默认取 settings.SANDBOX_LOCAL_EXEC_TIMEOUT。
    """

    def __init__(self, *, user_id: str, session_id: str, exec_timeout: int | None = None):
        self._user_id = user_id
        self._session_id = session_id
        self._exec_timeout = exec_timeout or settings.SANDBOX_LOCAL_EXEC_TIMEOUT

    @property
    def id(self) -> str:
        return f"local-{self._session_id}"

    # =========================================================================
    # Command execution（BaseSandbox 的抽象成员，其余文件操作由此自动继承）
    # =========================================================================

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        result = await dispatch_local_call(
            self._user_id,
            "exec",
            {"command": command, "cwd": f"/workspace/{self._session_id}"},
            timeout=float(timeout or self._exec_timeout),
        )
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""
        # ExecuteResponse 只有合并 output 字段（protocol.py），照 E2BBackend 的拼接方式
        output = f"{stdout}\n{stderr}" if stdout and stderr else (stdout or stderr)
        return ExecuteResponse(
            output=output,
            exit_code=int(result.get("exit_code") or 0),
            truncated=False,
        )

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return _run_coro_sync(self.aexecute(command, timeout=timeout))

    # =========================================================================
    # Upload / download（BaseSandbox 抽象成员，经 exec op 的单命令往返实现）
    # =========================================================================

    @staticmethod
    def _upload_command(path: str, content: bytes) -> str:
        b64_content = base64.standard_b64encode(content).decode("ascii")
        parent = posixpath.dirname(path)
        mkdir = f"mkdir -p {shlex.quote(parent)} && " if parent else ""
        return (
            f'{mkdir}python3 -c "import base64, sys; '
            f"open(sys.argv[1], 'wb').write(base64.b64decode(sys.argv[2]))\" "
            f"{shlex.quote(path)} {shlex.quote(b64_content)}"
        )

    @staticmethod
    def _download_command(path: str) -> str:
        return (
            'python3 -c "import base64, sys; '
            "sys.stdout.buffer.write(base64.b64encode(open(sys.argv[1], 'rb').read()))\" "
            f"{shlex.quote(path)}"
        )

    def _upload_response(self, path: str, result: ExecuteResponse) -> FileUploadResponse:
        if result.exit_code != 0:
            return file_upload_response(
                path=path,
                error=_classify_file_error(result.output),
            )
        return FileUploadResponse(path=path, error=None)

    def _download_response(self, path: str, result: ExecuteResponse) -> FileDownloadResponse:
        if result.exit_code != 0:
            return file_download_response(
                path=path, content=None, error=_classify_file_error(result.output)
            )
        try:
            content = base64.b64decode(result.output.strip())
        except (ValueError, TypeError):
            logger.warning("local download_files(%s) got non-base64 output", path)
            return file_download_response(path=path, content=None, error="file_not_found")
        return FileDownloadResponse(path=path, content=content, error=None)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                result = self.execute(self._upload_command(path, content))
            except AppError:
                # 中继级故障（离线/超时）不属于单文件错误，向上透传给统一错误处理
                raise
            except Exception:
                logger.exception("local upload_files(%s) failed", path)
                responses.append(file_upload_response(path=path, error="invalid_path"))
                continue
            responses.append(self._upload_response(path, result))
        return responses

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        # 覆盖协议默认（to_thread 同步版）：直接走 aexecute，避免事件循环桥接
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                result = await self.aexecute(self._upload_command(path, content))
            except AppError:
                raise
            except Exception:
                logger.exception("local aupload_files(%s) failed", path)
                responses.append(file_upload_response(path=path, error="invalid_path"))
                continue
            responses.append(self._upload_response(path, result))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                result = self.execute(self._download_command(path))
            except AppError:
                raise
            except Exception:
                logger.exception("local download_files(%s) failed", path)
                responses.append(
                    file_download_response(path=path, content=None, error="file_not_found")
                )
                continue
            responses.append(self._download_response(path, result))
        return responses

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        # 覆盖协议默认（to_thread 同步版）：直接走 aexecute，避免事件循环桥接
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                result = await self.aexecute(self._download_command(path))
            except AppError:
                raise
            except Exception:
                logger.exception("local adownload_files(%s) failed", path)
                responses.append(
                    file_download_response(path=path, content=None, error="file_not_found")
                )
                continue
            responses.append(self._download_response(path, result))
        return responses
