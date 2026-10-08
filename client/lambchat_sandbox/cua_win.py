"""Windows computer-use 后端(pywinauto,UI Automation)。

UIA 常规窗口无需特殊权限(提权窗口/UAC 需 daemon 同级管理员运行);
键鼠/截屏由 ops 层的 pyautogui 统一处理(Windows 下零额外系统依赖)。

注意:本后端编写基于 pywinauto 文档与源码结构,合入后需在真机
(Windows 桌面端)抽检一次——仓库发版流程本就要求 win 真机抽检。
"""

from __future__ import annotations

from typing import Any

from pywinauto import Desktop


def ax_trusted() -> bool:
    # UIA 对常规窗口开箱可用;提权窗口需要进程同级提权,运行时按元素报错
    return True


def frontmost_pid() -> int | None:
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = ctypes.c_uint32()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


def list_apps() -> list[dict[str, Any]]:
    import subprocess

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
        rows.append({"pid": pid, "name": name.removesuffix(".exe")})
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


def windows(pid: int) -> list[dict[str, Any]]:
    # 全量枚举后按 wrapper.process_id() 过滤:Desktop.windows(process=) 的
    # kwarg 过滤与 Application.connect(process=).windows() 在真机上均枚举
    # 不到目标进程(192.168.1.2 Win10 实测 0 窗口,而全量列表里窗口明明
    # 存在)——窗口在那,过滤坏,就自己过滤。
    rows: list[dict[str, Any]] = []
    try:
        all_windows = Desktop(backend="uia").windows()
    except Exception:  # noqa: BLE001 - UIA 不可用
        return rows
    for element in all_windows:
        if _window_pid(element) != pid:
            continue
        try:
            info = element.element_info
            rect = info.rectangle
            bounds = [float(rect.left), float(rect.top), float(rect.width()), float(rect.height())]
        except Exception:  # noqa: BLE001
            bounds = None
        rows.append(
            {
                "window_id": len(rows),
                "title": getattr(element.element_info, "name", "") or "",
                "subrole": None,
                "main": len(rows) == 0,
                "focused": False,
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
            return row["handle"], {k: row[k] for k in ("window_id", "title", "bounds")}
        raise KeyError(f"window index {window_id} out of range")
    if rows:
        row = rows[0]
        return row["handle"], {k: row[k] for k in ("window_id", "title", "bounds")}
    raise KeyError("app has no accessible windows")


def children(element: Any) -> list[Any]:
    try:
        return list(element.children())
    except Exception:  # noqa: BLE001
        return []


def row_of(element: Any) -> dict[str, Any]:
    try:
        info = element.element_info
        kind = getattr(info, "control_type", None) or ""
        title = getattr(info, "name", None) or ""
    except Exception:  # noqa: BLE001
        kind, title = "", ""
    value = _read_value(element)
    actions: list[str] = []
    for name, method in (
        ("Invoke", "invoke"),
        ("Select", "select"),
        ("Expand", "expand"),
        ("Toggle", "toggle"),
    ):
        if hasattr(element, method):
            actions.append(name)
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


def perform(element: Any, action: str) -> None:
    mapping = {"invoke": "invoke", "select": "select", "expand": "expand", "toggle": "toggle"}
    method = mapping.get(action.removeprefix("AX").lower())
    if method and hasattr(element, method):
        getattr(element, method)()
        return
    raise KeyError(f"action {action} not available on element")


def _read_value(element: Any) -> str | None:
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
