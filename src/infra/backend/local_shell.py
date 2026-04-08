"""Local Shell 沙箱后端

借鉴 Xpert 的 LocalShellSandbox 方案，在宿主机本地执行命令。
零外部依赖，纯 Python 标准库实现，适合自部署场景。

特性：
- 直接在宿主机子进程中执行命令
- 文件操作通过 BaseSandbox 的 shell 命令模板实现
- 用户隔离：每个用户一个工作目录
- 支持超时控制和流式输出
"""

import asyncio
import os
import shlex
import uuid
from typing import Callable

from deepagents.backends.protocol import ExecuteResponse
from deepagents.backends.sandbox import BaseSandbox

from src.infra.logging import get_logger

logger = get_logger(__name__)

# 默认命令超时 5 分钟
_DEFAULT_TIMEOUT = 5 * 60

# 默认最大输出字节（4MB）
_DEFAULT_MAX_OUTPUT = 4 * 1024 * 1024


class LocalShellBackend(BaseSandbox):
    """本地 Shell 沙箱后端

    在宿主机上通过 subprocess 执行命令，文件操作通过 BaseSandbox
    的 execute() → shell 命令模板自动实现。

    每个用户有独立的工作目录，实现基本隔离。
    """

    def __init__(
        self,
        work_dir: str,
        timeout: int = _DEFAULT_TIMEOUT,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT,
        sandbox_id: str | None = None,
    ):
        """
        Args:
            work_dir: 工作目录（命令在此目录下执行）
            timeout: 命令超时时间（秒）
            max_output_bytes: 最大输出字节数
            sandbox_id: 沙箱 ID（默认自动生成）
        """
        self._work_dir = os.path.abspath(work_dir)
        self._timeout = timeout
        self._max_output_bytes = max_output_bytes
        self._id = sandbox_id or f"local-{uuid.uuid4().hex[:12]}"

        # 确保工作目录存在
        os.makedirs(self._work_dir, exist_ok=True)

        logger.info(f"[LocalShellBackend] Created: id={self._id}, work_dir={self._work_dir}")

    @property
    def id(self) -> str:
        return self._id

    @property
    def work_dir(self) -> str:
        return self._work_dir

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """同步执行命令"""
        effective_timeout = timeout or self._timeout
        try:
            proc = __import__("subprocess").run(
                ["/bin/bash", "-c", command],
                cwd=self._work_dir,
                capture_output=True,
                timeout=effective_timeout,
                env={**os.environ},
            )
            output = ""
            if proc.stdout:
                output = proc.stdout.decode("utf-8", errors="replace")
            if proc.stderr:
                stderr = proc.stderr.decode("utf-8", errors="replace")
                output = f"{output}\n{stderr}" if output else stderr

            # 截断检查
            truncated = len(output.encode("utf-8")) > self._max_output_bytes
            if truncated:
                output = output[: self._max_output_bytes]

            return ExecuteResponse(
                output=output,
                exit_code=proc.returncode,
                truncated=truncated,
            )
        except __import__("subprocess").TimeoutExpired:
            return ExecuteResponse(
                output=f"Command timed out after {effective_timeout} seconds",
                exit_code=-1,
                truncated=False,
            )
        except Exception as e:
            return ExecuteResponse(
                output=f"Command execution failed: {e}",
                exit_code=-1,
                truncated=False,
            )

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """异步执行命令（不阻塞事件循环）"""
        effective_timeout = timeout or self._timeout
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.execute, command, timeout=timeout),
                timeout=effective_timeout + 5,  # 额外 5s 余量
            )
        except asyncio.TimeoutError:
            return ExecuteResponse(
                output=f"Command timed out after {effective_timeout} seconds (async)",
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
        """执行命令并实时流式输出 stdout/stderr"""
        import subprocess

        effective_timeout = timeout or self._timeout
        chunks: list[str] = []
        truncated = False
        total_bytes = 0

        try:
            proc = subprocess.Popen(
                ["/bin/bash", "-c", command],
                cwd=self._work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ},
            )

            # 读取 stdout
            if proc.stdout:
                for line in iter(proc.stdout.readline, b""):
                    text = line.decode("utf-8", errors="replace")
                    total_bytes += len(text.encode("utf-8"))
                    if total_bytes <= self._max_output_bytes:
                        chunks.append(text)
                    else:
                        truncated = True
                    if on_stdout:
                        on_stdout(text)

            # 读取 stderr
            if proc.stderr:
                for line in iter(proc.stderr.readline, b""):
                    text = line.decode("utf-8", errors="replace")
                    total_bytes += len(text.encode("utf-8"))
                    if total_bytes <= self._max_output_bytes:
                        chunks.append(text)
                    else:
                        truncated = True
                    if on_stderr:
                        on_stderr(text)

            try:
                exit_code = proc.wait(timeout=effective_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                return ExecuteResponse(
                    output=f"Command timed out after {effective_timeout} seconds",
                    exit_code=-1,
                    truncated=truncated,
                )

            output = "".join(chunks)
            return ExecuteResponse(
                output=output,
                exit_code=exit_code,
                truncated=truncated,
            )

        except Exception as e:
            return ExecuteResponse(
                output=f"Command execution failed: {e}",
                exit_code=-1,
                truncated=False,
            )

    def _ensure_parent_dir(self, file_path: str) -> None:
        """确保父目录存在"""
        parent = os.path.dirname(file_path)
        if not parent:
            return
        self.execute(f"mkdir -p {shlex.quote(parent)}")
