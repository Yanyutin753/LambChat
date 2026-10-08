"""macOS computer-use 后端(atomacos)。

Apple Accessibility API 经 PyObjC;TCC 授权对象为 LambChat.app(辅助功能
= AX 读取与 pyautogui 事件注入;屏幕录制 = 截屏含窗口内容)。
"""

from __future__ import annotations

from typing import Any

import atomacos
from atomacos import _a11y


def ax_trusted() -> bool:
    try:
        return bool(_a11y.AXIsProcessTrusted())
    except Exception:  # noqa: BLE001 - 预检永不抛
        return False


def frontmost_pid() -> int | None:
    if not ax_trusted():
        return None  # 未授权的 AX 系统调用可能被消息超时拖住,不碰
    try:
        # 纯 AX 路径:system-wide 元素的 AXFocusedApplication(atomacos 自带的
        # frontmost() 是 NSWorkspace + 逐 app AX 轮询——AppKit 非主线程死等 +
        # N 次超时,均不可用,见 list_apps 注释)
        system = atomacos.NativeUIElement.getSystemObject()
        focused = system.AXFocusedApplication
        return focused.pid if focused is not None else None
    except Exception:  # noqa: BLE001 - system-wide AX is unavailable on some macOS sessions
        import re
        import subprocess

        # Launch Services reports focus even when the foreground app has no window.
        front = subprocess.run(
            ["/usr/bin/lsappinfo", "front"], capture_output=True, text=True, timeout=2
        ).stdout.strip()
        info = subprocess.run(
            ["/usr/bin/lsappinfo", "info", "-only", "pid", front],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
        match = re.search(r"\bpid\s*=\s*(\d+)", info)
        return int(match[1]) if match else None


def list_apps() -> list[dict[str, Any]]:
    # 应用发现只用 ps 子进程:① 绝不走逐 app 的 AX 调用——未授权时每次
    # AXUIElement 消息都可能被拖满超时(81 app × 数秒 = E2E 实测撞 exec 超时);
    # ② NSWorkspace/AppKit 在非主线程会死等主 runloop——daemon 的 op 跑在
    # to_thread 工作线程(同样 E2E 实测卡死)。ps 免 TCC、线程安全、~1s。
    import subprocess

    rows: list[dict[str, Any]] = []
    output = subprocess.run(
        ["ps", "axo", "pid=,comm="], capture_output=True, text=True, timeout=10
    ).stdout
    for line in output.splitlines():
        line = line.strip()
        if ".app/Contents/MacOS/" not in line:
            continue
        pid_text, _, comm = line.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        name = comm.strip().rsplit("/Contents/MacOS/", 1)[0].rsplit("/", 1)[-1]
        rows.append({"pid": pid, "name": name.removesuffix(".app")})
    return rows


def _point(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, IndexError, ValueError):
        return None


def _bounds(element: Any) -> list[float] | None:
    position = _point(getattr(element, "AXPosition", None))
    size = _point(getattr(element, "AXSize", None))
    if not position or not size:
        return None
    return [position[0], position[1], size[0], size[1]]


def _scalar(element: Any, attribute: str) -> Any:
    try:
        value = getattr(element, attribute, None)
    except Exception:  # noqa: BLE001 - AX getter 对不支持属性抛错
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    return None


def app_by_pid(pid: int) -> Any:
    return atomacos.getAppRefByPid(pid)


def windows(pid: int) -> list[dict[str, Any]]:
    app = app_by_pid(pid)
    rows = []
    for index, window in enumerate(app.windows()):
        rows.append(
            {
                "window_id": index,
                "title": _scalar(window, "AXTitle") or "",
                "subrole": _scalar(window, "AXSubrole"),
                "main": bool(_scalar(window, "AXMain")),
                "focused": bool(_scalar(window, "AXFocused")),
                "bounds": _bounds(window),
                "handle": window,
            }
        )
    return rows


def pick_window(pid: int, window_id: int | None) -> tuple[Any, dict[str, Any]]:
    # atomacos 无 CGWindowID 通道;window_id 为 windows() 列表序号(ops 层换算)
    rows = windows(pid)
    if window_id is not None:
        if 0 <= window_id < len(rows):
            row = rows[window_id]
            return row["handle"], {k: row[k] for k in ("window_id", "title", "bounds", "focused")}
        raise KeyError(f"window index {window_id} out of range")
    for row in rows:
        if row["focused"]:
            return row["handle"], {k: row[k] for k in ("window_id", "title", "bounds", "focused")}
    for row in rows:
        if row["main"]:
            return row["handle"], {k: row[k] for k in ("window_id", "title", "bounds", "focused")}
    if rows:
        row = rows[0]
        return row["handle"], {k: row[k] for k in ("window_id", "title", "bounds", "focused")}
    raise KeyError("app has no accessible windows")


def children(element: Any) -> list[Any]:
    for attribute in ("AXVisibleChildren", "AXChildren"):
        try:
            value = getattr(element, attribute, None)
        except Exception:  # noqa: BLE001
            value = None
        if isinstance(value, list) and value:
            return value
        if isinstance(value, list):
            return value
    return []


def row_of(element: Any) -> dict[str, Any]:
    try:
        actions = list(element.getActions())
    except Exception:  # noqa: BLE001
        actions = []
    role = _scalar(element, "AXRole")
    subrole = _scalar(element, "AXSubrole")
    protected = subrole == "AXSecureTextField" or role == "AXSecureTextField"
    value = None if protected else _scalar(element, "AXValue")
    return {
        "kind": _scalar(element, "AXRole"),
        "title": _scalar(element, "AXTitle"),
        "value": value,
        "actions": actions,
        "bounds": _bounds(element),
    }


def perform(element: Any, action: str) -> None:
    # ops 层传语义名(click/context_menu)或树的 actions= 原名(AXPress/AXShowMenu…)
    mapped = {
        "click": "AXPress",
        "context_menu": "AXShowMenu",
        "press": "AXPress",
    }.get(action.removeprefix("AX").lower(), action)
    if not mapped.startswith("AX"):
        mapped = f"AX{mapped[:1].upper()}{mapped[1:]}"
    fn = getattr(element, mapped, None)
    if callable(fn):
        fn()
        return
    raise KeyError(f"action {action} not available on element")


def set_value(element: Any, text: str) -> None:
    try:
        element.setString(text)
    except Exception:  # noqa: BLE001 - 非可设置元素
        try:
            element.AXValue = text
        except Exception as exc:  # noqa: BLE001
            raise KeyError(f"element not settable: {exc}") from exc


def press_chord(keys: list[str], modifiers: list[str]) -> None:
    """Set modifier flags on each key event; separate modifier events can race."""
    import Quartz
    from pyautogui import isShiftCharacter  # noqa: N813
    from pyautogui._pyautogui_osx import keyboardMapping  # noqa: N813

    modifier_flags = {
        "command": Quartz.kCGEventFlagMaskCommand,
        "ctrl": Quartz.kCGEventFlagMaskControl,
        "option": Quartz.kCGEventFlagMaskAlternate,
        "shift": Quartz.kCGEventFlagMaskShift,
    }
    flags = 0
    for modifier in modifiers:
        flags |= modifier_flags[modifier]
    for key in keys:
        code = keyboardMapping.get(key)
        if code is None:
            raise KeyError(f"key {key} is unavailable")
        key_flags = flags | (Quartz.kCGEventFlagMaskShift if isShiftCharacter(key) else 0)
        for down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, code, down)
            Quartz.CGEventSetFlags(event, key_flags if down else 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def type_text(text: str) -> None:
    """Paste literal text while preserving images, files and rich clipboard formats."""
    import time

    import AppKit

    board = AppKit.NSPasteboard.generalPasteboard()
    saved = []
    for item in board.pasteboardItems() or []:
        copy = AppKit.NSPasteboardItem.alloc().init()
        for kind in item.types():
            data = item.dataForType_(kind)
            if data is None:
                raise RuntimeError("clipboard format cannot be preserved")
            raw = bytes(data)
            copy.setData_forType_(AppKit.NSData.dataWithBytes_length_(raw, len(raw)), kind)
        saved.append(copy)
    try:
        board.clearContents()
        board.setString_forType_(text, AppKit.NSPasteboardTypeString)
        press_chord(["v"], ["command"])
        time.sleep(0.1)  # Allow the target to consume the paste before restoring formats.
    finally:
        board.clearContents()
        if saved:
            board.writeObjects_(saved)


def set_focus(element: Any) -> None:
    """AX 聚焦元素(不抢前台窗口),并确认属性写入生效。"""
    element.AXFocused = True
    if not element.AXFocused:
        raise KeyError("element not focusable")


def screenshot(bounds: list[float] | None) -> Any:
    """Capture native screen-point bounds; cropping a Retina raster mixes coordinate units."""
    import subprocess
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from PIL import Image

    with TemporaryDirectory(prefix="lambchat-cua-") as directory:
        path = str(Path(directory) / "screen.png")
        command = ["/usr/sbin/screencapture", "-x", "-t", "png"]
        if bounds:
            x, y, width, height = bounds
            command.append(f"-R{int(x)},{int(y)},{max(1, int(width))},{max(1, int(height))}")
        else:
            command.append("-m")
        subprocess.run([*command, path], check=True, capture_output=True, timeout=10)
        with Image.open(path) as image:
            return image.copy()


def activate_window(pid: int, window_id: int | None) -> None:
    """把应用调到前台:`open -a <bundle>`(免 osascript——System Events 的
    自动化权限无人批准会无限卡死,见记忆 osascript-tcc-hang-gotcha)。

    AppKit/NSWorkspace 非主线程会死锁(记忆 computer-use-implementation),
    不碰;psutil 取可执行路径后向上找 .app bundle 交给系统 open。
    """
    import subprocess
    from pathlib import Path

    import psutil

    exe = Path(psutil.Process(pid).exe())
    bundle = next((p for p in exe.parents if p.name.endswith(".app")), None)
    if bundle is None:
        raise KeyError(f"pid {pid} is not a bundled .app (exe={exe})")
    subprocess.Popen(["open", "-a", str(bundle)], start_new_session=True)
