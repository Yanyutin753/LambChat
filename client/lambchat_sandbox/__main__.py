"""python -m lambchat_sandbox 入口。"""

import os
import signal
import sys


def _enable_parent_death_signal() -> None:
    """Linux 下注册 PR_SET_PDEATHSIG(SIGKILL)：父进程死亡时内核同步清理本进程。

    动机（M3 T8 发现）：PyInstaller onefile 外层 wrapper 被 SIGKILL 时（shell
    托管 stop / 意外被杀）无法运行任何清理代码，内层 daemon 被 init/subreaper
    收养而残留，并与新拉起的实例在服务端 registry 互踢。PDEATHSIG 让内核在
    wrapper 死亡瞬间直接 SIGKILL 内层，杜绝孤儿。

    仅 Linux 生效；失败静默降级（不影响正常功能，只是回到孤儿兜底语义）。
    """
    if sys.platform != "linux":
        return
    try:
        import ctypes

        PR_SET_PDEATHSIG = 1
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL) != 0:
            return
        # 竞态兜底：若 prctl 调用前父进程已死（信号永不触发），此处主动退出。
        # 1 是 init；subreaper 场景（ppid 非 1 但父已换人）无法廉价判别，接受。
        if os.getppid() == 1:
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - 保守降级，不阻塞 daemon 启动
        pass


if __name__ == "__main__":
    _enable_parent_death_signal()
    from lambchat_sandbox.cli import main

    raise SystemExit(main())
