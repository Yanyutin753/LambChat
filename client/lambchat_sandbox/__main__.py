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

        PR_SET_PDEATHSIG = 1  # noqa: N806 - linux/prctl.h 原名，保留便于对照
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


def _watch_parent_windows() -> None:
    """Windows 挂载父进程监视：父亡即向主线程注入 SIGINT（PDEATHSIG 替代）。

    仅 Windows 生效（Linux 已有 PDEATHSIG，不双挂；macOS 留 M5）。exit_fn 用
    ``_thread.interrupt_main``：主线程的 asyncio.Runner 把 KeyboardInterrupt
    转成任务取消，走 daemon 既有的优雅下线路径（finally: post_offline +
    close + 审计 shutdown），与 ``cmd_run`` 捕获 (KeyboardInterrupt,
    CancelledError) 的既有语义吻合——不另造退出通道。
    """
    from lambchat_sandbox import platform as plat

    if not plat.is_windows():
        return
    import _thread

    from lambchat_sandbox.procsup import watch_parent

    watch_parent(_thread.interrupt_main)


def _force_utf8_stdio() -> None:
    """std 统一 UTF-8：Windows 控制台/管道默认 cp1252，中文输出（cli.py 的
    login/status 提示等）直接 UnicodeEncodeError；errors=replace 保证写失败
    也不致命（打印诊断信息绝不该带崩主流程）。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 降级即可，不阻塞启动
            pass


if __name__ == "__main__":
    _force_utf8_stdio()
    _enable_parent_death_signal()
    _watch_parent_windows()
    from lambchat_sandbox.cli import main

    raise SystemExit(main())
