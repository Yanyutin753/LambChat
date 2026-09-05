"""executor Windows 分支：Job Object 生命周期（Linux 上经注入 ``_winapi`` 全量可测）。

测试策略：``platform._sys_platform`` 注入 ``win32`` + ``executor._winapi`` 替换为
记录调用序的假实现——真实子进程照跑（Linux shell），win32 API 调用面被完全接管：

- 调用序与参数：CreateJobObjectW → SetInformationJobObject(信息类 9 +
  仅 KILL_ON_JOB_CLOSE 标志) → OpenProcess(SET_QUOTA|TERMINATE, pid) →
  AssignProcessToJobObject → 进程句柄即关 → [超时: TerminateJobObject] → Job 句柄收尾关；
- 超时契约与 POSIX 完全一致（error=timeout / exit_code=None），假 terminate
  真杀 pid 以复验不会等满命令时长；
- 入 Job 失败：补杀子进程、双句柄不泄漏、异常上抛交 daemon 收敛；
- POSIX 回归：宿主为 posix 时 ``_winapi`` 零调用、start_new_session 路径不变；
- ctypes 结构体按 MS 文档字段序定义，x64 尺寸逐一锁死（64/48/144 防字段错位）。
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path

import pytest

import lambchat_sandbox.executor as executor_mod
from lambchat_sandbox import platform as plat
from lambchat_sandbox.executor import (
    IO_COUNTERS,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOBOBJECT_BASIC_LIMIT_INFORMATION,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOBOBJECT_INFO_CLASS_EXTENDED_LIMIT,
    PROCESS_SET_QUOTA,
    PROCESS_TERMINATE,
    Executor,
)

_EXECUTOR_PY = "client/lambchat_sandbox/executor.py"


def _source(path: str) -> str:
    """读文件原文；缺失返回空串，让断言（而非收集错误）暴露缺失。"""
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


class FakeWinApi:
    """executor._WinApi 的测试替身：按调用序记录 (函数名, 参数)。

    ``terminate_job_object`` 复刻真语义——击杀 Job 内全部进程：把经
    ``open_process`` 记录的 pid 真杀（Linux 上 SIGKILL），使超时路径的
    ``_reap`` 立即返回、测试能断言"不等满命令时长"。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._next_handle = 0x1000
        self._pid_by_process_handle: dict[int, int] = {}

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def args_of(self, name: str) -> list[tuple]:
        return [args for n, args in self.calls if n == name]

    def _new_handle(self) -> int:
        self._next_handle += 1
        return self._next_handle

    def create_job_object(self) -> int:
        handle = self._new_handle()
        self.calls.append(("create_job_object", ()))
        return handle

    def set_information_job_object(
        self, job: int, info_class: int, info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    ) -> None:
        self.calls.append(("set_information_job_object", (job, info_class, info)))

    def open_process(self, desired_access: int, pid: int) -> int:
        handle = self._new_handle()
        self._pid_by_process_handle[handle] = pid
        self.calls.append(("open_process", (desired_access, pid)))
        return handle

    def assign_process_to_job_object(self, job: int, process: int) -> None:
        self.calls.append(("assign_process_to_job_object", (job, process)))

    def terminate_job_object(self, job: int, exit_code: int) -> None:
        for pid in self._pid_by_process_handle.values():
            try:
                os.kill(pid, 9)
            except (ProcessLookupError, PermissionError):
                pass
        self.calls.append(("terminate_job_object", (job, exit_code)))

    def close_handle(self, handle: int) -> None:
        self.calls.append(("close_handle", (handle,)))


@pytest.fixture
def win32(monkeypatch: pytest.MonkeyPatch) -> FakeWinApi:
    """伪造 win32 宿主 + 注入假 winapi；返回假实现供断言。"""
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    fake = FakeWinApi()
    monkeypatch.setattr(executor_mod, "_winapi", fake)
    return fake


# ---------------------------------------------------------------------------
# 正常路径：Job Object 生命周期调用序与参数
# ---------------------------------------------------------------------------


def test_win_execute_job_object_lifecycle_order(tmp_path: Path, win32: FakeWinApi) -> None:
    res = Executor(tmp_path).execute("echo hello", "/workspace/s1", timeout=15)
    assert res["status"] == "ok"
    assert res["stdout"] == "hello\n"
    assert res["error"] is None

    names = win32.names()
    assert names[0] == "create_job_object"
    assert names[1] == "set_information_job_object"
    assert names[2] == "open_process"
    assert names[3] == "assign_process_to_job_object"
    assert names[4] == "close_handle"  # 进程句柄用完即关（Job 句柄必须保留）
    assert names[-1] == "close_handle"  # 收尾关 Job 句柄（触发 KILL_ON_JOB_CLOSE 的钥匙）
    assert names.count("close_handle") == 2
    assert "terminate_job_object" not in names

    # 参数：Set 用信息类 9、LimitFlags 恰为 KILL_ON_JOB_CLOSE（不多设其他限制）
    job = win32.args_of("set_information_job_object")[0][0]
    set_args = win32.args_of("set_information_job_object")[0]
    assert set_args[1] == JOBOBJECT_INFO_CLASS_EXTENDED_LIMIT == 9
    info = set_args[2]
    assert isinstance(info, JOBOBJECT_EXTENDED_LIMIT_INFORMATION)
    assert info.BasicLimitInformation.LimitFlags == JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

    # OpenProcess：SET_QUOTA|TERMINATE 权限 + 真实子进程 pid（非本进程）
    access, pid = win32.args_of("open_process")[0]
    assert access == PROCESS_SET_QUOTA | PROCESS_TERMINATE == 0x101
    assert isinstance(pid, int) and pid > 1
    assert pid != os.getpid()

    # Assign：入 Job 的正是 OpenProcess 拿到的句柄；随后该进程句柄被关、Job 收尾再关
    assign_args = win32.args_of("assign_process_to_job_object")[0]
    process_handle = assign_args[1]
    assert assign_args == (job, process_handle)
    assert win32.args_of("close_handle") == [(process_handle,), (job,)]


def test_win_execute_nonzero_exit_still_completes_lifecycle(
    tmp_path: Path, win32: FakeWinApi
) -> None:
    res = Executor(tmp_path).execute("echo oops >&2; exit 3", "/workspace/s1", timeout=15)
    assert res["status"] == "error"
    assert res["exit_code"] == 3
    assert win32.names()[-1] == "close_handle"  # 非零退出同样收尾关 Job
    assert "terminate_job_object" not in win32.names()


# ---------------------------------------------------------------------------
# 超时：TerminateJobObject 击杀整个 Job，契约与 POSIX 一致
# ---------------------------------------------------------------------------


def test_win_execute_timeout_terminates_job(tmp_path: Path, win32: FakeWinApi) -> None:
    start = time.monotonic()
    res = Executor(tmp_path).execute("sleep 5", "/workspace/s1", timeout=0.3)
    elapsed = time.monotonic() - start
    assert res["status"] == "error"
    assert res["error"] == "timeout"
    assert res["exit_code"] is None
    # 假 terminate 真杀了 pid：_reap 立即返回，绝不等满 sleep 5
    assert elapsed < 3, f"execute 等 {elapsed:.1f}s 才返回，Job 未被击杀"

    names = win32.names()
    job_handle = win32.args_of("assign_process_to_job_object")[0][0]
    term_args = win32.args_of("terminate_job_object")[0]
    assert term_args[0] == job_handle, "击杀的必须是 Assign 时用的同一个 Job"
    assert term_args[1] != 0  # 非零退出码
    term_idx = names.index("terminate_job_object")
    assert term_idx > names.index("assign_process_to_job_object")
    assert term_idx < len(names) - 1  # terminate 之后还有收尾 close_handle(job)
    assert names[-1] == "close_handle"


def test_win_execute_timeout_partial_output_surfaces(tmp_path: Path, win32: FakeWinApi) -> None:
    res = Executor(tmp_path).execute("echo part; sleep 5", "/workspace/s1", timeout=0.5)
    assert res["error"] == "timeout"
    # TimeoutExpired 携带的部分输出进入结果（POSIX 同款 _partial/_tail 路径）
    assert "part" in res["stdout"]


# ---------------------------------------------------------------------------
# 入 Job 失败：补杀子进程、句柄不泄漏、异常上抛
# ---------------------------------------------------------------------------


def test_win_execute_assign_failure_kills_child_and_leaks_no_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeWinApi()
    monkeypatch.setattr(plat, "_sys_platform", "win32")
    monkeypatch.setattr(executor_mod, "_winapi", fake)

    def _boom(job: int, process: int) -> None:
        raise OSError("process already in another job")

    fake.assign_process_to_job_object = _boom

    start = time.monotonic()
    with pytest.raises(OSError, match="already in another job"):
        Executor(tmp_path).execute("sleep 5", "/workspace/s1", timeout=10)
    elapsed = time.monotonic() - start
    # 入 Job 失败后子进程被补杀：不等满 sleep 5
    assert elapsed < 3, f"execute 等 {elapsed:.1f}s 才返回，失败路径子进程泄漏"
    # 双句柄都关了（进程句柄在 assign 的 finally、Job 句柄在外层 finally）
    closes = fake.args_of("close_handle")
    assert len(closes) == 2
    assert {args[0] for args in closes} == {0x1001, 0x1002}, "进程句柄与 Job 句柄都必须各关一次"


# ---------------------------------------------------------------------------
# POSIX 回归：宿主为 posix 时 winapi 零调用、start_new_session 路径不变
# ---------------------------------------------------------------------------


def test_posix_execute_never_touches_winapi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeWinApi()
    monkeypatch.setattr(plat, "_sys_platform", "linux")
    monkeypatch.setattr(executor_mod, "_winapi", fake)
    res = Executor(tmp_path).execute("echo hi", "/workspace/s1", timeout=10)
    assert res["status"] == "ok"
    assert fake.calls == [], "POSIX 路径绝不能触碰 winapi"


@pytest.mark.skipif(sys.platform == "win32", reason="非 Windows 宿主上 _winapi 恒为 None")
def test_module_winapi_is_none_off_windows() -> None:
    assert executor_mod._winapi is None
    # 真实 _WinApi 在非 Windows 构造即拒绝：防止绕过注入直接用
    with pytest.raises(OSError):
        executor_mod._WinApi()


def test_executor_source_locks_platform_split() -> None:
    src = _source(_EXECUTOR_PY)
    # 平台分支经 platform.is_windows()（可注入判定），POSIX 路径原样保留
    assert "if plat.is_windows():" in src
    assert "start_new_session=True" in src  # POSIX 路径原样保留
    # Windows 方法体（_execute_windows 起、_reap 止）绝不出现 POSIX 专属实参
    # （docstring 里提及参数名不算——锁 kwarg 形态 "start_new_session="）
    win_section = src.split("def _execute_windows", 1)[1].split("def _reap", 1)[0]
    assert "start_new_session=" not in win_section
    # 超时击杀两侧对仗：killpg（POSIX）↔ terminate_job_object（Windows）
    assert "os.killpg" in src
    assert "terminate_job_object" in src


# ---------------------------------------------------------------------------
# ctypes 结构体：MS 文档字段序 + x64 尺寸锁（错位即 SetInformationJobObject 失败）
# ---------------------------------------------------------------------------


def test_job_struct_field_order_matches_ms_docs() -> None:
    assert [f[0] for f in IO_COUNTERS._fields_] == [
        "ReadOperationCount",
        "WriteOperationCount",
        "OtherOperationCount",
        "ReadTransferCount",
        "WriteTransferCount",
        "OtherTransferCount",
    ]
    assert [f[0] for f in JOBOBJECT_BASIC_LIMIT_INFORMATION._fields_] == [
        "PerProcessUserTimeLimit",
        "PerJobUserTimeLimit",
        "LimitFlags",
        "MinimumWorkingSetSize",
        "MaximumWorkingSetSize",
        "ActiveProcessLimit",
        "Affinity",
        "PriorityClass",
        "SchedulingClass",
    ]
    assert [f[0] for f in JOBOBJECT_EXTENDED_LIMIT_INFORMATION._fields_] == [
        "BasicLimitInformation",
        "IoInfo",
        "ProcessMemoryLimit",
        "JobMemoryLimit",
        "PeakProcessMemoryUsed",
        "PeakJobMemoryUsed",
    ]


@pytest.mark.skipif(ctypes.sizeof(ctypes.c_void_p) != 8, reason="x64 指针尺寸下的布局锁")
def test_job_struct_sizes_match_windows_x64_layout() -> None:
    # winnt.h 三结构在 x64 的原生尺寸：字段序/对齐错位会直接改变 sizeof
    assert ctypes.sizeof(JOBOBJECT_BASIC_LIMIT_INFORMATION) == 64
    assert ctypes.sizeof(IO_COUNTERS) == 48
    assert ctypes.sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION) == 144


def test_job_constants_match_windows_sdk_values() -> None:
    # winnt.h / winbase.h 原值：写死防手滑
    assert JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE == 0x00002000
    assert JOBOBJECT_INFO_CLASS_EXTENDED_LIMIT == 9  # JOBOBJECTINFOCLASS 成员序
    assert PROCESS_TERMINATE == 0x0001
    assert PROCESS_SET_QUOTA == 0x0100
