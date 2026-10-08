"""computer-use 平台后端调度。

三平台各接当前最好的开源无障碍自动化库,键鼠/截屏统一走 pyautogui
(atomacos 在 macOS 附带;其余平台由 cua 依赖组显式引入):

- macOS: ``atomacos``(Apple AX API,经 PyObjC)
- Windows: ``pywinauto``(UI Automation)
- Linux: ``dogtail``(AT-SPI2;需系统 python3-atspi / gir1.2-atspi-2.0)

后端按平台**懒加载**(非本平台不 import,PyInstaller 按入口可达性收集),
加载失败(库缺失/平台不匹配)统一抛 :class:`UnsupportedBackendError`,由 op 层
收敛为 ``unsupported_platform`` 结构化错误——CI(Linux 无 X11/无 atspi)与
生产未授权路径都优雅降级,不炸通道。

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

import sys
from typing import Any


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
    platform = sys.platform
    try:
        if platform == "darwin":
            from lambchat_sandbox import cua_mac

            _BACKEND = cua_mac
        elif platform == "win32":
            from lambchat_sandbox import cua_win

            _BACKEND = cua_win
        elif platform.startswith("linux"):
            from lambchat_sandbox import cua_linux

            _BACKEND = cua_linux
        else:
            raise UnsupportedBackendError(f"unsupported_platform:{platform}")
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
