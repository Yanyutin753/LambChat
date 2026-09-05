"""procsup：父进程监视（Windows PDEATHSIG 的用户态替代）。

全部用真实线程 + 短命子进程当"假父"（pid 注入 ``pid_of``）验证：
- 判死双保险：pid_of 返回值变化（POSIX 孤儿被收养）**或** 快照 pid 消失
  （psutil.pid_exists，Windows 上 getppid 是静态快照、只能靠这条）都触发；
- exit_fn 恰好调用一次，触发后线程退出（不空转）；
- 父进程存活期间绝不误触发；
- ``__main__`` 仅在 Windows 挂载（Linux 已有 PDEATHSIG，不双挂）。
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

from lambchat_sandbox import procsup

# 结构断言用：仓库根相对 CWD（pytest 自仓库根跑，与 test_packaging.py 同法）
_MAIN_PY = "client/lambchat_sandbox/__main__.py"


def _source(path: str) -> str:
    """读文件原文；缺失返回空串，让断言（而非收集错误）暴露缺失。"""
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _spawn_fake_parent() -> subprocess.Popen:
    """起一个能活 60s 的子进程当"假父"；测试自行 kill/wait 制造父亡。"""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


class _ExitRecorder:
    """exit_fn 替身：记录调用次数，线程安全置 Event。"""

    def __init__(self) -> None:
        self.count = 0
        self.fired = threading.Event()

    def __call__(self) -> None:
        self.count += 1
        self.fired.set()


def test_watch_parent_fires_when_parent_pid_disappears() -> None:
    # Windows 语义场景：pid_of 恒返回同一 pid（getppid 静态快照），
    # 只能靠 psutil.pid_exists 判死 → 假父被杀并收尸后必须触发。
    parent = _spawn_fake_parent()
    try:
        recorder = _ExitRecorder()
        thread = procsup.watch_parent(recorder, poll_s=0.05, pid_of=lambda: parent.pid)
        parent.kill()
        parent.wait()  # 收尸：pid 从进程表消失（否则 pid_exists 仍为 True）
        assert recorder.fired.wait(5.0), "假父死亡后 exit_fn 未被调用"
        assert recorder.count == 1
        thread.join(2.0)
        assert not thread.is_alive()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()


def test_watch_parent_silent_while_parent_alive() -> None:
    # 父进程存活期间（≥5 个轮询周期）绝不误触发。
    parent = _spawn_fake_parent()
    try:
        recorder = _ExitRecorder()
        procsup.watch_parent(recorder, poll_s=0.05, pid_of=lambda: parent.pid)
        time.sleep(0.3)
        assert recorder.count == 0, "父进程仍存活时 exit_fn 被误调用"
    finally:
        parent.kill()
        parent.wait()


def test_watch_parent_fires_when_pid_of_value_changes() -> None:
    # POSIX 语义场景：getppid() 变化即原父死亡（孤儿被 init/subreaper 收养）。
    # 原父 pid 仍被占用（新进程顶替了该 pid 或父成僵尸）也必须触发。
    old_parent = _spawn_fake_parent()
    new_parent = _spawn_fake_parent()
    try:
        values = iter([old_parent.pid] * 3 + [new_parent.pid] * 1000)

        def pid_of() -> int:
            try:
                return next(values)
            except StopIteration:
                return new_parent.pid

        recorder = _ExitRecorder()
        procsup.watch_parent(recorder, poll_s=0.05, pid_of=pid_of)
        assert recorder.fired.wait(5.0), "pid_of 返回值变化（原父已死）未触发 exit_fn"
    finally:
        for proc in (old_parent, new_parent):
            proc.kill()
            proc.wait()


def test_watch_parent_exits_thread_after_single_invocation() -> None:
    # 父亡触发一次后线程必须退出：不会在下个周期重复调用 exit_fn。
    parent = _spawn_fake_parent()
    parent.kill()
    parent.wait()  # 启动前父已死：首个周期就应触发（无需先睡一个 poll_s）
    try:
        recorder = _ExitRecorder()
        thread = procsup.watch_parent(recorder, poll_s=0.05, pid_of=lambda: parent.pid)
        thread.join(5.0)
        assert not thread.is_alive(), "触发后线程未退出"
        time.sleep(0.2)  # 4 个周期：若线程未退出会重复调用
        assert recorder.count == 1
        assert not thread.is_alive()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()


def test_watch_parent_returns_daemon_thread() -> None:
    # daemon 线程：父进程监视绝不阻塞解释器退出（进程正常关停不靠它收尾）。
    parent = _spawn_fake_parent()
    try:
        thread = procsup.watch_parent(lambda: None, poll_s=0.1, pid_of=lambda: parent.pid)
        assert thread.daemon is True
        assert thread.is_alive()
    finally:
        parent.kill()
        parent.wait()


def test_watch_parent_probe_failure_degrades_to_alive(monkeypatch) -> None:
    """探活异常降级（对齐 Linux PDEATHSIG 的静默降级风格）：psutil.pid_exists
    抛错（如权限/资源异常）按"父仍存活"处理——绝不误杀，也不让监视线程崩溃。"""
    parent = _spawn_fake_parent()
    try:

        def boom_pid_exists(pid: int) -> bool:
            raise PermissionError(f"probe denied for {pid}")

        monkeypatch.setattr(procsup.psutil, "pid_exists", boom_pid_exists)
        recorder = _ExitRecorder()
        thread = procsup.watch_parent(recorder, poll_s=0.05, pid_of=lambda: parent.pid)
        time.sleep(0.3)  # ≥5 个周期全部探活失败
        assert recorder.count == 0, "探活失败（非父亡）被误判为父死"
        assert thread.is_alive(), "探活异常不应拖垮监视线程"
    finally:
        parent.kill()
        parent.wait()


def test_watch_parent_pid_of_failure_degrades_to_alive() -> None:
    """pid_of 抛错同样按存活降级：之后恢复（父真死）仍能触发，恰好一次。"""
    parent = _spawn_fake_parent()
    parent.kill()
    parent.wait()  # 真死：恢复后首个周期即触发
    try:
        fail = {"on": True}

        def flaky_pid_of() -> int:
            if fail["on"]:
                raise RuntimeError("getppid unavailable")
            return parent.pid

        recorder = _ExitRecorder()
        procsup.watch_parent(recorder, poll_s=0.05, pid_of=flaky_pid_of)
        time.sleep(0.2)
        assert recorder.count == 0, "pid_of 异常期间被误判为父死"
        fail["on"] = False  # 恢复：下个周期应看到 pid 消失
        assert recorder.fired.wait(5.0), "恢复后父死未触发 exit_fn"
        assert recorder.count == 1
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()


# ---------------------------------------------------------------------------
# __main__ 挂载结构：仅 Windows 挂 watch_parent，Linux PDEATHSIG 保持不双挂
# ---------------------------------------------------------------------------


def test_main_mounts_watch_parent_only_on_windows() -> None:
    src = _source(_MAIN_PY)
    assert "watch_parent" in src, "__main__ 必须挂载 procsup.watch_parent"
    assert "is_windows()" in src, "挂载必须经 platform.is_windows() 门控（仅 Windows）"
    # exit_fn 走 interrupt_main：向主线程注入 SIGINT → asyncio.Runner 转任务取消
    # → daemon 既有优雅下线（post_offline + close + 审计 shutdown）——不另造退出路径
    assert "interrupt_main" in src
    # Linux PDEATHSIG 路径保留且依旧仅限 linux（不双挂、不回退拆除）
    assert "PR_SET_PDEATHSIG" in src
    assert 'sys.platform != "linux"' in src
