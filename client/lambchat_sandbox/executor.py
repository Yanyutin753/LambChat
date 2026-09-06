"""本地命令执行器：虚拟工作区映射 + 受控子进程执行。

daemon 收到 ``op=exec`` 的 tool_call 后经此执行：

- **工作区映射**：虚拟 cwd ``/workspace/{sid}`` 唯一映射到 ``data_root/{sid}``；
  非法路径（非 ``/workspace/`` 前缀、含 ``..``、sid 含 ``/`` 或为空）抛
  :class:`ExecutorError`，绝不落到 data_root 之外；
- **隔离执行**（平台分支，:func:`lambchat_sandbox.platform.is_windows`）：
  - POSIX：``shell=True`` + ``start_new_session=True``（子进程自成会话与
    进程组，与 daemon 脱钩），cwd 即映射后的工作区（mkdir -p）；
  - Windows：Job Object（``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``）圈住整棵
    进程树——daemon 持有 Job 句柄，daemon 意外死亡时最后一个句柄关闭、
    内核自动击杀 Job 内全部进程（对齐 PDEATHSIG 的"父亡子死"语义）；
- **超时杀树**：POSIX 对整个进程组 ``os.killpg`` 补 SIGKILL——shell 的后台
  孙进程与 shell 同组，只杀直接子进程会漏杀；Windows
  ``TerminateJobObject`` 一次击杀 Job 内所有进程，语义对仗；
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
import ctypes
import os
import signal
import subprocess
from pathlib import Path

from lambchat_sandbox import platform as plat

MAX_OUTPUT_BYTES = 256 * 1024
TRUNCATED_MARK = "...[truncated]"

_WORKSPACE_PREFIX = "/workspace/"


class ExecutorError(Exception):
    """虚拟工作区路径非法。"""


# ---------------------------------------------------------------------------
# Windows Job Object：整棵进程树的隔离与击杀（POSIX 走 start_new_session+killpg）
#
# 结构体字段序/常量原值出处（learn.microsoft.com）：
# - JOBOBJECT_BASIC_LIMIT_INFORMATION:
#   windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information
# - IO_COUNTERS:                    windows/win32/api/winnt/ns-winnt-io_counters
# - JOBOBJECT_EXTENDED_LIMIT_INFORMATION:
#   windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information
# - JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE（winnt.h）：Causes all processes to be
#   terminated when the job's last handle is closed
# - JOBOBJECTINFOCLASS 枚举（winbase.h）：JobObjectExtendedLimitInformation = 9
# - OpenProcess 权限（processthreadsapi.h）：进程加入 Job 需 PROCESS_SET_QUOTA；
#   兜底单杀需 PROCESS_TERMINATE
# ---------------------------------------------------------------------------

#: winnt.h ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``：Job 最后一个句柄关闭时
#: 内核自动击杀 Job 内全部进程——daemon 意外死亡即整树陪葬（对齐 PDEATHSIG）。
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

#: winbase.h ``JOBOBJECTINFOCLASS`` 枚举成员序：SetInformationJobObject 的信息类。
JOBOBJECT_INFO_CLASS_EXTENDED_LIMIT = 9

#: processthreadsapi.h OpenProcess 权限位原值。
PROCESS_TERMINATE = 0x0001
PROCESS_SET_QUOTA = 0x0100

#: 超时击杀 Job 的退出码（任意非零即可；协议上 exit_code 仍透传 None）。
_JOB_TERMINATE_EXIT_CODE = 1


class IO_COUNTERS(ctypes.Structure):  # noqa: N801 - winnt.h 原名，保留便于对照头文件
    """winnt.h ``IO_COUNTERS``：六个 8 字节 ULONGLONG 计数器，字段序照抄文档。"""

    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):  # noqa: N801 - winnt.h 原名
    """winnt.h ``JOBOBJECT_BASIC_LIMIT_INFORMATION``（字段序照抄文档）。

    LARGE_INTEGER 按 8 字节 ``c_int64`` 定义（本用法只需清零，联合体另一半
    不参与布局）；SIZE_T/ULONG_PTR 按指针尺寸 ``c_size_t``；ctypes 原生对齐
    与 MSVC x64 布局一致（64 字节，测试锁死）。
    """

    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):  # noqa: N801 - winnt.h 原名
    """winnt.h ``JOBOBJECT_EXTENDED_LIMIT_INFORMATION``（字段序照抄文档）。"""

    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WinApi:
    """kernel32 Job Object API 的 ctypes 薄封装（方法与 win32 函数一一对应）。

    仅真实 Windows 宿主实例化（见模块尾 ``_winapi``）；失败抛
    :class:`OSError`（附 GetLastError）。测试通过 monkeypatch 替换模块级
    ``_winapi`` 注入假实现、断言调用序与参数——本类自身不进测试路径。
    """

    def __init__(self) -> None:
        windll = getattr(ctypes, "windll", None)  # Windows 独有（stdcall 加载器）
        if windll is None:
            raise OSError("Job Object API 仅 Windows 可用（ctypes.windll 缺失）")
        self._kernel32 = windll.kernel32

    def _fail(self, api: str) -> OSError:
        # get_last_error 是 Windows 专属 API（typeshed 不声明、本类也仅 Windows 执行）
        return OSError(f"{api} 失败: GetLastError={ctypes.get_last_error()}")  # type: ignore[attr-defined]

    def create_job_object(self) -> int:
        """``CreateJobObjectW(NULL, NULL)`` → 新 Job 句柄。"""
        fn = self._kernel32.CreateJobObjectW
        fn.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        fn.restype = ctypes.c_void_p
        handle = fn(None, None)
        if not handle:
            raise self._fail("CreateJobObjectW")
        return int(handle)

    def set_information_job_object(
        self, job: int, info_class: int, info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    ) -> None:
        """``SetInformationJobObject(job, 类, byref(info), sizeof(info))``。"""
        fn = self._kernel32.SetInformationJobObject
        fn.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        fn.restype = ctypes.c_int  # BOOL
        if not fn(job, info_class, ctypes.byref(info), ctypes.sizeof(info)):
            raise self._fail("SetInformationJobObject")

    def open_process(self, desired_access: int, pid: int) -> int:
        """``OpenProcess(access, FALSE, pid)`` → 进程句柄。

        不用 ``Popen._handle``：那是 CPython 实现细节，跨版本稳定性差；
        OpenProcess 是公开契约（Assign 进程需要 SET_QUOTA 权限）。
        """
        fn = self._kernel32.OpenProcess
        fn.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        fn.restype = ctypes.c_void_p
        handle = fn(desired_access, False, pid)
        if not handle:
            raise self._fail("OpenProcess")
        return int(handle)

    def assign_process_to_job_object(self, job: int, process: int) -> None:
        """``AssignProcessToJobObject(job, process)``：进程（及此后代）入 Job。"""
        fn = self._kernel32.AssignProcessToJobObject
        fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        fn.restype = ctypes.c_int  # BOOL
        if not fn(job, process):
            raise self._fail("AssignProcessToJobObject")

    def terminate_job_object(self, job: int, exit_code: int) -> None:
        """``TerminateJobObject(job, exit_code)``：击杀 Job 内全部进程。"""
        fn = self._kernel32.TerminateJobObject
        fn.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        fn.restype = ctypes.c_int  # BOOL
        if not fn(job, exit_code):
            raise self._fail("TerminateJobObject")

    def close_handle(self, handle: int) -> None:
        """``CloseHandle``：关 Job 句柄即引爆 KILL_ON_JOB_CLOSE；关进程句柄防泄漏。"""
        fn = self._kernel32.CloseHandle
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_int  # BOOL
        if not fn(handle):
            raise self._fail("CloseHandle")


# 模块级可注入的 win32 API 面：真实宿主仅 Windows 构造，其余平台为 None
# （Windows 分支必经 is_windows() 门控；测试 monkeypatch 本变量注入假实现）。
_winapi: _WinApi | None = _WinApi() if plat.is_windows() else None


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
    """在 data_root 会话目录里执行 shell 命令的受控执行器。

    ``extra_path``（M4 T4）：内嵌 Python 的 shim bin 目录——前置进全部子进程
    PATH，使命令里的 ``python3`` 命中内嵌解释器而非用户系统安装。``None``
    （embedded_python=false / 装配回退）时 Popen 不传 env，完全继承父环境。
    """

    def __init__(self, data_root: Path, extra_path: Path | None = None) -> None:
        self._data_root = Path(data_root)
        self._extra_path = Path(extra_path) if extra_path is not None else None

    def _spawn_env(
        self,
        workspace: Path | None = None,
        env_extra: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        """构建子进程环境，落笔顺序固定：PYTHONIOENCODING 默认 → 用户 env →
        PATH shim 前置 → LAMBCHAT_WORKSPACE（契约变量最后写，不被用户 env
        覆盖——PATH 被覆盖会破坏内嵌 python3 shim 的解析）。

        - ``PYTHONIOENCODING`` 默认钉 utf-8（用户 env / 继承环境显式给出时
          尊重原值）：子进程 Python 的 stdio 输出 UTF-8，executor 的解码链
          原样命中，脚本 print 中文不再吐 GBK（cmd.exe 自身消息仍是 GBK，
          由解码链兜底）；
        - ``env_extra``：服务端下发的用户 env 变量（对齐云端 envs= 语义，
          来自用户加密存储，EnvVarStorage 已限 50 个/单值 16k/总量 64k）；
        - ``extra_path`` 前置进 PATH（内嵌 Python shim 目录）；
        - ``workspace`` 非空时注入 LAMBCHAT_WORKSPACE（指向映射后的真实
          工作区目录——云端沙箱在每条命令前 export 同名变量，系统提示词
          据此让模型用 $LAMBCHAT_WORKSPACE；本地链路由这里等效提供，否则
          模型生成的 `"$LAMBCHAT_WORKSPACE/x"` 展开为 /x 而失败）。
        """
        if self._extra_path is None and workspace is None and not env_extra:
            return None
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        if env_extra:
            env.update(env_extra)
        if self._extra_path is not None:
            path = env.get("PATH", "")
            env["PATH"] = (
                os.pathsep.join([str(self._extra_path), path]) if path else str(self._extra_path)
            )
        if workspace is not None:
            env["LAMBCHAT_WORKSPACE"] = str(workspace)
            env["LAMBCHAT_SHARED"] = str(self._data_root / ".shared")
        return env

    def execute(
        self,
        command: str,
        virtual_cwd: str,
        timeout: float,
        env_extra: dict[str, str] | None = None,
    ) -> dict:
        """执行 command，返回 {status, stdout, stderr, exit_code, error}。

        ``env_extra``：服务端下发的用户 env（仅 exec op 携带），合并进子进程
        环境（合并序见 :meth:`_spawn_env`）。
        """
        workspace = map_workspace(virtual_cwd, self._data_root)
        workspace.mkdir(parents=True, exist_ok=True)
        # 共享目录（LAMBCHAT_SHARED 指向处）随首次执行一并建好——跨会话持久，
        # 之后任意会话的重定向 `$LAMBCHAT_SHARED/…` 不会再因目录缺失而失败。
        (self._data_root / ".shared").mkdir(parents=True, exist_ok=True)
        if plat.is_windows():
            return self._execute_windows(command, workspace, timeout, env_extra)
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # 子进程自成会话：pgid == pid，超时可整组击杀
            env=self._spawn_env(workspace, env_extra),
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

    def _execute_windows(
        self,
        command: str,
        workspace: Path,
        timeout: float,
        env_extra: dict[str, str] | None = None,
    ) -> dict:
        """Windows 路径：Job Object 圈住整棵进程树（KILL_ON_JOB_CLOSE）。

        生命周期：CreateJobObjectW → Set（KILL_ON_JOB_CLOSE）→ Popen（不传
        ``start_new_session``，POSIX 专属参数）→ OpenProcess(pid) → Assign →
        关进程句柄（Job 句柄留到收尾）→ [超时 TerminateJobObject] → 关 Job 句柄。
        shell=True 走 cmd.exe：cmd 及其全部后代默认随父入 Job（未设 breakaway），
        对齐 POSIX"孙进程同组"的击杀覆盖面。

        已知窄窗：Popen 到 Assign 之间子进程若抢先再 spawn 孙进程，孙进程不
        在 Job 内（POSIX 的 start_new_session 在 exec 前生效、无此竞窗）——窗口
        为毫秒级且仅影响极端抢跑场景，真机验证项记录于 M4 任务报告。
        """
        winapi = _winapi
        assert winapi is not None  # 仅经 is_windows() 分支进入（mypy 收窄）
        job = winapi.create_job_object()
        try:
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            winapi.set_information_job_object(job, JOBOBJECT_INFO_CLASS_EXTENDED_LIMIT, info)
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._spawn_env(workspace, env_extra),
            )
            try:
                process = winapi.open_process(PROCESS_SET_QUOTA | PROCESS_TERMINATE, proc.pid)
                try:
                    winapi.assign_process_to_job_object(job, process)
                finally:
                    winapi.close_handle(process)
            except OSError:
                # 未入 Job（OpenProcess 失败，或进程已在别的 Job 且不许
                # breakaway）：KILL_ON_JOB_CLOSE 罩不住它，补杀再上抛防泄漏。
                proc.kill()
                _reap(proc)
                raise
            try:
                stdout_b, stderr_b = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                # 与 POSIX 对仗：communicate 超时不杀进程，这里击杀 Job 内全部
                # 进程（= 进程组语义），随后关管道、回收直接子进程、不重读管道。
                winapi.terminate_job_object(job, _JOB_TERMINATE_EXIT_CODE)
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
        finally:
            # 收尾关 Job 句柄：进程树正常退完即释放内核对象；若仍有存活成员，
            # 这一步就是 KILL_ON_JOB_CLOSE 的击杀钥匙。
            winapi.close_handle(job)


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


# 输出解码链（2026-09-06 Windows 真机事故）：cmd.exe 与本地工具在中文
# Windows 输出 GBK（CP936），一律按 UTF-8 容错解码会把「信息: ...」变成
# 乱码喂给模型。先按 UTF-8 严格解码（绝大多数子进程输出），失败再试 GBK
# （中文 Windows 控制台码页），最终退化为 UTF-8 replace（二进制垃圾）。
_DECODE_FALLBACKS = ("gbk",)


def _decode_output(data: bytes) -> str:
    """按解码链把子进程输出字节转文本：UTF-8 → GBK → UTF-8 replace。"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for encoding in _DECODE_FALLBACKS:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _tail(data: bytes) -> str:
    """超过 MAX_OUTPUT_BYTES 时保留尾部并加头部标记；经解码链容错解码。"""
    if len(data) <= MAX_OUTPUT_BYTES:
        return _decode_output(data)
    return TRUNCATED_MARK + _decode_output(data[-MAX_OUTPUT_BYTES:])
