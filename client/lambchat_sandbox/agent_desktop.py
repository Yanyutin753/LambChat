"""Pinned agent-desktop adapter; LambChat retains foreground and approval policy."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


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


class AgentDesktopBackend:
    driver_name = "agent-desktop-1.3.1"

    def __init__(self, binary: Path, native: Any):
        self.binary = binary
        self.native = native
        self.sessions: dict[str | None, str] = {}
        self.cursors: dict[str, dict] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.native, name)

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
            raise CuaOpError(code, json.dumps(error, ensure_ascii=False))
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
        from lambchat_sandbox.cua_ops import CuaOpError

        session = self._session()
        if session not in self.cursors:
            try:
                self.cursors[session] = self._call("cursor-overlay", "enable")
            except CuaOpError as exc:
                self.cursors[session] = {"rendered": False, "error": exc.code}
        return self.cursors[session]

    def windows(self, pid: int) -> list[dict]:
        from lambchat_sandbox.cua_backend import backend_platform

        # Avoid Windows' global UIA scan; Linux toolkit names can differ from process names.
        apps = (
            self._call("list-apps")["apps"]
            if backend_platform() in ("linux", "win32")
            else self.native.list_apps()
        )
        app = next((a for a in apps if a["pid"] == pid), None)
        if app is None:
            raise KeyError("app_not_found")
        result = self._call("list-windows", "--app", app["name"], "--timeout-ms", "5000")
        return [
            {
                "window_id": _window_number(w["id"]),
                "driver_window_id": w["id"],
                "title": w["title"],
                "focused": w.get("is_focused") is True,
                "bounds": _bounds(w.get("bounds")),
                "main": w.get("is_focused") is True,
            }
            for w in result
            if w["pid"] == pid
        ]

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
            element["_tree"] = result["tree"]
            element["_window"]["driver_complete"] = result.get("complete", False)
        return element.get("_tree", element)

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

    def refresh_element(self, element: dict) -> dict:
        return self._call(
            "snapshot",
            "--root",
            self._node(element)["ref_id"],
            "--compact",
            "--include-bounds",
            "--timeout-ms",
            "5000",
        )["tree"]

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
        return self._call(commands[action], self._node(element)["ref_id"])

    def set_value(self, element: dict, text: str) -> dict:
        self._enable_cursor()
        return self._call("set-value", self._node(element)["ref_id"], "--stdin", text=text)

    def set_focus(self, element: dict) -> None:
        self.perform(element, "Focus")

    def activate_window(self, pid: int, window_id: int | None) -> None:
        _, window = self.pick_window(pid, window_id)
        self._call("focus-window", "--window-id", window["driver_window_id"])

    def click_point(self, x: float, y: float, button: str = "left", *, count: int = 1) -> dict:
        self._enable_cursor()
        return self._call(
            "--headed", "mouse-click", f"--xy={x},{y}", "--button", button, "--count", str(count)
        )

    click_point_repeated = click_point

    def scroll_element(self, element: dict, direction: str, pages: float) -> None:
        from lambchat_sandbox.cua_backend import backend_platform

        self._enable_cursor()
        self._call(
            *(["--headed"] if backend_platform() == "linux" else []),
            "scroll",
            self._node(element)["ref_id"],
            "--direction",
            direction,
            "--amount",
            str(max(1, round(pages * 10))),
        )
