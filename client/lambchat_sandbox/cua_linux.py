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
    desktop = _pyatspi().Registry.getDesktop(0)
    # The daemon has no GLib event loop to refresh AT-SPI's cached descendants.
    desktop.clear_cache()
    return desktop


def screenshot(bounds: list[float] | None) -> Any:
    import os

    from PIL import ImageGrab

    if os.environ.get("WAYLAND_DISPLAY"):
        raise RuntimeError(
            "native Wayland capture is unavailable; use an X11 desktop for screenshots"
        )
    bbox = None
    if bounds:
        x, y, width, height = bounds
        bbox = (int(x), int(y), int(x + width), int(y + height))
    return ImageGrab.grab(bbox=bbox, xdisplay=os.environ.get("DISPLAY"))


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
        return element.getRoleName() in ("frame", "window", "dialog", "alert", "file chooser")
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
            app.clear_cache()
        except Exception:  # noqa: BLE001
            continue
        for child_index in range(app.childCount):
            child = app.getChildAtIndex(child_index)
            child.clear_cache()
            if not _is_window(child):
                continue
            try:
                focused = bool(child.getState().contains(_pyatspi().STATE_ACTIVE))
            except Exception:  # noqa: BLE001 - Unknown native focus must deny screenshot capture.
                focused = False
            rows.append(
                {
                    "window_id": len(rows),
                    "title": child.name or "",
                    "subrole": child.getRoleName(),
                    "main": len(rows) == 0,
                    "focused": focused,
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
        getattr(element, "clear_cache", lambda: None)()
        # Spreadsheet providers expose millions of virtual cells below a single node.
        candidates = [element.getChildAtIndex(i) for i in range(min(element.childCount, 400))]
        visible = []
        for child in candidates:
            getattr(child, "clear_cache", lambda: None)()
            if child.getState().contains(_pyatspi().STATE_SHOWING):
                visible.append(child)
        return visible
    except Exception:  # noqa: BLE001
        return []


def _text_value(element: Any) -> str | None:
    try:
        if element.getRole() == _pyatspi().ROLE_PASSWORD_TEXT:
            return None
        text = element.queryText()
        content = text.getText(0, text.characterCount)
        return content if content else None
    except Exception:  # noqa: BLE001 - 非文本控件
        return None


def row_of(element: Any) -> dict[str, Any]:
    getattr(element, "clear_cache", lambda: None)()
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
    if not editable.setTextContents(text):
        raise KeyError("element not settable: setTextContents failed")
    element.clear_cache()
    if element.queryText().getText(0, -1) != text:
        raise KeyError("setTextContents did not change the editable text")


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
    """Activate the pinned X11 window; native Wayland windows require element actions."""
    import subprocess

    _, info = pick_window(pid, window_id)
    try:
        output = subprocess.run(
            ["wmctrl", "-lp"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
        matches = []
        for line in output.splitlines():
            fields = line.split(None, 4)
            if len(fields) == 5 and fields[2] == str(pid) and fields[4] == info["title"]:
                matches.append(fields[0])
        if len(matches) != 1:
            raise KeyError("pinned window unavailable on X11; use element actions on Wayland")
        subprocess.run(["wmctrl", "-ia", matches[0]], capture_output=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise KeyError(
            f"X11 activation unavailable; use element actions on Wayland: {exc}"
        ) from exc


# AT-SPI 合成输入;Wayland 下是否可用取决于桌面,不保证全局键鼠支持。
# 特殊键名 → X keysym(pyatspi KEY_SYM 用)
_KEYSYMS = {
    "return": "Return",
    "enter": "Return",
    "escape": "Escape",
    "esc": "Escape",
    "tab": "Tab",
    "backspace": "BackSpace",
    "delete": "Delete",
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
    """Replace the focused text selection; KEY_STRING corrupts non-ASCII input."""
    import time

    pyatspi = _pyatspi()
    desktop = _desktop()
    pid = frontmost_pid()
    queue = [
        desktop.getChildAtIndex(i)
        for i in range(desktop.childCount)
        if desktop.getChildAtIndex(i).get_process_id() == pid
    ]
    deadline = time.monotonic() + 5
    visited = 0
    while queue and visited < 400 and time.monotonic() < deadline:
        element = queue.pop(0)
        visited += 1
        if element.getState().contains(pyatspi.STATE_FOCUSED):
            try:
                source = element.queryText()
                old = source.getText(0, -1)
                start, end = (
                    source.getSelection(0)
                    if source.getNSelections()
                    else (source.caretOffset, source.caretOffset)
                )
                editable = element.queryEditableText()
                updated = old[:start] + text + old[end:]
                # AT-SPI insertion length counts UTF-8 bytes, caret offsets count characters.
                changed = (
                    editable.insertText(start, text, len(text.encode("utf-8")))
                    if start == end
                    else editable.setTextContents(updated)
                )
                if changed:
                    element.clear_cache()
                    if element.queryText().getText(0, -1) != updated:
                        raise KeyError("typing did not change the editable text")
                    source.setCaretOffset(start + len(text))
                    return
            except Exception:  # noqa: BLE001 - terminals may lack EditableText
                pass
        queue.extend(
            child for child in children(element) if child.getState().contains(pyatspi.STATE_SHOWING)
        )
    import os

    if (
        os.environ.get("DISPLAY")
        and not os.environ.get("WAYLAND_DISPLAY")
        and os.environ.get("XDG_SESSION_TYPE") != "wayland"
    ):
        _type_x11_text(text)
        return
    if any(ord(char) > 127 for char in text):
        raise KeyError("Unicode typing requires a focused editable element; use set_value")
    pyatspi.Registry.generateKeyboardEvent(0, text, pyatspi.KEY_STRING)


def _type_x11_text(text: str) -> None:
    """Use Unicode keysyms so Shift does not toggle the user's input method."""
    import time
    from contextlib import suppress

    from Xlib import X, display
    from Xlib.ext import xtest

    connection = display.Display()
    saved = []
    try:
        first = connection.display.info.min_keycode
        count = connection.display.info.max_keycode - first + 1
        mapping = connection.get_keyboard_mapping(first, count)
        modifiers = {code for group in connection.get_modifier_mapping() for code in group}
        free = [
            (first + i, row)
            for i, row in enumerate(mapping)
            if not any(row) and first + i not in modifiers
        ]
        chars = list(dict.fromkeys(text))
        # shortcut: distinct characters must fit unused keycodes; chunk longer input when needed.
        if len(chars) > len(free):
            raise KeyError("not enough unused X11 keycodes; type text in smaller chunks")
        codes = {}
        for char, (code, row) in zip(chars, free):
            symbol = {"\n": 0xFF0D, "\r": 0xFF0D, "\t": 0xFF09}.get(char, 0x01000000 | ord(char))
            saved.append((code, tuple(row)))
            connection.change_keyboard_mapping(code, [(symbol, *([0] * (len(row) - 1)))])
            codes[char] = code
        connection.sync()
        for char in text:
            xtest.fake_input(connection, X.KeyPress, codes[char])
            xtest.fake_input(connection, X.KeyRelease, codes[char])
            connection.sync()
            time.sleep(0.02)
        time.sleep(0.1)  # Let the focused app consume keys before restoring the map.
    finally:
        try:
            for code, row in saved:
                with suppress(Exception):
                    xtest.fake_input(connection, X.KeyRelease, code)
                connection.change_keyboard_mapping(code, [row])
            connection.sync()
        finally:
            connection.close()


def press_key(key: str) -> None:
    """单键(特殊键走 KEY_SYM,单字符走 KEY_STRING)。"""
    pyatspi = _pyatspi()
    sym = _KEYSYMS.get(key.lower())
    if sym:
        from Xlib import XK

        pyatspi.Registry.generateKeyboardEvent(XK.string_to_keysym(sym), "", pyatspi.KEY_SYM)
        return
    if len(key) == 1:
        pyatspi.Registry.generateKeyboardEvent(0, key, pyatspi.KEY_STRING)
        return
    raise KeyError(f"unknown_key:{key}")


def press_chord(keys: list[str], modifiers: list[str]) -> None:
    from Xlib import XK, display

    pyatspi = _pyatspi()
    connection = display.Display()
    names = {"ctrl": "Control_L", "alt": "Alt_L", "shift": "Shift_L", "winleft": "Super_L"}
    pressed = []
    try:
        symbols = [names[modifier] for modifier in modifiers]
        symbols.extend(_KEYSYMS.get(key.lower(), key) for key in keys)
        codes = [connection.keysym_to_keycode(XK.string_to_keysym(symbol)) for symbol in symbols]
        if not all(codes):
            raise KeyError("unknown key in chord")
        try:
            for code in codes:
                pressed.append(code)
                pyatspi.Registry.generateKeyboardEvent(code, "", pyatspi.KEY_PRESS)
        finally:
            for code in reversed(pressed):
                pyatspi.Registry.generateKeyboardEvent(code, "", pyatspi.KEY_RELEASE)
    finally:
        connection.close()


def click_point(x: float, y: float, button: str = "left") -> None:
    pyatspi = _pyatspi()
    mapping = {
        "left": pyatspi.MOUSE_B1C,
        "middle": pyatspi.MOUSE_B2C,
        "right": pyatspi.MOUSE_B3C,
    }
    kind = mapping.get(button, pyatspi.MOUSE_B1C)
    pyatspi.Registry.generateMouseEvent(int(x), int(y), kind)


def scroll_element(element: Any, direction: str, pages: float) -> None:
    import time

    pyatspi = _pyatspi()
    queue = [element]
    visited = 0
    deadline = time.monotonic() + 5
    while queue and visited < 400 and time.monotonic() < deadline:
        candidate = queue.pop(0)
        visited += 1
        if candidate.getRoleName() == "scroll bar":
            horizontal = candidate.getState().contains(pyatspi.STATE_HORIZONTAL)
            if horizontal == (direction in ("left", "right")):
                value = candidate.queryValue()
                if value.maximumValue > value.minimumValue:
                    step = value.minimumIncrement or (value.maximumValue - value.minimumValue) / 100
                    delta = step * 10 * pages * (-1 if direction in ("up", "left") else 1)
                    expected = max(
                        value.minimumValue, min(value.maximumValue, value.currentValue + delta)
                    )
                    value.currentValue = expected
                    if abs(value.currentValue - expected) > 0.001:
                        raise KeyError("scroll range rejected the requested value")
                    return
        queue.extend(children(candidate))
    raise KeyError("element has no accessible scroll range")
