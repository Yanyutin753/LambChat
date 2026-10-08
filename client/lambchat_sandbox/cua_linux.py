"""Linux computer-use 后端(pyatspi / AT-SPI2)。

直接用系统原生的 ``python3-pyatspi``(apt/dnf 系统包,不经 pip——dogtail
在 Ubuntu 26.04 的 pip 生态已装不上,且它只是 pyatspi 的薄壳)。

前置条件:
- 系统包 ``python3-pyatspi``(或 ``python3-pyatspi``+``gir1.2-atspi-2.0``);
- 会话需可达:``DBUS_SESSION_BUS_ADDRESS`` 指向用户会话总线(SSH 场景需
  显式 ``unix:path=/run/user/<uid>/bus``),AT-SPI 总线由 GNOME 桌面常驻提供;
- GNOME 需开无障碍:``gsettings set org.gnome.desktop.interface toolkit-accessibility true``;
- 事件/截屏走 ops 层 pyautogui(X11;Wayland 下合成输入受限,报错引导)。
"""

from __future__ import annotations

from typing import Any


def _pyatspi() -> Any:
    try:
        import pyatspi

        return pyatspi
    except ImportError as exc:
        raise RuntimeError(f"python3-pyatspi missing: {exc}") from exc


def _desktop() -> Any:
    return _pyatspi().Registry.getDesktop(0)


def ax_trusted() -> bool:
    try:
        _desktop().childCount  # noqa: B018 - AT-SPI 总线可达性探测
        return True
    except Exception:  # noqa: BLE001
        return False


def frontmost_pid() -> int | None:
    # AT-SPI 无前台语义;X11 下用 xdotool 探测,Wayland 返回 None
    # (事件路径据此报 foreground_required,绝不猜)
    import subprocess

    try:
        output = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowpid"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        return int(output.strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def list_apps() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        desktop = _desktop()
        for index in range(desktop.childCount):
            app = desktop.getChildAtIndex(index)
            try:
                rows.append({"pid": int(app.get_process_id()), "name": app.name or ""})
            except Exception:  # noqa: BLE001 - 单应用元数据缺失不拖垮清单
                continue
    except Exception:  # noqa: BLE001 - AT-SPI 不可达
        pass
    return rows


def _extents(element: Any) -> list[float] | None:
    try:
        rect = element.get_extents(_pyatspi().DESKTOP_COORDS)
        return [float(rect.x), float(rect.y), float(rect.width), float(rect.height)]
    except Exception:  # noqa: BLE001
        return None


def _is_window(element: Any) -> bool:
    try:
        return element.getRoleName() in ("frame", "window", "dialog", "alert")
    except Exception:  # noqa: BLE001
        return False


def windows(pid: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        desktop = _desktop()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"at-spi unreachable: {exc}") from exc
    for index in range(desktop.childCount):
        app = desktop.getChildAtIndex(index)
        try:
            if int(app.get_process_id()) != pid:
                continue
        except Exception:  # noqa: BLE001
            continue
        for child_index in range(app.childCount):
            child = app.getChildAtIndex(child_index)
            if not _is_window(child):
                continue
            rows.append(
                {
                    "window_id": len(rows),
                    "title": child.name or "",
                    "subrole": child.getRoleName(),
                    "main": len(rows) == 0,
                    "focused": False,
                    "bounds": _extents(child),
                    "handle": child,
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
        return [element.getChildAtIndex(i) for i in range(element.childCount)]
    except Exception:  # noqa: BLE001
        return []


def _text_value(element: Any) -> str | None:
    try:
        text = element.queryText()
        content = text.getText(0, text.characterCount)
        return content if content else None
    except Exception:  # noqa: BLE001 - 非文本控件
        return None


def row_of(element: Any) -> dict[str, Any]:
    actions: list[str] = []
    try:
        action = element.queryAction()
        actions = [action.getName(i) for i in range(action.nActions)]
    except Exception:  # noqa: BLE001
        actions = []
    try:
        kind = element.getRoleName() or None
        title = element.name or None
    except Exception:  # noqa: BLE001
        kind, title = None, None
    return {
        "kind": kind,
        "title": title,
        "value": _text_value(element),
        "actions": actions,
        "bounds": _extents(element),
    }


# 语义动作 → 各 UI 框架的 AT-SPI 动作名(GTK: click/press;Chromium: press/
# doDefault;Qt: press)。按序匹配第一个存在的。
_SEMANTIC_ACTIONS: dict[str, tuple[str, ...]] = {
    "click": ("click", "press", "doDefault", "activate"),
    "context_menu": ("showContextMenu", "showMenu"),
}


def perform(element: Any, action: str) -> None:
    try:
        act = element.queryAction()
    except Exception as exc:  # noqa: BLE001
        raise KeyError(f"no actions on element: {exc}") from exc
    available = {act.getName(i): i for i in range(act.nActions)}
    if action.startswith("AX"):
        action = action.removeprefix("AX")
    candidates = _SEMANTIC_ACTIONS.get(action, (action,))
    for name in candidates:
        if name in available or name.lower() in {k.lower(): v for k, v in available.items()}:
            index = available.get(name)
            if index is None:
                lowered = {k.lower(): v for k, v in available.items()}
                index = lowered[name.lower()]
            if not act.doAction(index):
                raise RuntimeError(f"action {name} returned failure")
            return
    raise KeyError(f"action {action} not available on element")


def set_value(element: Any, text: str) -> None:
    try:
        editable = element.queryEditableText()
    except Exception as exc:  # noqa: BLE001
        raise KeyError(f"element not settable (no editable text): {exc}") from exc
    # setTextContents → replaceText 双路径:Chromium 对 setTextContents 常返回
    # 失败,但 EditableText.replaceText(0, charCount, text) 可用(xiaoxin 真机)
    try:
        if editable.setTextContents(text):
            return
    except Exception:  # noqa: BLE001
        pass
    try:
        count = element.queryText().characterCount
        if editable.replaceText(0, count, text):
            return
    except Exception as exc:  # noqa: BLE001
        raise KeyError(f"element not settable: {exc}") from exc
    raise KeyError("element not settable: setTextContents/replaceText both failed")


def set_focus(element: Any) -> None:
    """AT-SPI component.grabFocus(免前台聚焦,Wayland 可用)。"""
    try:
        if not element.queryComponent().grabFocus():
            raise KeyError("grabFocus returned False")
    except KeyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise KeyError(f"element not focusable: {exc}") from exc


def activate_window(pid: int, window_id: int | None) -> None:
    """Wayland 安全模型下外部激活窗口没有可靠通道(wmctrl 只认 X11;
    GNOME 的 Shell D-Bus 激活面向应用 ID 不面向 pid)。明确报不支持并
    指路元素动作,不让模型空转重试。"""
    raise KeyError("window activation unsupported on Linux/Wayland; act on elements instead")


# pyatspi 原生合成输入(经 AT-SPI 总线,Wayland 原生可用,无需 X11/pyautogui)。
# 特殊键名 → X keysym(pyatspi KEY_SYM 用)
_KEYSYMS = {
    "return": "Return",
    "enter": "Return",
    "escape": "Escape",
    "tab": "Tab",
    "delete": "BackSpace",
    "forwarddelete": "Delete",
    "space": "space",
    "left": "Left",
    "right": "Right",
    "down": "Down",
    "up": "Up",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pagedown": "Next",
    "f1": "F1",
    "f2": "F2",
    "f3": "F3",
    "f4": "F4",
    "f5": "F5",
    "f6": "F6",
    "f7": "F7",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
    "f11": "F11",
    "f12": "F12",
}


def type_text(text: str) -> None:
    """KEY_STRING 整串合成(大小写/unicode 由 keysym 字符串承载)。"""
    _pyatspi().Registry.generateKeyboardEvent(0, text, _pyatspi().KEY_STRING)


def press_key(key: str) -> None:
    """单键(特殊键走 KEY_SYM,单字符走 KEY_STRING)。"""
    pyatspi = _pyatspi()
    sym = _KEYSYMS.get(key.lower())
    if sym:
        pyatspi.Registry.generateKeyboardEvent(0, sym, pyatspi.KEY_SYM)
        return
    if len(key) == 1:
        pyatspi.Registry.generateKeyboardEvent(0, key, pyatspi.KEY_STRING)
        return
    raise KeyError(f"unknown_key:{key}")


def click_point(x: float, y: float, button: str = "left") -> None:
    pyatspi = _pyatspi()
    mapping = {
        "left": pyatspi.MOUSE_B1C,
        "middle": pyatspi.MOUSE_B2C,
        "right": pyatspi.MOUSE_B3C,
    }
    kind = mapping.get(button, pyatspi.MOUSE_B1C)
    pyatspi.Registry.generateMouseEvent(int(x), int(y), kind)
