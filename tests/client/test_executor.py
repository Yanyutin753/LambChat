"""Executor：虚拟工作区映射 + 真实子进程执行（超时杀组 / 输出尾部截断）。

全部走真实子进程（shell=True），不做 subprocess mock：
- 映射：``/workspace/{sid}`` → ``data_root/sid``；非法路径（非 /workspace/ 前缀、
  含 ``..``、sid 含 ``/``、sid 为空）抛 ExecutorError；
- cwd：``pwd`` 落在映射后的工作区，写入文件落在 ``data_root/sid`` 下；
  ``cd ..`` 可到 data_root（M2 接受无 jail，治理留给 M3 HITL，这里只锁映射正确性）；
- 超时：``os.killpg`` 杀整个进程组（含 shell 的后台孙进程，用 /proc 状态验证）；
- 截断：stdout/stderr 各保留尾部 256KB，头部加 ``...[truncated]`` 标记。
"""

from __future__ import annotations

import os
import shlex
import sys
import time
from pathlib import Path

import pytest

from lambchat_sandbox.executor import (
    MAX_OUTPUT_BYTES,
    TRUNCATED_MARK,
    Executor,
    ExecutorError,
    map_workspace,
)

# ---------------------------------------------------------------------------
# map_workspace：纯映射函数
# ---------------------------------------------------------------------------


def test_map_workspace_maps_sid_under_data_root(tmp_path):
    assert map_workspace("/workspace/s1", tmp_path) == tmp_path / "s1"


def test_map_workspace_rejects_non_workspace_prefix(tmp_path):
    with pytest.raises(ExecutorError):
        map_workspace("/etc", tmp_path)


def test_map_workspace_rejects_parent_escape(tmp_path):
    with pytest.raises(ExecutorError):
        map_workspace("/workspace/../etc", tmp_path)


def test_map_workspace_rejects_dotted_sid(tmp_path):
    with pytest.raises(ExecutorError):
        map_workspace("/workspace/..", tmp_path)


def test_map_workspace_rejects_sid_containing_slash(tmp_path):
    with pytest.raises(ExecutorError):
        map_workspace("/workspace/a/b", tmp_path)


def test_map_workspace_rejects_prefix_without_sid(tmp_path):
    with pytest.raises(ExecutorError):
        map_workspace("/workspace", tmp_path)


def test_map_workspace_rejects_empty_sid(tmp_path):
    with pytest.raises(ExecutorError):
        map_workspace("/workspace/", tmp_path)


# ---------------------------------------------------------------------------
# execute：真实子进程
# ---------------------------------------------------------------------------


def test_execute_echo_roundtrip(tmp_path):
    res = Executor(tmp_path).execute("echo hello", "/workspace/s1", timeout=10)
    assert res["status"] == "ok"
    assert res["exit_code"] == 0
    assert res["stdout"] == "hello\n"
    assert res["stderr"] == ""
    assert res["error"] is None


def test_execute_nonzero_exit_code_reports_error(tmp_path):
    res = Executor(tmp_path).execute("echo oops >&2; exit 3", "/workspace/s1", timeout=10)
    assert res["status"] == "error"
    assert res["exit_code"] == 3
    assert res["stderr"].strip() == "oops"


def test_execute_runs_in_mapped_workspace(tmp_path):
    res = Executor(tmp_path).execute("pwd", "/workspace/s42", timeout=10)
    assert res["stdout"].strip() == str((tmp_path / "s42").resolve())


def test_execute_creates_workspace_and_files_land_there(tmp_path):
    res = Executor(tmp_path).execute("echo data > f.txt", "/workspace/s9", timeout=10)
    assert res["status"] == "ok"
    assert (tmp_path / "s9" / "f.txt").read_text() == "data\n"


def test_execute_cd_up_lands_in_data_root_not_workspace(tmp_path):
    # M2 接受 shell cwd 即工作区、cd .. 可上溯：只锁落点在 data_root（jail 治理是 M3 HITL）
    res = Executor(tmp_path).execute("cd .. && pwd > parent.txt", "/workspace/s1", timeout=10)
    assert res["status"] == "ok"
    assert (tmp_path / "parent.txt").exists()
    assert not (tmp_path / "s1" / "parent.txt").exists()


def test_execute_rejects_illegal_virtual_cwd(tmp_path):
    with pytest.raises(ExecutorError):
        Executor(tmp_path).execute("pwd", "/etc", timeout=10)


# ---------------------------------------------------------------------------
# 超时：杀整个进程组
# ---------------------------------------------------------------------------


def test_execute_timeout_kills_process_and_returns_error(tmp_path):
    start = time.monotonic()
    res = Executor(tmp_path).execute("sleep 5", "/workspace/s1", timeout=0.3)
    elapsed = time.monotonic() - start
    assert res["status"] == "error"
    assert res["error"] == "timeout"
    assert res["exit_code"] is None
    # 远小于 sleep 时长：证明被杀，而非等满 5s
    assert elapsed < 4


def test_execute_timeout_kills_whole_process_group(tmp_path):
    # 后台孙进程持有 stdout 管道：只杀直接子进程（shell）时它会活满 30s，
    # 且 shell 自己也要等满 30s；killpg 杀组后两者立即死亡。
    cmd = "sleep 30 & echo $! > bg.pid; sleep 30"
    start = time.monotonic()
    res = Executor(tmp_path).execute(cmd, "/workspace/s1", timeout=0.5)
    elapsed = time.monotonic() - start
    assert res["error"] == "timeout"
    # 杀组是即时的：绝不能等满孙进程的 30s
    assert elapsed < 5, f"execute 等 {elapsed:.1f}s 才返回，进程组未被整组击杀"
    bg_pid = int((tmp_path / "s1" / "bg.pid").read_text().strip())
    assert _wait_until_dead(bg_pid), f"后台进程 {bg_pid} 在杀组后仍存活"


def _wait_until_dead(pid: int, deadline_s: float = 3.0) -> bool:
    """轮询 /proc 直到进程消失或成僵尸（僵尸 = 已被杀，只是未被收尸）。"""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
        except FileNotFoundError:
            return True  # 已被 init 回收
        state = stat.rsplit(")", 1)[1].split()[0]
        if state in {"Z", "X"}:
            return True  # 僵尸/死亡：已被 SIGKILL
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# 输出截断：stdout/stderr 各保留尾部 256KB
# ---------------------------------------------------------------------------


def _python_stdout_cmd(emit_expr: str) -> str:
    """构造 `python -c "sys.stdout.write(<emit_expr>)"`（emit_expr 内联生成大输出）。"""
    code = f"import sys; sys.stdout.write({emit_expr})"
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def test_execute_truncates_oversized_stdout_keeps_tail(tmp_path):
    cmd = _python_stdout_cmd(f"'x' * {300 * 1024} + 'TAIL'")
    res = Executor(tmp_path).execute(cmd, "/workspace/s1", timeout=30)
    assert res["status"] == "ok"
    assert res["stdout"].startswith(TRUNCATED_MARK)
    assert res["stdout"].endswith("TAIL")
    assert len(res["stdout"]) == len(TRUNCATED_MARK) + MAX_OUTPUT_BYTES


def test_execute_truncates_stderr_independently(tmp_path):
    payload = f"'e' * {300 * 1024} + 'ETAIL'"
    cmd = _python_stdout_cmd(payload).replace("sys.stdout.write", "sys.stderr.write")
    res = Executor(tmp_path).execute(cmd, "/workspace/s1", timeout=30)
    assert res["status"] == "ok"
    assert res["stdout"] == ""
    assert res["stderr"].startswith(TRUNCATED_MARK)
    assert res["stderr"].endswith("ETAIL")
    assert len(res["stderr"]) == len(TRUNCATED_MARK) + MAX_OUTPUT_BYTES


def test_execute_output_at_limit_is_not_truncated(tmp_path):
    cmd = _python_stdout_cmd(f"'a' * {MAX_OUTPUT_BYTES}")
    res = Executor(tmp_path).execute(cmd, "/workspace/s1", timeout=30)
    assert res["stdout"] == "a" * MAX_OUTPUT_BYTES  # 恰好 256KB：不加截断标记


# ---------------------------------------------------------------------------
# extra_path（M4 T4：内嵌 Python bin 目录前置进子进程 PATH）
# ---------------------------------------------------------------------------


def test_execute_prepends_extra_path_to_subprocess_path(tmp_path):
    """extra_path 目录成为子进程 PATH 首段（内嵌 Python 经此命中）。"""
    bin_dir = tmp_path / "embedded-bin"
    bin_dir.mkdir()
    res = Executor(tmp_path, extra_path=bin_dir).execute("echo $PATH", "/workspace/s1", timeout=15)
    assert res["status"] == "ok"
    assert res["stdout"].strip().split(os.pathsep)[0] == str(bin_dir)


def test_execute_without_extra_path_keeps_inherited_path(tmp_path):
    """不传 extra_path：子进程 PATH 保持继承（首段绝不是随意注入的目录）。"""
    injected = tmp_path / "not-in-path"
    res = Executor(tmp_path).execute("echo $PATH", "/workspace/s1", timeout=15)
    assert res["status"] == "ok"
    assert str(injected) not in res["stdout"]


def test_execute_extra_path_shim_wins_over_system_python3(tmp_path):
    """PATH 前置后 shell 解析 python3 命中 shim：假解释器输出哨兵串。"""
    bin_dir = tmp_path / "embedded-bin"
    bin_dir.mkdir()
    shim = bin_dir / "python3"
    shim.write_text('#!/bin/sh\necho EMBEDDED-HIT "$0"\n', encoding="utf-8")
    shim.chmod(0o755)
    res = Executor(tmp_path, extra_path=bin_dir).execute(
        "python3 -c 'x'", "/workspace/s1", timeout=15
    )
    assert res["status"] == "ok"
    assert res["stdout"].startswith("EMBEDDED-HIT")


def test_spawn_env_is_none_without_extra_path(tmp_path):
    """env=None → Popen 继承父环境（embedded_python=false 的零开销路径）。"""
    assert Executor(tmp_path)._spawn_env() is None


def test_spawn_env_prepends_extra_path(tmp_path):
    env = Executor(tmp_path, extra_path=tmp_path / "b")._spawn_env()
    assert env is not None
    assert env["PATH"].split(os.pathsep)[0] == str(tmp_path / "b")
    # 其余环境变量原样保留
    assert env.get("HOME") == os.environ.get("HOME")
