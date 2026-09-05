"""父进程监视（process supervision）：Windows 上替代 Linux PDEATHSIG 的保活契约。

Linux 侧 ``__main__`` 用 ``prctl(PR_SET_PDEATHSIG)`` 让内核在父进程死亡瞬间
SIGKILL 本进程（M3 T8 修复 PyInstaller onefile 外层 wrapper 被杀后内层 daemon
残留互踢的问题）；Windows 无对应机制——:func:`watch_parent` 用 daemon 线程
轮询父进程存活，父亡即回调 ``exit_fn`` 一次（``__main__`` 仅 Windows 挂载，
Linux 不双挂）。

判死双保险（两条任一命中即判父亡）：

1. ``pid_of()`` 返回值 != 启动快照——POSIX 语义：原父死后本进程被
   init/subreaper 收养，``os.getppid()`` 立即变化（父成僵尸、pid 被新进程
   顶替等情况也都被"变化"覆盖，不吃 pid 复用的亏）；
2. 快照 pid 不复存在（``psutil.pid_exists``）——Windows 语义：
   CPython 的 ``os.getppid()`` 在 Windows 上是解释器启动时的静态快照、
   永不变化，只能靠 pid 存活探测判死（psutil 是本项目主依赖）。
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable

import psutil

DEFAULT_POLL_S = 2.0


def watch_parent(
    exit_fn: Callable[[], None],
    poll_s: float = DEFAULT_POLL_S,
    *,
    pid_of: Callable[[], int] = os.getppid,
) -> threading.Thread:
    """启动 daemon 线程监视父进程；父亡时调用 ``exit_fn`` 一次后线程退出。

    - 快照在监视线内取首个成功值（``pid_of()``）；之后每个周期先判死再睡——
      父在快照前已死则首个周期立即触发，不空等一个 ``poll_s``；
    - 快照/探活异常（``pid_of``/``psutil.pid_exists`` 抛错，如权限/资源异常）
      按"父仍存活"降级（M4 T8，对齐 Linux PDEATHSIG 的静默降级风格）——
      探测失败绝不误判父亡触发误杀，也不拖垮监视线程；快照持续失败则每周期
      重试，恢复（拿到首个成功值）后照常监视；
    - ``exit_fn`` 恰好调用一次（触发即 return，线程退出）；
    - ``pid_of`` 可注入：测试用短命子进程的 pid 伪造"父"；
    - 线程为 daemon：监视本身绝不阻塞解释器退出。
    """
    parent: int | None = None

    def _watch() -> None:
        nonlocal parent
        while True:
            try:
                current = pid_of()
                if parent is None:
                    parent = current  # 首个成功快照（此前持续失败则本周期补拍）
                gone = current != parent or not psutil.pid_exists(parent)
            except Exception:  # noqa: BLE001 - 快照/探活失败按存活降级，绝不误杀
                gone = False
            if gone:
                exit_fn()
                return
            time.sleep(poll_s)

    thread = threading.Thread(target=_watch, name="lambchat-parent-watch", daemon=True)
    thread.start()
    return thread
