"""本地命令执行器：虚拟工作区映射 + 受控子进程执行。

daemon 收到 ``op=exec`` 的 tool_call 后经此执行：

- **工作区映射**：虚拟 cwd ``/workspace/{sid}`` 唯一映射到 ``data_root/{sid}``；
  非法路径（非 ``/workspace/`` 前缀、含 ``..``、sid 含 ``/`` 或为空）抛
  :class:`ExecutorError`，绝不落到 data_root 之外；
- **隔离执行**：``shell=True`` + ``start_new_session=True``（子进程自成会话与
  进程组，与 daemon 脱钩），cwd 即映射后的工作区（mkdir -p）；
- **超时杀组**：超时对整个进程组 ``os.killpg`` 补 SIGKILL——shell 的后台孙进程
  与 shell 同组，只杀直接子进程会漏杀；
- **输出截断**：stdout/stderr 各保留尾部 :data:`MAX_OUTPUT_BYTES` 字节，被截断时
  头部加 :data:`TRUNCATED_MARK` 标记。

结果契约（dict，daemon 直接作为 done payload 回传）::

    {"status": "ok" | "error", "stdout": str, "stderr": str,
     "exit_code": int | None, "error": str | None}

``status`` 镜像命令结局：exit_code == 0 为 ok，非零或超时为 error；超时时
``error="timeout"``、``exit_code=None``（进程被 SIGKILL，退出码未确定——协议约定
缺失透传 None，不伪装成 0）。
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from pathlib import Path

MAX_OUTPUT_BYTES = 256 * 1024
TRUNCATED_MARK = "...[truncated]"

_WORKSPACE_PREFIX = "/workspace/"


class ExecutorError(Exception):
    """虚拟工作区路径非法。"""


def map_workspace(virtual_cwd: str, data_root: Path) -> Path:
    """虚拟 cwd → data_root 下会话目录的纯映射；非法路径抛 ExecutorError。

    合法形态严格为 ``/workspace/{sid}``：sid 非空、不含 ``/``（子目录即拒绝）、
    不是 ``.``/``..``（防上溯）。只做映射，不创建目录。
    """
    if not virtual_cwd.startswith(_WORKSPACE_PREFIX):
        raise ExecutorError(f"virtual_cwd 必须以 {_WORKSPACE_PREFIX} 开头: {virtual_cwd!r}")
    sid = virtual_cwd[len(_WORKSPACE_PREFIX) :]
    if not sid or "/" in sid or sid in (".", ".."):
        raise ExecutorError(f"非法会话路径: {virtual_cwd!r}")
    return Path(data_root) / sid


class Executor:
    """在 data_root 会话目录里执行 shell 命令的受控执行器。"""

    def __init__(self, data_root: Path) -> None:
        self._data_root = Path(data_root)

    def execute(self, command: str, virtual_cwd: str, timeout: float) -> dict:
        """执行 command，返回 {status, stdout, stderr, exit_code, error}。"""
        workspace = map_workspace(virtual_cwd, self._data_root)
        workspace.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # 子进程自成会话：pgid == pid，超时可整组击杀
        )
        try:
            stdout_b, stderr_b = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            # communicate 超时只抛异常、不杀任何进程；这里对整个进程组补 SIGKILL
            # （shell 的孙进程同组），随后关闭管道、只回收直接子进程——绝不重读
            # 管道，避免个别脱组的管道持有者把 execute 拖死。
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(proc.pid, signal.SIGKILL)
            _reap(proc)
            return {
                "status": "error",
                "stdout": _tail(_partial(exc.stdout)),
                "stderr": _tail(_partial(exc.stderr)),
                "exit_code": None,
                "error": "timeout",
            }
        exit_code = proc.returncode
        return {
            "status": "ok" if exit_code == 0 else "error",
            "stdout": _tail(stdout_b),
            "stderr": _tail(stderr_b),
            "exit_code": exit_code,
            "error": None,
        }


def _reap(proc: subprocess.Popen) -> None:
    """关闭管道并回收子进程（不读内容；调用前须已 killpg）。"""
    if proc.stdout is not None:
        proc.stdout.close()
    if proc.stderr is not None:
        proc.stderr.close()
    proc.wait()


def _partial(data: bytes | str | None) -> bytes:
    """超时异常携带的输出在 POSIX 为 bytes、Windows 为 str，统一为 bytes。"""
    if data is None:
        return b""
    if isinstance(data, str):
        return data.encode("utf-8", errors="replace")
    return data


def _tail(data: bytes) -> str:
    """超过 MAX_OUTPUT_BYTES 时保留尾部并加头部标记；UTF-8 容错解码。"""
    if len(data) <= MAX_OUTPUT_BYTES:
        return data.decode("utf-8", errors="replace")
    return TRUNCATED_MARK + data[-MAX_OUTPUT_BYTES:].decode("utf-8", errors="replace")
