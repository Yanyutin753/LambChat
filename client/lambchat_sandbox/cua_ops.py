"""computer-use op 实现:平台无关的观察/动作层。

复刻 ZCode computer-use 的核心语义契约:

- **observe → act → observe** 循环;元素索引寻址该应用**最近一次**观察,
  新观察会重新编号,失效索引报 ``element_unavailable``;
- **无障碍优先**:元素动作用 AX/UIA/AT-SPI 接口(后台应用可操作,不抢
  焦点);坐标/键盘走 pyautogui 事件兜底,要求目标已在前台
  (``foreground_required``,事件策略绝不替用户激活应用);
- 全部观察带时间/数量预算,任何 op 都不会无限占用线程(osascript 卡死教训);
- 截屏走 pyautogui/pyscreeze(窗口 region 优先),缩放+jpeg 控制在结果预算内。

平台差异由 ``cua_backend`` 调度(macOS atomacos / Windows pywinauto /
Linux dogtail);本模块只面对统一的 duck-typed 后端接口。
"""

from __future__ import annotations

import base64
import io
import os
import time
from typing import Any

from lambchat_sandbox import cua_backend

CUA_OPS = frozenset(
    {
        "cua_status",
        "cua_apps",
        "cua_launch",
        "cua_windows",
        "cua_state",
        "cua_activate",
        "cua_click",
        "cua_set_value",
        "cua_type",
        "cua_key",
        "cua_scroll",
        "cua_action",
    }
)
"""computer-use op 清单(daemon.py 据此分发到本模块)。"""

# 观察与动作预算:大树的走查、输入注入都不能无限占用 daemon 线程。
STATE_TIME_BUDGET = 5.0
STATE_MAX_ELEMENTS = 400
ELEMENT_CACHE_TTL = 180.0
ELEMENT_CACHE_MAX_APPS = 8
# 截屏结果预算:relay 的 SANDBOX_RESULTS_MAX_BYTES=2MiB,留出 JSON 余量。
SCREENSHOT_MAX_BYTES = 1_500_000
SCREENSHOT_MAX_DIMENSION = 1568

TEXT_VALUE_MAX = 200
TEXT_TITLE_MAX = 120

# 工具键名 → pyautogui 键名
_KEY_MAP = {
    "return": "enter",
    "enter": "enter",
    "escape": "esc",
    "delete": "backspace",
    "forwarddelete": "delete",
    "space": "space",
    "tab": "tab",
    "left": "left",
    "right": "right",
    "down": "down",
    "up": "up",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
}


class CuaOpError(Exception):
    """op 级结构化错误(收敛进 result.error,不炸通道)。"""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _backend() -> Any:
    try:
        return cua_backend.backend()
    except cua_backend.UnsupportedBackendError as exc:
        raise CuaOpError("unsupported_platform", str(exc)) from exc


def _pyautogui() -> Any:
    try:
        import pyautogui

        return pyautogui
    except (ImportError, SystemExit) as exc:
        raise CuaOpError("unsupported_platform", f"pyautogui_missing:{exc}") from exc


def _is_mac() -> bool:
    return cua_backend.backend_platform() == "darwin"


def _require_ax() -> None:
    backend = _backend()
    if not backend.ax_trusted():
        raise CuaOpError(
            "ax_not_trusted",
            "grant Accessibility to LambChat.app in System Settings > Privacy & Security"
            if _is_mac()
            else "enable accessibility (mac: grant to LambChat.app; linux: toolkit-accessibility + python3-atspi)",
        )


# ---------------------------------------------------------------------------
# 应用发现
# ---------------------------------------------------------------------------


def _op_apps(payload: dict) -> dict:  # noqa: ARG001
    backend = _backend()
    front_pid = None
    try:
        front_pid = backend.frontmost_pid()
    except Exception:  # noqa: BLE001 - 前台探测失败不阻塞清单
        pass
    rows = []
    for app in backend.list_apps():
        rows.append(
            {
                "pid": app["pid"],
                "name": app.get("name") or "",
                "bundle_id": None,
                "active": app["pid"] == front_pid if front_pid is not None else None,
            }
        )
    return {"apps": rows}


# ---------------------------------------------------------------------------
# 应用/URL 拉起(平台正确的 detach 启动)
# ---------------------------------------------------------------------------


def _op_launch(payload: dict) -> dict:
    """启动应用或打开 URL,进程与 daemon 同生命周期(daemon 自身不在任何
    Job/进程组里,子进程天然存活——绕开 exec 的 Windows Job 连坐与超时击杀)。

    - ``url``:经系统 opener(macOS ``open`` / Windows ``os.startfile`` /
      Linux ``xdg-open``,均免 shell);
    - ``app``:可执行路径 + 可选 ``args`` 列表(不经过 shell,杜绝注入)。
    Linux 下自动注入图形会话环境(WAYLAND_DISPLAY/DISPLAY/DBUS,SSH 起的
    daemon 常缺)。
    """
    import subprocess

    url = payload.get("url")
    app = payload.get("app")
    args = payload.get("args") or []
    if not isinstance(args, list):
        raise CuaOpError("invalid_arguments", "args must be a list")
    args = [str(a) for a in args]
    if not url and not app:
        raise CuaOpError("invalid_arguments", "need url or app")
    if url and app:
        raise CuaOpError("invalid_arguments", "url and app are mutually exclusive")

    platform = cua_backend.backend_platform()
    try:
        if url:
            if platform == "darwin":
                subprocess.Popen(["open", url], start_new_session=True)
            elif platform == "win32":
                os.startfile(url)  # noqa: S606 - 系统 opener,非 shell  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", url], start_new_session=True)
            return {"ok": True, "kind": "url", "target": url}
        # app 路径启动(不走 shell);裸名(如 "firefox")经 PATH 解析——
        # 2026-10-08 xiaoxin 实测 agent 常用裸名,直接 Popen 报
        # launch_failed: No such file or directory
        import shutil

        resolved = str(app)
        if not os.path.isfile(resolved) and os.sep not in str(app):
            which = shutil.which(str(app))
            if which:
                resolved = which
        argv = [resolved, *args]
        env = None
        if platform.startswith("linux"):
            env = dict(os.environ)
            runtime_dir = f"/run/user/{os.getuid()}"
            env.setdefault("XDG_RUNTIME_DIR", runtime_dir)
            env.setdefault("WAYLAND_DISPLAY", "wayland-0")
            env.setdefault("DISPLAY", ":0")
            env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime_dir}/bus")
        creationflags = 0
        if platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            argv,
            start_new_session=(platform != "win32"),
            env=env,
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "kind": "app", "target": argv[0], "pid": proc.pid}
    except OSError as exc:
        raise CuaOpError("launch_failed", str(exc)) from exc


# ---------------------------------------------------------------------------
# 元素缓存(索引寻址最近一次观察)
# ---------------------------------------------------------------------------


class _Observed:
    __slots__ = ("ts", "elements", "window")

    def __init__(self, elements: list[Any], window: dict[str, Any]):
        self.ts = time.monotonic()
        self.elements = elements
        self.window = window


_OBSERVATIONS: dict[str, _Observed] = {}


def _cache_key(pid: int, window_id: int | None) -> str:
    return f"{pid}:{window_id if window_id is not None else 'main'}"


def _drop(key: str) -> None:
    _OBSERVATIONS.pop(key, None)


def _store_observation(pid: int, window_id: int | None, observed: _Observed) -> None:
    key = _cache_key(pid, window_id)
    now = time.monotonic()
    for stale_key in [k for k, v in _OBSERVATIONS.items() if now - v.ts > ELEMENT_CACHE_TTL]:
        _drop(stale_key)
    while len(_OBSERVATIONS) >= ELEMENT_CACHE_MAX_APPS:
        oldest = min(_OBSERVATIONS, key=lambda k: _OBSERVATIONS[k].ts)
        _drop(oldest)
    _drop(key)
    _OBSERVATIONS[key] = observed


def _resolve_index(pid: int, window_id: int | None, index: Any) -> Any:
    if window_id is not None:
        observed = _OBSERVATIONS.get(_cache_key(pid, window_id))
    else:
        # 索引寻址该应用**最近一次**观察(未显式钉窗口时),与 ZCode 语义一致
        candidates = [v for k, v in _OBSERVATIONS.items() if k.startswith(f"{pid}:")]
        observed = max(candidates, key=lambda v: v.ts) if candidates else None
    if observed is None or time.monotonic() - observed.ts > ELEMENT_CACHE_TTL:
        raise CuaOpError("stale_state", "observe again with cua_state before acting")
    if not isinstance(index, int) or index < 0 or index >= len(observed.elements):
        raise CuaOpError("element_unavailable", f"index {index!r} not in latest observation")
    return observed.elements[index]


# ---------------------------------------------------------------------------
# 窗口与树观察
# ---------------------------------------------------------------------------


def _resolve_app_ref(payload: dict) -> int:
    pid = payload.get("pid")
    if isinstance(pid, int) and pid > 0:
        return pid
    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        lowered = name.strip().lower()
        for app in _backend().list_apps():
            if (app.get("name") or "").lower() == lowered:
                return app["pid"]
        raise CuaOpError("app_not_found", name)
    raise CuaOpError("invalid_arguments", "need pid or name")


def _op_windows(payload: dict) -> dict:
    _require_ax()
    backend = _backend()
    pid = _resolve_app_ref(payload)
    try:
        rows = backend.windows(pid)
    except Exception as exc:  # noqa: BLE001 - 平台后端异常收敛
        raise CuaOpError("ax_error", str(exc)) from exc
    cleaned = [{k: v for k, v in row.items() if k != "handle"} for row in rows]
    return {"pid": pid, "windows": cleaned}


def _walk_tree(root: Any) -> tuple[list[dict[str, Any]], list[Any], bool]:
    """BFS 走查(可见子树优先),带时间与数量预算。

    返回 (行列表, 元素句柄列表, 是否截断);两个列表同序,索引即下标。
    """
    backend = _backend()
    deadline = time.monotonic() + STATE_TIME_BUDGET
    rows: list[dict[str, Any]] = []
    elements: list[Any] = []
    truncated = False
    queue: list[tuple[Any, int]] = [(root, 0)]
    while queue:
        if len(rows) >= STATE_MAX_ELEMENTS or time.monotonic() > deadline:
            truncated = True
            break
        element, depth = queue.pop(0)
        try:
            row = backend.row_of(element)
        except Exception:  # noqa: BLE001 - 单元素元数据失败跳过不中断
            continue
        row["depth"] = depth
        rows.append(row)
        elements.append(element)
        if depth >= 30:
            continue
        for child in backend.children(element):
            queue.append((child, depth + 1))
    return rows, elements, truncated


def _render_tree(rows: list[dict[str, Any]], window: dict[str, Any], truncated: bool) -> str:
    lines = [f"window: {window.get('title') or ''} (id={window.get('window_id')})"]
    for index, row in enumerate(rows):
        indent = "  " * row["depth"]
        kind = row.get("kind") or "Unknown"
        label = f"[{index}] {kind}"
        if row.get("title"):
            label += f" {row['title'][:TEXT_TITLE_MAX]!r}"
        if row.get("value") is not None:
            label += f" value={str(row['value'])[:TEXT_VALUE_MAX]!r}"
        if row.get("actions"):
            label += " actions=" + ",".join(str(a) for a in row["actions"])
        lines.append(f"{indent}{label}")
    if truncated:
        lines.append("[tree truncated by element/time budget]")
    return "\n".join(lines)


def _op_state(payload: dict) -> dict:
    _require_ax()
    backend = _backend()
    pid = _resolve_app_ref(payload)
    window_id = payload.get("window_id")
    try:
        window_element, window_info = backend.pick_window(
            pid, window_id if isinstance(window_id, int) else None
        )
    except KeyError as exc:
        raise CuaOpError("window_not_found", str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise CuaOpError("ax_error", str(exc)) from exc
    rows, elements, truncated = _walk_tree(window_element)
    resolved_window_id = window_info.get("window_id")
    _store_observation(pid, resolved_window_id, _Observed(elements, window_info))
    result: dict[str, Any] = {
        "pid": pid,
        "window": window_info,
        "element_count": len(rows),
        "truncated": truncated,
        "state": _render_tree(rows, window_info, truncated),
    }
    if payload.get("include_screenshot"):
        try:
            result["screenshot"] = _capture(window_info.get("bounds"))
        except CuaOpError as exc:
            result["screenshot"] = {"error": exc.code, "detail": exc.detail}
    return result


# ---------------------------------------------------------------------------
# 截屏(pyautogui/pyscreeze,窗口 region 优先)
# ---------------------------------------------------------------------------


def _capture(bounds: list[float] | None) -> dict[str, Any]:
    backend = _backend()  # 平台可用性预检
    if _is_mac():
        import Quartz

        if not Quartz.CGPreflightScreenCaptureAccess():
            raise CuaOpError("screen_recording_denied", "grant Screen Recording to LambChat.app")
    try:
        native_capture = getattr(backend, "screenshot", None)
        if callable(native_capture):
            image = native_capture(bounds)
        elif bounds:
            region = (
                int(bounds[0]),
                int(bounds[1]),
                max(1, int(bounds[2])),
                max(1, int(bounds[3])),
            )
            image = _pyautogui().screenshot(region=region)
        else:
            image = _pyautogui().screenshot()
    except Exception as exc:  # noqa: BLE001
        raise CuaOpError("screenshot_failed", str(exc)) from exc
    if image is None:
        raise CuaOpError("screenshot_failed", "capture returned nothing")
    width, height = image.size
    if width * height < 100:
        raise CuaOpError(
            "screen_recording_denied",
            "capture is empty — grant Screen Recording to LambChat.app"
            if _is_mac()
            else "capture is empty (X11 required on Linux)",
        )
    try:
        if max(width, height) > SCREENSHOT_MAX_DIMENSION:
            scale = SCREENSHOT_MAX_DIMENSION / max(width, height)
            image = image.resize((int(width * scale), int(height * scale)))
            width, height = image.size
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=60)
        data = buffer.getvalue()
        if len(data) > SCREENSHOT_MAX_BYTES:
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=40)
            data = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001
        raise CuaOpError("screenshot_failed", str(exc)) from exc
    return {
        "mime": "image/jpeg",
        "width": width,
        "height": height,
        "data_b64": base64.b64encode(data).decode("ascii"),
    }


# ---------------------------------------------------------------------------
# 动作
# ---------------------------------------------------------------------------


def _require_foreground(pid: int) -> None:
    front = None
    try:
        front = _backend().frontmost_pid()
    except Exception:  # noqa: BLE001
        pass
    if front != pid:
        raise CuaOpError(
            "foreground_required",
            "event strategy never activates apps; act on an element instead",
        )


def _element_center(element: Any) -> tuple[float, float]:
    row = _backend().row_of(element)
    bounds = row.get("bounds")
    if not bounds:
        raise CuaOpError("element_unavailable", "element has no bounds")
    return bounds[0] + bounds[2] / 2, bounds[1] + bounds[3] / 2


def _op_click(payload: dict) -> dict:
    _require_ax()
    backend = _backend()
    pid = _resolve_app_ref(payload)
    target = payload.get("target") or {}
    button = payload.get("mouse_button") or "left"
    clicks = int(payload.get("click_count") or 1)
    if button not in ("left", "right", "middle"):
        raise CuaOpError("invalid_arguments", f"mouse_button:{button}")
    if target.get("type") == "element":
        element = _resolve_index(pid, payload.get("window_id"), target.get("index"))
        semantic = "click" if button == "left" else "context_menu"
        try:
            backend.perform(element, semantic)
        except KeyError as exc:
            raise CuaOpError("action_failed", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise CuaOpError("action_failed", str(exc)) from exc
        return {"ok": True, "strategy": "a11y", "action": semantic}
    _require_foreground(pid)
    try:
        x = float(target["x"])
        y = float(target["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CuaOpError("invalid_arguments", "target needs x/y") from exc
    native_click = getattr(_backend(), "click_point", None)
    if callable(native_click):
        native_click(x, y, button)  # Linux: AT-SPI 鼠标合成
        return {"ok": True, "strategy": "a11y-event", "x": x, "y": y}
    pyautogui = _pyautogui()
    for _ in range(max(1, min(clicks, 3))):
        if button == "right":
            pyautogui.rightClick(x=x, y=y)
        elif button == "middle":
            pyautogui.middleClick(x=x, y=y) if hasattr(
                pyautogui, "middleClick"
            ) else pyautogui.click(x=x, y=y, button="middle")
        else:
            pyautogui.click(x=x, y=y)
    return {"ok": True, "strategy": "event", "x": x, "y": y}


def _op_set_value(payload: dict) -> dict:
    _require_ax()
    backend = _backend()
    pid = _resolve_app_ref(payload)
    target = payload.get("target") or {}
    if target.get("type") != "element":
        raise CuaOpError("invalid_arguments", "set_value needs an element target")
    value = payload.get("value")
    if not isinstance(value, str):
        raise CuaOpError("invalid_arguments", "value must be text")
    element = _resolve_index(pid, payload.get("window_id"), target.get("index"))
    try:
        backend.set_value(element, value)
    except KeyError as exc:
        raise CuaOpError("action_failed", f"{exc} (element may not be settable)") from exc
    except Exception as exc:  # noqa: BLE001
        raise CuaOpError("action_failed", str(exc)) from exc
    return {"ok": True}


def _type_text(text: str) -> None:
    backend = _backend()
    native = getattr(backend, "type_text", None)
    if callable(native):
        native(text)  # Linux: AT-SPI KEY_STRING(Wayland 原生)
        return
    pyautogui = _pyautogui()
    if all(ord(ch) < 128 for ch in text):
        pyautogui.typewrite(text, interval=0.01)
        return
    # Non-ASCII fallback for platforms without native text injection.
    import pyperclip

    previous = pyperclip.paste()
    try:
        pyperclip.copy(text)
        pyautogui.hotkey(*(["command", "v"] if _is_mac() else ["ctrl", "v"]))
    finally:
        pyperclip.copy(previous)


def _op_type(payload: dict) -> dict:
    """输入文本。带元素索引时优先走免前台路径:AX/UIA 聚焦元素 →
    ValuePattern/EditableText 直写——后台窗口也能输入,绕开事件策略的
    foreground 门槛(实测 Chromium 地址框有 ValuePattern,直写即可)。
    直写失败再回退合成键盘(需前台)。
    """
    _require_ax()
    pid = _resolve_app_ref(payload)
    text = payload.get("text")
    if not isinstance(text, str) or not text:
        raise CuaOpError("invalid_arguments", "text required")

    # index 取值兼容两层:工具层规范是 target.index(与 click/set_value 同),
    # 顶层 index 供 op 直调。只读顶层会让元素路径在真实链路上静默失效。
    target_ref = payload.get("target") or {}
    index = payload.get("index")
    if index is None and isinstance(target_ref, dict):
        index = target_ref.get("index")
    if index is not None:
        element = _resolve_index(pid, payload.get("window_id"), index)
        backend = _backend()
        try:
            backend.set_focus(element)
        except Exception:  # noqa: BLE001 - 聚焦尽力而为,直写不依赖它
            pass
        try:
            backend.set_value(element, text)
            return {"ok": True, "strategy": "a11y", "method": "set_value"}
        except Exception:  # noqa: BLE001 - 元素不可直写,回退事件输入
            pass
        # set_focus 在 Windows 会顺带把窗口调到前台;再查一次前台,过则打字
        try:
            _require_foreground(pid)
        except CuaOpError as exc:
            raise CuaOpError(
                "foreground_required",
                f"{exc.detail}; element is not directly settable — "
                "activate the window (action=activate) first, or use set_value on a settable element",
            ) from exc
        _type_text(text)
        return {"ok": True, "strategy": "event", "method": "focused-typing"}

    _require_foreground(pid)
    _type_text(text)
    return {"ok": True, "strategy": "event", "method": "raw-typing"}


def _op_activate(payload: dict) -> dict:
    """显式把目标应用/窗口调到前台(agent 主动调用)。

    与「事件策略绝不自动激活」不冲突:禁的是静默抢焦点,给模型一个
    显式 activate 动作是 ZCode 同款契约——key 快捷键类操作的前置步骤。
    """
    backend = _backend()
    pid = _resolve_app_ref(payload)
    try:
        backend.activate_window(pid, payload.get("window_id"))
    except CuaOpError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CuaOpError("action_failed", f"activate failed: {exc}") from exc
    return {"ok": True, "pid": pid}


def _map_modifiers(text: str | None) -> list[str]:
    if not text:
        return []
    parts: list[str] = []
    for token in text.lower().split("+"):
        token = token.strip()
        if not token:
            continue
        if token in ("cmd", "command", "meta", "win"):
            parts.append("command" if _is_mac() else "winleft")
        elif token in ("ctrl", "control"):
            parts.append("ctrl")
        elif token in ("alt", "option"):
            parts.append("option" if _is_mac() else "alt")
        elif token == "shift":
            parts.append("shift")
        else:
            raise CuaOpError("invalid_arguments", f"unknown_modifier:{token}")
    return parts


def _op_key(payload: dict) -> dict:
    _require_ax()
    backend = _backend()
    pid = _resolve_app_ref(payload)
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise CuaOpError("invalid_arguments", "text required (e.g. 'return' or 'cmd+c')")
    repeat = max(1, min(int(payload.get("repeat") or 1), 50))
    chord_modifiers = [
        token.strip().lower()
        for token in text.split("+")
        if token.strip().lower()
        in ("cmd", "command", "meta", "win", "ctrl", "control", "alt", "option", "shift")
    ]
    modifier_keys = list(
        dict.fromkeys(
            _map_modifiers(payload.get("modifiers")) + _map_modifiers("+".join(chord_modifiers))
        )
    )
    keys = []
    for token in text.split("+"):
        token = token.strip().lower()
        if not token:
            continue
        if token in ("cmd", "command", "meta", "win", "ctrl", "control", "alt", "option", "shift"):
            continue  # 修饰键已与 modifiers 参数合并
        keys.append(_KEY_MAP.get(token, token))
    if not keys and not modifier_keys:
        raise CuaOpError("invalid_arguments", "no key in chord")
    _require_foreground(pid)

    native_chord = getattr(backend, "press_chord", None)
    if (
        callable(native_chord)
        and keys
        and (modifier_keys or len(keys) > 1 or not callable(getattr(backend, "press_key", None)))
    ):
        for _ in range(repeat):
            native_chord(keys, modifier_keys)
        return {"ok": True, "strategy": "a11y-event"}

    # 单键优先走后端原生合成(Linux/AT-SPI KEY_SYM,Wayland 原生可用)。
    # 2026-10-08 xiaoxin 实测:回车走 pyautogui 在无 X11 环境直接
    # unsupported_platform,agent 只能绕 URL 导航——单键是最高频操作。
    native_press = getattr(backend, "press_key", None)
    if callable(native_press) and not modifier_keys and len(keys) == 1:
        try:
            for _ in range(repeat):
                native_press(keys[0])
            return {"ok": True, "strategy": "a11y-event", "key": keys[0]}
        except Exception:  # noqa: BLE001 - 原生不支持该键回退 pyautogui
            pass

    pyautogui = _pyautogui()
    for _ in range(repeat):
        if modifier_keys and keys:
            pyautogui.hotkey(*modifier_keys, *keys)
        elif keys:
            for key in keys:
                pyautogui.press(key)
        else:
            pyautogui.hotkey(*modifier_keys)
    return {"ok": True}


def _op_scroll(payload: dict) -> dict:
    _require_ax()
    pid = _resolve_app_ref(payload)
    direction = payload.get("scroll_direction")
    if direction not in ("up", "down", "left", "right"):
        raise CuaOpError("invalid_arguments", "scroll_direction required")
    pages = max(0.0, min(float(payload.get("scroll_amount") or 1), 100))
    clicks = int(pages * 10)
    target = payload.get("target") or {}
    native_scroll = getattr(_backend(), "scroll_element", None)
    if target.get("type") == "element" and callable(native_scroll):
        element = _resolve_index(pid, payload.get("window_id"), target.get("index"))
        try:
            native_scroll(element, direction, pages)
            return {"ok": True, "strategy": "a11y", "clicks": clicks}
        except KeyError:
            pass
    _require_foreground(pid)
    pyautogui = _pyautogui()
    if target.get("type") == "element":
        element = _resolve_index(pid, payload.get("window_id"), target.get("index"))
        pyautogui.moveTo(*_element_center(element))
    elif target.get("type") == "coordinate":
        pyautogui.moveTo(float(target["x"]), float(target["y"]))
    magnitude = -clicks if direction in ("down", "left") else clicks
    try:
        if direction in ("left", "right"):
            pyautogui.hscroll(magnitude)
        else:
            pyautogui.scroll(magnitude)
    except Exception as exc:  # noqa: BLE001 - Wayland 等环境受限
        raise CuaOpError("action_failed", f"scroll unsupported: {exc}") from exc
    return {"ok": True, "clicks": clicks}


def _op_action(payload: dict) -> dict:
    _require_ax()
    backend = _backend()
    pid = _resolve_app_ref(payload)
    target = payload.get("target") or {}
    if target.get("type") != "element":
        raise CuaOpError("invalid_arguments", "action needs an element target")
    action = payload.get("action")
    if not isinstance(action, str) or not action:
        raise CuaOpError("invalid_arguments", "action required (name from the tree's actions=)")
    element = _resolve_index(pid, payload.get("window_id"), target.get("index"))
    try:
        backend.perform(element, action)
    except KeyError as exc:
        raise CuaOpError("action_failed", str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise CuaOpError("action_failed", str(exc)) from exc
    return {"ok": True, "action": action}


# ---------------------------------------------------------------------------
# 状态预检
# ---------------------------------------------------------------------------


def _op_status(payload: dict) -> dict:
    try:
        backend = _backend()
    except CuaOpError as exc:
        return {
            "platform": "unsupported",
            "ready": False,
            "accessibility": "unknown",
            "screen_recording": "unknown",
            "message": exc.detail,
        }
    try:
        ax_ok = backend.ax_trusted()
    except Exception:  # noqa: BLE001 - 预检永不抛
        ax_ok = False
    screen_state = "unknown"
    message = None
    if payload.get("probe_screen"):
        try:
            _capture(None)
            screen_state = "granted"
        except CuaOpError as exc:
            screen_state = "denied" if exc.code == "screen_recording_denied" else "unknown"
            message = f"{exc.code}: {exc.detail}"
    ready = ax_ok and (not payload.get("probe_screen") or screen_state == "granted")
    if not ax_ok:
        message = (
            "grant Accessibility (and Screen Recording) to LambChat.app"
            if _is_mac()
            else "enable accessibility: toolkit-accessibility + python3-atspi (linux)"
        )
    return {
        "platform": cua_backend.backend_platform(),
        "ready": ready,
        "accessibility": "granted" if ax_ok else "denied",
        "screen_recording": screen_state,
        "message": message,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

_CUA_HANDLERS = {
    "cua_status": _op_status,
    "cua_apps": _op_apps,
    "cua_launch": _op_launch,
    "cua_windows": _op_windows,
    "cua_state": _op_state,
    "cua_activate": _op_activate,
    "cua_click": _op_click,
    "cua_set_value": _op_set_value,
    "cua_type": _op_type,
    "cua_key": _op_key,
    "cua_scroll": _op_scroll,
    "cua_action": _op_action,
}


def handle_cua_op(op: str, payload: dict) -> dict:
    """执行一个 computer-use op。

    CuaOpError 与**一切**运行时异常都转为 ``{"error": ...}`` 结构化结果:
    生产实测(2026-10-08 Windows)未捕获的 COMError/pyperclip 缺失会裸穿到
    daemon 层 error 字符串,relay 包成 SANDBOX_EXEC_FAILED 后模型只见到
    模板文案而无从纠错——op 级异常必须在模型可读层收敛。
    """
    handler = _CUA_HANDLERS.get(op)
    if handler is None:
        raise ValueError(f"unknown cua op: {op}")
    try:
        return handler(payload or {})
    except CuaOpError as exc:
        return {"error": exc.code, "detail": exc.detail}
    except Exception as exc:  # noqa: BLE001 - COMError 等三方异常同样结构化
        return {"error": "op_failed", "detail": f"{type(exc).__name__}: {exc}"}
