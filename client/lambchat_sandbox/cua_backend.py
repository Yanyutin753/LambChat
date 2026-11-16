"""computer-use 平台后端调度。

三平台的应用发现、窗口、快照和语义操作统一经打包的 agent-desktop。
权限、前台、输入与截图也由同一驱动提供；驱动缺失时明确失败。

后端接口(duck-typed,ops 层唯一依赖面):
- ``ax_trusted() -> bool``          权限预检(mac=辅助功能;linux=AT-SPI 可达)
- ``frontmost_pid() -> int | None`` 前台应用 pid(事件策略前台判定)
- ``list_apps() -> [{pid, name}]``
- ``windows(pid) -> [{window_id?, title, main, focused, bounds}]``
- ``pick_window(pid, window_id?) -> (window_handle, info)``
- ``children(element) -> [element]``
- ``row_of(element) -> {kind, title, value, actions, bounds}``
- ``perform(element, action)`` / ``set_value(element, text)``
bounds 为 ``[x, y, w, h]`` 全局屏幕坐标(截屏 region 与元素中心点用)。
"""

from __future__ import annotations

import os
import sys
from typing import Any


def is_control_window(pid: int, title: str) -> bool:
    return (
        bool(os.environ.get("LAMBCHAT_DESKTOP_CONTROL"))
        and os.environ.get("LAMBCHAT_DESKTOP_CONTROL_OWNER_PID") == str(pid)
        and title in {"LambChat Control", "LambChat Control Overlay"}
    )


class UnsupportedBackendError(Exception):
    """当前平台/环境没有可用的 computer-use 后端。"""


_BACKEND: Any = None
_BACKEND_ERROR: str | None = None


def _load_backend() -> Any:
    global _BACKEND, _BACKEND_ERROR
    if _BACKEND is not None:
        return _BACKEND
    if _BACKEND_ERROR is not None:
        raise UnsupportedBackendError(_BACKEND_ERROR)
    from lambchat_sandbox.platform import daemon_platform

    platform = "android" if daemon_platform() == "android" else sys.platform
    try:
        if platform not in ("darwin", "win32", "linux"):
            raise UnsupportedBackendError(f"unsupported_platform:{platform}")
        from lambchat_sandbox.agent_desktop import AgentDesktopBackend, binary_path

        binary = binary_path()
        if binary is None:
            raise UnsupportedBackendError("agent_desktop_missing: repair the desktop installation")
        _BACKEND = AgentDesktopBackend(binary)
    except ImportError as exc:
        _BACKEND_ERROR = f"backend_import_failed:{exc}"
        raise UnsupportedBackendError(_BACKEND_ERROR) from exc
    return _BACKEND


def backend() -> Any:
    try:
        return _load_backend()
    except UnsupportedBackendError:
        raise


def backend_platform() -> str:
    return sys.platform
