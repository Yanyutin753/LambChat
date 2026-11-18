"""Pinned agent-desktop adapter; LambChat retains foreground and approval policy."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# ZCode's session cursor palette; the native driver renders the pointer, outline and ripple.
_CURSOR_FILLS = (
    "#FFE485",
    "#F698DB",
    "#E1EEAF",
    "#FFD3E4",
    "#92D1FF",
    "#FFD058",
    "#AFDFEE",
    "#FFBDB4",
    "#F72967",
    "#46C6D7",
    "#BCACDD",
)


def _cursor_fill(session_id: str | None) -> str:
    if not session_id or session_id == "default":
        return "#1F8CFF"
    suffix = re.search(r"(?:^|[-_.])([0-9]{1,18})$", session_id)
    if suffix:
        index = int(suffix[1]) - 1
    elif len(session_id) == 1 and session_id.isascii() and session_id.isalpha():
        index = ord(session_id.lower()) - ord("a")
    else:
        index = 2166136261
        for byte in session_id.encode("utf-8"):
            index = ((index ^ byte) * 16777619) & 0xFFFFFFFF
    return _CURSOR_FILLS[index % len(_CURSOR_FILLS)]


def binary_path() -> Path | None:
    name = "agent-desktop.exe" if sys.platform == "win32" else "agent-desktop"
    override = os.environ.get("LAMBCHAT_AGENT_DESKTOP")
    if override:
        path = Path(override)
    elif getattr(sys, "frozen", False):
        path = Path(getattr(sys, "_MEIPASS")) / "agent-desktop" / name
    else:
        path = Path(__file__).parents[1] / "resources" / "agent-desktop" / name
    return path if path.is_file() else None


def _bounds(value: dict | None) -> list | None:
    return [value[k] for k in ("x", "y", "width", "height")] if value else None


def _window_number(native_id: str) -> int:
    suffix = native_id.removeprefix("w-")
    if suffix.isdecimal():
        return int(suffix)
    return int.from_bytes(hashlib.sha256(native_id.encode()).digest()[:8], "big") & ((1 << 53) - 1)


def _windows_desktop_locked() -> bool:
    import ctypes
    import struct

    api = ctypes.WinDLL("wtsapi32", use_last_error=True)
    api.WTSQuerySessionInformationW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    api.WTSQuerySessionInformationW.restype = ctypes.c_int
    api.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    api.WTSFreeMemory.restype = None
    buffer = ctypes.c_void_p()
    size = ctypes.c_uint32()
    if not api.WTSQuerySessionInformationW(
        None, 0xFFFFFFFF, 25, ctypes.byref(buffer), ctypes.byref(size)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # WTSINFOEXW has a DWORD level followed by an 8-byte-aligned level-1 union.
        if not buffer.value or size.value < 20:
            raise OSError("Incomplete Windows session information")
        level, _, state, flags = struct.unpack("<I4xIIi", ctypes.string_at(buffer, 20))
        if level != 1 or flags not in (0, 1):
            raise OSError("Unknown Windows session lock state")
        return flags == 0 or state != 0  # Only WTSActive permits interactive control.
    finally:
        api.WTSFreeMemory(buffer)


class AgentDesktopBackend:
    driver_name = "agent-desktop-1.3.1"

    def __init__(self, binary: Path):
        self.binary = binary
        self.sessions: dict[str | None, str] = {}
        self.cursors: dict[str, dict] = {}

    def ax_trusted(self) -> bool:
        return self._call("permissions")["accessibility"]["state"] == "granted"

    def frontmost_pid(self) -> int | None:
        windows = self._call("list-windows")
        focused = {w["pid"] for w in windows if w.get("is_focused") is True}
        return next(iter(focused)) if len(focused) == 1 else None

    def desktop_locked(self) -> bool:
        # This is a session safety check, not an alternate CUA execution backend.
        if sys.platform == "win32":
            return _windows_desktop_locked()
        if sys.platform != "darwin":
            return False
        from Quartz import CGSessionCopyCurrentDictionary

        session = CGSessionCopyCurrentDictionary()
        return (
            not session
            or bool(session.get("CGSSessionScreenIsLocked"))
            or not session.get("kCGSSessionOnConsoleKey", False)
        )

    def _run(self, args: list[str], text: str | None = None) -> Any:
        from lambchat_sandbox.cua_ops import CuaOpError

        completed = subprocess.run(
            [str(self.binary), *args],
            input=text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        try:
            envelope = json.loads(completed.stdout)
        except ValueError as exc:
            raise CuaOpError("driver_failed", "agent-desktop returned invalid JSON") from exc
        if not envelope.get("ok"):
            error = envelope.get("error", {})
            code = error.get("code", "driver_failed").lower()
            if code in ("stale_ref", "snapshot_not_found", "ambiguous_target"):
                code = "stale_state"
            raise CuaOpError(code, error.get("message", code), context=error)
        data = envelope["data"]
        if isinstance(data, dict) and "disposition" in data:
            data.pop("steps", None)
            if isinstance(data.get("details"), dict):
                data["details"].pop("auto_wait", None)
                if not data["details"]:
                    data.pop("details")
        return data

    def _session(self) -> str:
        from lambchat_sandbox.cua_ops import _OBSERVATION_SESSION

        key = _OBSERVATION_SESSION.get()
        if key not in self.sessions:
            if len(self.sessions) >= 8:
                oldest = next(iter(self.sessions))
                expired = self.sessions.pop(oldest)
                self._run(["--session", expired, "session", "end"])
                self.cursors.pop(expired, None)
            self.sessions[key] = self._run(["session", "start", "--no-trace"])["session_id"]
        return self.sessions[key]

    def _call(self, *args: str, text: str | None = None) -> Any:
        return self._run(["--session", self._session(), *args], text)

    def _enable_cursor(self) -> dict:
        from lambchat_sandbox.cua_ops import _OBSERVATION_SESSION, CuaOpError

        session = self._session()
        if session not in self.cursors:
            try:
                self.cursors[session] = self._call(
                    "cursor-overlay",
                    "enable",
                    "--accent",
                    _cursor_fill(_OBSERVATION_SESSION.get()),
                    "--rim",
                    "#FFFFFF",
                    "--label",
                    "LambChat",
                    "--tremor",
                    "0",
                )
            except CuaOpError as exc:
                self.cursors[session] = {"rendered": False, "error": exc.code}
        return self.cursors[session]

    def list_apps(self) -> list[dict]:
        # Discovery and snapshots must use the same process names and IDs.
        return self._call("list-apps")["apps"]

    def windows(self, pid: int) -> list[dict]:
        from lambchat_sandbox.cua_backend import is_control_window

        apps = self.list_apps()
        app = next((a for a in apps if a["pid"] == pid), None)
        if app is None:
            raise KeyError("app_not_found")
        result = self._call("list-windows", "--app", app["name"], "--timeout-ms", "5000")
        rows = [
            {
                "window_id": _window_number(w["id"]),
                "driver_window_id": w["id"],
                "title": w["title"],
                "focused": w.get("is_focused") is True,
                "bounds": _bounds(w.get("bounds")),
                "main": w.get("is_focused") is True,
                "minimized": w.get("minimized") is True,
            }
            for w in result
            if w["pid"] == pid and not is_control_window(pid, w["title"])
        ]
        return rows

    def pick_window(self, pid: int, window_id: int | None) -> tuple[dict, dict]:
        rows = self.windows(pid)
        candidates = (
            [w for w in rows if w["window_id"] == window_id]
            if window_id is not None
            else [w for w in rows if w["focused"]]
        )
        if not candidates and window_id is None and len(rows) == 1:
            candidates = rows
        if len(candidates) != 1:
            raise KeyError("ambiguous or missing window; specify window_id from windows")
        window = candidates[0]
        return {"_window": window, "_pid": pid}, window

    def _node(self, element: dict) -> dict:
        if "_window" in element and "_tree" not in element:
            from lambchat_sandbox.cua_backend import backend_platform

            if element["_window"].get("minimized") and backend_platform() == "darwin":
                from lambchat_sandbox.cua_ops import CuaOpError

                raise CuaOpError(
                    "window_minimized", "Activate the window to restore it, then observe again"
                )
            result = self._call(
                "snapshot",
                "--window-id",
                element["_window"]["driver_window_id"],
                "--compact",
                "--include-bounds",
                "--timeout-ms",
                "5000",
            )
            owner = result.get("window", {})
            windows = self._call("list-windows", "--app", result["app"], "--timeout-ms", "5000")
            if owner.get("id") != element["_window"]["driver_window_id"] or not any(
                w["id"] == owner.get("id") and w["pid"] == element["_pid"] for w in windows
            ):
                from lambchat_sandbox.cua_ops import CuaOpError

                raise CuaOpError("stale_state", "window ownership changed")
            self._bind_paths(
                result["tree"], {"_window": element["_window"], "_pid": element["_pid"]}, []
            )
            element["_tree"] = result["tree"]
            element["_window"]["driver_complete"] = result.get("complete", False)
        return element.get("_tree", element)

    @staticmethod
    def _bind_paths(tree: dict, owner: dict, path: list[int]) -> None:
        pending = [(tree, path)]
        while pending:
            node, current_path = pending.pop()
            node["_driver_owner"] = owner
            node["_driver_path"] = current_path
            pending.extend(
                (child, [*current_path, index])
                for index, child in enumerate(node.get("children", []))
            )

    def row_of(self, element: dict) -> dict:
        node = self._node(element)
        return {
            "kind": node["role"],
            "title": node.get("name", ""),
            "value": node.get("value"),
            "bounds": _bounds(node.get("bounds")),
            "states": node.get("states", []),
            "actions": node.get("available_actions", []),
        }

    def children(self, element: dict) -> list:
        return self._node(element).get("children", [])

    def refresh_element(self, element: dict, window: dict) -> dict:
        from lambchat_sandbox.cua_ops import CuaOpError

        node = self._node(element)
        if not node.get("ref_id"):
            return self._refresh_subtree_by_path(node, window)
        try:
            result = self._call(
                "snapshot",
                "--root",
                self._reference(element),
                "--compact",
                "--include-bounds",
                "--timeout-ms",
                "5000",
            )
        except CuaOpError as exc:
            if (
                exc.code != "stale_state"
                or exc.context.get("details", {}).get("kind") != "identity_not_unique"
            ):
                raise
            # Only refresh reads may use a verified path; actions still require unique refs.
            return self._refresh_subtree_by_path(node, window)
        window["driver_complete"] = result.get("complete", False)
        if "_driver_owner" in node and "_driver_path" in node:
            self._bind_paths(result["tree"], node["_driver_owner"], node["_driver_path"])
        return result["tree"]

    def _refresh_subtree_by_path(self, node: dict, window: dict) -> dict:
        from lambchat_sandbox.cua_ops import CuaOpError

        owner, path = node.get("_driver_owner"), node.get("_driver_path")
        if not isinstance(owner, dict) or not isinstance(path, list):
            raise CuaOpError(
                "element_unavailable", "Element has no live reference; observe the window again"
            )
        fresh_owner = {"_window": dict(owner["_window"]), "_pid": owner["_pid"]}
        fresh = self._node(fresh_owner)
        try:
            for index in path:
                fresh = fresh["children"][index]
        except (KeyError, IndexError, TypeError) as exc:
            raise CuaOpError(
                "stale_state", "Element tree changed; observe the window again"
            ) from exc
        if any(fresh.get(key) != node.get(key) for key in ("role", "name", "bounds")):
            raise CuaOpError("stale_state", "Element identity changed; observe the window again")
        window["driver_complete"] = fresh_owner["_window"].get("driver_complete", False)
        return fresh

    def _reference(self, element: dict) -> str:
        from lambchat_sandbox.cua_ops import CuaOpError

        reference = self._node(element).get("ref_id")
        if not isinstance(reference, str) or not reference:
            raise CuaOpError(
                "element_unavailable",
                "Element is observable but has no action reference; observe again or use verified screenshot coordinates",
            )
        return reference

    def perform(self, element: dict, action: str) -> dict:
        commands = {
            "click": "click",
            "context_menu": "right-click",
            "Click": "click",
            "RightClick": "right-click",
            "ScrollTo": "scroll-to",
            "Check": "check",
            "Uncheck": "uncheck",
            "Hover": "hover",
            "Press": "click",
            "Focus": "focus",
            "SetFocus": "focus",
            "Toggle": "toggle",
            "Expand": "expand",
            "Collapse": "collapse",
            "AXPress": "click",
        }
        commands.update(
            {
                name: name
                for name in (
                    "right-click",
                    "focus",
                    "toggle",
                    "expand",
                    "collapse",
                    "check",
                    "uncheck",
                    "clear",
                    "scroll-to",
                )
            }
        )
        if action not in commands:
            raise KeyError(action)
        self._enable_cursor()
        prefix = ("--headed",) if commands[action] in {"focus", "hover"} else ()
        return self._call(*prefix, commands[action], self._reference(element))

    def set_value(self, element: dict, text: str) -> dict:
        self._enable_cursor()
        return self._call("set-value", self._reference(element), "--stdin", text=text)

    def set_focus(self, element: dict) -> None:
        self.perform(element, "Focus")

    def activate_window(self, pid: int, window_id: int | None) -> dict:
        _, window = self.pick_window(pid, window_id)
        if window.get("minimized"):
            self._call("restore", "--window-id", window["driver_window_id"])
        return self._call("focus-window", "--window-id", window["driver_window_id"])

    def click_point(self, x: float, y: float, button: str = "left", *, count: int = 1) -> dict:
        self._enable_cursor()
        return self._call(
            "--headed", "mouse-click", f"--xy={x},{y}", "--button", button, "--count", str(count)
        )

    def scroll_element(self, element: dict, direction: str, pages: float) -> dict:
        from lambchat_sandbox.cua_backend import backend_platform

        self._enable_cursor()
        return self._call(
            *(["--headed"] if backend_platform() == "linux" else []),
            "scroll",
            self._reference(element),
            "--direction",
            direction,
            "--amount",
            str(max(1, round(pages * 10))),
        )

    def press_chord(self, keys: list[str], modifiers: list[str], window: dict) -> dict:
        aliases = {
            "enter": "return",
            "esc": "escape",
            "winleft": "meta",
            "command": "cmd",
            "option": "alt",
            "delete": "forwarddelete",
            "backspace": "delete",
        }
        chord = "+".join(aliases.get(key, key) for key in [*modifiers, *keys])
        self._enable_cursor()
        return self._call("--headed", "press", chord, "--window-id", window["driver_window_id"])

    def type_text(self, text: str, window: dict) -> dict:
        from lambchat_sandbox.cua_ops import CuaOpError

        focused = self._call(
            "snapshot",
            "--window-id",
            window["driver_window_id"],
            "--surface",
            "focused",
            "--compact",
            "--timeout-ms",
            "5000",
        )
        if focused.get("window", {}).get("id") != window["driver_window_id"]:
            raise CuaOpError("stale_state", "Focused window changed; observe again")
        pending = [(focused["tree"], 0)]
        candidates = []
        while pending:
            node, depth = pending.pop()
            if (
                "focused" in node.get("states", [])
                and node.get("ref_id")
                and node.get("role") not in {"window", "dialog", "application"}
            ):
                candidates.append((depth, node))
            pending.extend((child, depth + 1) for child in node.get("children", []))
        deepest = max((depth for depth, _ in candidates), default=-1)
        targets = [node for depth, node in candidates if depth == deepest]
        if len(targets) != 1:
            raise CuaOpError(
                "element_unavailable",
                "Observe and select a unique focused text element before typing",
            )
        reference = self._reference(targets[0])
        self._enable_cursor()
        return self._call("--headed", "type", reference, "--stdin", text=text)

    def scroll_point(self, x: float, y: float, direction: str, amount: int) -> dict:
        magnitude = -amount if direction in ("down", "left") else amount
        axis = "dx" if direction in ("left", "right") else "dy"
        self._enable_cursor()
        return self._call(
            "--headed", "mouse-wheel", f"--x={x}", f"--y={y}", f"--{axis}={magnitude}"
        )

    def screenshot(self, bounds: list, window: dict | None = None) -> Any:
        from PIL import Image

        from lambchat_sandbox.cua_ops import CuaOpError

        args = ("--window-id", window["driver_window_id"]) if window else ("--screen", "0")
        for _ in range(2):
            result = self._call("screenshot", *args)
            image = Image.open(io.BytesIO(base64.b64decode(result["data"], validate=True)))
            image.load()
            # Judge the whole window before cropping: an element can legitimately be solid black.
            if not window or (image.getbbox() and image.convert("RGB").getbbox()):
                break
        else:
            raise CuaOpError("window_capture_blank", "Target window returned two blank frames")
        if window:
            left, top, width, height = window["bounds"]
            x, y, crop_width, crop_height = bounds
            if (
                width <= 0
                or height <= 0
                or x < left
                or y < top
                or x + crop_width > left + width
                or y + crop_height > top + height
            ):
                raise CuaOpError(
                    "screenshot_failed", "Capture bounds are outside the observed window"
                )
            sx, sy = image.width / width, image.height / height
            image = image.crop(
                (
                    round((x - left) * sx),
                    round((y - top) * sy),
                    round((x - left + crop_width) * sx),
                    round((y - top + crop_height) * sy),
                )
            )
        else:
            image = image.crop((0, 0, 10, 10))
        return image

    def launch(self, app: str, args: list[str]) -> dict:
        return self._call("launch", app, *(f"--arg={arg}" for arg in args))
