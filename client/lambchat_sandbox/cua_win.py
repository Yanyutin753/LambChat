"""Windows computer-use 后端(pywinauto,UI Automation)。

UIA 常规窗口无需特殊权限(提权窗口/UAC 需 daemon 同级管理员运行);
键鼠/截屏由 ops 层的 pyautogui 统一处理(Windows 下零额外系统依赖)。

注意:本后端编写基于 pywinauto 文档与源码结构,合入后需在真机
(Windows 桌面端)抽检一次——仓库发版流程本就要求 win 真机抽检。
"""

from __future__ import annotations

from typing import Any


def _desktop_windows() -> list[Any]:
    """Desktop(backend="uia").windows()——懒加载 pywinauto(本模块需在
    非 Windows 平台可导入供单元测试),失败按无窗口处理。"""
    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        windows = list(desktop.windows())
    except Exception:  # noqa: BLE001 - UIA 不可用
        return []
    try:
        foreground = _foreground_hwnd()
        if foreground and all(_window_hwnd(window) != foreground for window in windows):
            # Owned Qt dialogs may be nested under their app in the UIA desktop tree.
            windows.append(desktop.window(handle=foreground).wrapper_object())
    except Exception:  # noqa: BLE001 - A denied active window must not hide discovered windows.
        pass
    return windows


def ax_trusted() -> bool:
    # UIA 对常规窗口开箱可用;提权窗口需要进程同级提权,运行时按元素报错
    return True


def _foreground_hwnd() -> int | None:
    import ctypes

    getter = ctypes.windll.user32.GetForegroundWindow  # type: ignore[attr-defined]
    getter.restype = ctypes.c_void_p
    return getter() or None


def frontmost_pid() -> int | None:
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    hwnd = _foreground_hwnd()
    if not hwnd:
        return None
    pid = ctypes.c_uint32()
    user32.GetWindowThreadProcessId.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


def list_apps() -> list[dict[str, Any]]:
    """只列**拥有可见顶层窗口**的进程。

    生产实测(2026-10-08):全量 tasklist 数百行系统进程(System/csrss/
    svchost),模型只能逐 pid 盲探 windows(连续 6 次 no_windows)。
    合并桌面窗口枚举后只回 GUI 进程——浏览器多进程场景也直接给出
    持窗口的主进程 pid,免探测。
    """
    import subprocess

    gui_pids: set[int] = set()
    for element in _desktop_windows():
        pid = _window_pid(element)
        if pid:
            gui_pids.add(pid)
    if not gui_pids:
        return []
    output = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=15
    ).stdout
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) < 2:
            continue
        name, pid_text = parts[0], parts[1]
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid not in gui_pids:
            continue
        rows.append({"pid": pid, "name": name.removesuffix(".exe")})
    try:
        front = frontmost_pid()
    except Exception:  # noqa: BLE001
        front = None
    if front is not None:
        rows.sort(key=lambda r: 0 if r["pid"] == front else 1)
    return rows


def _window_pid(element: Any) -> int | None:
    for getter in (
        lambda: element.process_id(),
        lambda: element.element_info.process_id,
    ):
        try:
            return int(getter())
        except Exception:  # noqa: BLE001
            continue
    return None


def _window_hwnd(element: Any) -> int | None:
    for getter in (lambda: element.handle, lambda: element.element_info.handle):
        try:
            handle = getter()
            if handle:
                return int(handle)
        except Exception:  # noqa: BLE001 - A stale wrapper may still expose its native info.
            continue
    return None


def windows(pid: int) -> list[dict[str, Any]]:
    # 全量枚举后按 wrapper.process_id() 过滤:Desktop.windows(process=) 的
    # kwarg 过滤与 Application.connect(process=).windows() 在真机上均枚举
    # 不到目标进程(192.168.1.2 Win10 实测 0 窗口,而全量列表里窗口明明
    # 存在)——窗口在那,过滤坏,就自己过滤。
    rows: list[dict[str, Any]] = []
    try:
        foreground = _foreground_hwnd()
    except Exception:  # noqa: BLE001 - Missing native focus must deny screenshot capture.
        foreground = None
    for element in _desktop_windows():
        if _window_pid(element) != pid:
            continue
        try:
            info = element.element_info
            rect = info.rectangle
            bounds = [float(rect.left), float(rect.top), float(rect.width()), float(rect.height())]
        except Exception:  # noqa: BLE001
            bounds = None
        focused = foreground is not None and _window_hwnd(element) == foreground
        rows.append(
            {
                "window_id": len(rows),
                "title": getattr(element.element_info, "name", "") or "",
                "subrole": None,
                "main": len(rows) == 0,
                "focused": focused,
                "bounds": bounds,
                "handle": element,
            }
        )
    return rows


def pick_window(pid: int, window_id: int | None) -> tuple[Any, dict[str, Any]]:
    rows = windows(pid)
    if window_id is not None:
        if 0 <= window_id < len(rows):
            row = rows[window_id]
            return row["handle"], {k: row[k] for k in ("window_id", "title", "bounds", "focused")}
        raise KeyError(f"window index {window_id} out of range")
    for row in rows:
        if row["focused"]:
            return row["handle"], {k: row[k] for k in ("window_id", "title", "bounds", "focused")}
    if rows:
        row = rows[0]
        return row["handle"], {k: row[k] for k in ("window_id", "title", "bounds", "focused")}
    raise KeyError("app has no accessible windows")


def children(element: Any) -> list[Any]:
    try:
        candidates = element.children()
    except Exception:  # noqa: BLE001
        return []
    visible = []
    for child in candidates:
        try:
            if child.is_visible():
                visible.append(child)
        except Exception:  # noqa: BLE001 - One stale provider must not hide visible siblings.
            continue
    return visible


def row_of(element: Any) -> dict[str, Any]:
    from pywinauto.uia_defines import NoPatternInterfaceError

    try:
        info = element.element_info
        kind = getattr(info, "control_type", None) or ""
        title = getattr(info, "name", None) or ""
    except Exception:  # noqa: BLE001
        kind, title = "", ""
    value = _read_value(element)
    actions: list[str] = []
    for name, pattern in (
        ("Invoke", "iface_invoke"),
        ("Select", "iface_selection_item"),
        ("Expand", "iface_expand_collapse"),
        ("Toggle", "iface_toggle"),
    ):
        try:
            interface = getattr(element, pattern, None)
            if interface is not None:
                actions.append(name)
                if name == "Toggle" and value is None:
                    try:
                        if element.element_info.element.CurrentIsPassword is False:
                            value = {0: "off", 1: "on", 2: "mixed"}.get(
                                interface.CurrentToggleState
                            )
                    except Exception:  # noqa: BLE001 - A stale state must not hide the control.
                        pass
        except NoPatternInterfaceError:
            pass
    bounds = None
    try:
        rect = element.element_info.rectangle
        bounds = [float(rect.left), float(rect.top), float(rect.width()), float(rect.height())]
    except Exception:  # noqa: BLE001
        pass
    return {
        "kind": kind or None,
        "title": title or None,
        "value": value,
        "actions": actions,
        "bounds": bounds,
    }


# 语义动作 → pywinauto wrapper 方法。生产实测(2026-10-08)漏了 "click"
# 语义映射:ops 层把 click 传进来,这里 KeyError「action click not available
# on element」——Windows 元素点击整体不可用。click/press 一律落到 Invoke
# (UIA 的默认动作,即「点一下」);legacy DoDefaultAction 兜底覆盖无
# InvokePattern 但有 LegacyIAccessible 默认动作的控件。
_PERFORM_MAPPING = {
    "invoke": "invoke",
    "click": "invoke",
    "press": "invoke",
    "default": "invoke",
    "select": "select",
    "expand": "expand",
    "toggle": "toggle",
}


def perform(element: Any, action: str) -> None:
    from pywinauto.uia_defines import NoPatternInterfaceError

    normalized = action.removeprefix("AX").lower()
    method = _PERFORM_MAPPING.get(normalized)
    if method and hasattr(element, method):
        try:
            getattr(element, method)()
            return
        except NoPatternInterfaceError:
            pass
    # LegacyIAccessible.DoDefaultAction 兜底:接口属性名随 pywinauto 版本
    # 有 iface_legacy / iface_legacy_IAccessible 两种拼写,逐一探测。
    for legacy_name in ("iface_legacy", "iface_legacy_IAccessible"):
        try:
            legacy = getattr(element, legacy_name, None)
        except NoPatternInterfaceError:
            continue
        do_default = getattr(legacy, "DoDefaultAction", None)
        if callable(do_default):
            do_default()
            return
    raise KeyError(f"action {action} not available on element")


def set_focus(element: Any) -> None:
    """聚焦元素;pywinauto 的 set_focus 会顺带把所在窗口调到前台——
    type 的免前台路径(focus+set_value)失败回退合成键盘时正需要它。"""
    element.set_focus()


def activate_window(pid: int, window_id: int | None) -> None:
    """把窗口调到前台(显式 activate 动作,agent 主动调用)。"""
    rows = windows(pid)
    index = 0 if window_id is None else window_id
    if not 0 <= index < len(rows):
        raise KeyError(f"window index {index} out of range")
    rows[index]["handle"].set_focus()


def screenshot(bounds: list[float] | None) -> Any:
    from PIL import ImageGrab

    bbox = None
    if bounds:
        x, y, width, height = bounds
        bbox = (int(x), int(y), int(x + width), int(y + height))
    return ImageGrab.grab(bbox=bbox, all_screens=True)


def type_text(text: str) -> None:
    from pywinauto.keyboard import send_keys

    # VK_PACKET carries 16-bit UTF-16 units; send_keys also interprets punctuation.
    encoded = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-16-le")
    units = (chr(int.from_bytes(encoded[i : i + 2], "little")) for i in range(0, len(encoded), 2))
    literal = "".join("{" + char + "}" if char in "{}+^%~()" else char for char in units)
    # Office cells recreate their editor after Enter/Tab; wait before the next character.
    literal = literal.replace("\n", "{ENTER}{PAUSE 0.15}").replace("\t", "{TAB}{PAUSE 0.15}")
    send_keys(literal, with_spaces=True, with_tabs=True, with_newlines=True, pause=0.01)


def _read_value(element: Any) -> str | None:
    try:
        if element.element_info.element.CurrentIsPassword is not False:
            return None
    except Exception:  # noqa: BLE001 - Unknown protection state must not expose values.
        return None
    # WinForms/WPF 控件常无 Legacy patterns:legacy → ValuePattern 双路径读
    try:
        legacy = element.legacy_properties()
        legacy_value = legacy.get("value")
        if legacy_value:
            return str(legacy_value)
    except Exception:  # noqa: BLE001
        pass
    try:
        return str(element.iface_value.CurrentValue) or None
    except Exception:  # noqa: BLE001
        return None


def press_chord(keys: list[str], modifiers: list[str]) -> None:
    from pywinauto.keyboard import CODES, VirtualKeyAction, parse_keys

    aliases = {"pageup": "PGUP", "pagedown": "PGDN"}
    sequence = ""
    for key in keys:
        if len(key) == 1:
            sequence += "{" + key + "}" if key in "{}+^%~()" else key
        else:
            name = aliases.get(key, key.upper())
            if name not in CODES:
                raise KeyError(f"unsupported key: {key}")
            sequence += "{" + name + "}"
    actions = parse_keys(sequence, vk_packet=False)
    modifier_codes = {
        "ctrl": "VK_CONTROL",
        "shift": "VK_SHIFT",
        "alt": "VK_MENU",
        "winleft": "VK_LWIN",
    }
    codes = [CODES[modifier_codes[modifier]] for modifier in modifiers]
    held = []
    try:
        for code in codes:
            held.append(code)
            VirtualKeyAction(code, up=False).run()
        for action in actions:
            action.run()  # VirtualKeyAction includes the extended flag for navigation keys.
    finally:
        for code in reversed(held):
            VirtualKeyAction(code, down=False).run()


def scroll_wheel(horizontal: bool, clicks: int) -> None:
    import ctypes

    mouse_event = ctypes.windll.user32.mouse_event
    mouse_event.argtypes = (ctypes.c_uint32,) * 4 + (ctypes.c_size_t,)
    mouse_event.restype = None
    # PyAutoGUI's Windows hscroll uses the vertical flag and its wheel omits WHEEL_DELTA.
    while clicks:
        step = max(-100, min(clicks, 100))  # WM_MOUSEWHEEL carries a signed 16-bit delta.
        mouse_event(0x1000 if horizontal else 0x0800, 0, 0, ctypes.c_uint32(step * 120).value, 0)
        clicks -= step


def set_value(element: Any, text: str) -> None:
    # 包装器方法优先,UIA ValuePattern 直写兜底(WinForms TextBox 实测只有
    # ValuePattern 可用,2026-10-07 真机)
    for method in ("set_value", "set_edit_text"):
        fn = getattr(element, method, None)
        if callable(fn):
            try:
                fn(text)
                return
            except Exception:  # noqa: BLE001 - 该包装器方法不适用此控件
                continue
    try:
        element.iface_value.SetValue(text)
        return
    except Exception as exc:  # noqa: BLE001
        raise KeyError(f"element not settable: {exc}") from exc
