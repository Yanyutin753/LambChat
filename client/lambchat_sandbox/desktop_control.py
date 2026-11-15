"""Local shell takeover over inherited pipes; no network or Agent-callable resume."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import threading
import uuid
from collections.abc import Callable, Coroutine
from typing import Any


class DesktopControl:
    def __init__(self, emit: Callable[[dict], None], *, timeout: float = 10) -> None:
        self.emit = emit
        self.timeout = timeout
        self.paused = False
        self.needs_observation = False
        self.observed = False
        self.pending: tuple[str, asyncio.Future[bool]] | None = None
        self.active: asyncio.Task[dict] | None = None

    def command(self, message: dict) -> None:
        action = message.get("action")
        if action == "pause":
            self.paused = True
            self.needs_observation = True
            self.observed = False
            if self.active:
                self.active.cancel()
            if self.pending and not self.pending[1].done():
                self.pending[1].set_result(False)
            if not self.active:
                self.emit({"state": "paused"})
        elif action == "resume":
            # Do not allow resume to race the disposal of an in-flight input.
            if self.active:
                return
            self.paused = False
            self.emit({"state": "idle"})
        elif action == "permit" and self.pending:
            request, future = self.pending
            if message.get("request") == request and not future.done():
                future.set_result(message.get("allowed") is True and not self.paused)

    async def execute(self, op: str, run: Callable[[], Coroutine[Any, Any, dict]]) -> dict:
        if self.paused:
            return self._paused_result()
        if self.needs_observation and op not in {
            "cua_state",
            "cua_status",
            "cua_apps",
            "cua_windows",
            "cua_activate",
        }:
            return {"error": "observation_required", "detail": "Observe again after local takeover"}
        request = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending = request, future
        try:
            self.emit({"state": "request", "request": request})
            if not await asyncio.wait_for(future, self.timeout):
                if self.paused:
                    return self._paused_result()
                return {
                    "error": "desktop_control_unavailable",
                    "detail": "Local control window unavailable; no action was started",
                }
            self.emit({"state": "active"})
            self.active = asyncio.create_task(run())
            result = await self.active
            disposition = result.get("disposition")
            if result.get("error") and (
                result.get("retry") == "observe_first"
                or isinstance(disposition, dict)
                and disposition.get("retry") != "safe"
            ):
                self.needs_observation = True
                self.observed = False
            screenshot = result.get("screenshot") or {}
            focus_lost = (
                result.get("error") == "foreground_required"
                or screenshot.get("error") == "foreground_required"
            )
            if focus_lost and self.observed:
                self.command({"action": "pause"})
            if op == "cua_state" and not result.get("error") and not screenshot.get("error"):
                self.needs_observation = False
                self.observed = True
            return result
        except TimeoutError:
            if self.active is not None:
                self.needs_observation = True
                return {
                    "error": "timeout",
                    "disposition": "unknown",
                    "retry": "observe_first",
                    "detail": "Desktop action timed out; it may have partially completed",
                }
            return {
                "error": "desktop_control_unavailable",
                "detail": "Local control window did not acknowledge; no action was started",
            }
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if self.paused and current is not None and not current.cancelling():
                return self._paused_result()
            raise
        finally:
            self.pending = None
            self.active = None
            self.emit({"state": "paused" if self.paused else "idle"})

    @staticmethod
    def _paused_result() -> dict:
        return {
            "error": "desktop_control_paused",
            "disposition": "unknown",
            "detail": "The user took control locally. Stop computer actions and wait for the user to resume. An interrupted action may have partially completed; do not replay it. Observe again after resuming.",
        }


_control: DesktopControl | None = None


def local_control() -> DesktopControl | None:
    global _control
    token = os.environ.get("LAMBCHAT_DESKTOP_CONTROL")
    if not token:
        return None  # Standalone CLI daemon retains its existing non-shell contract.
    if _control is None:
        loop = asyncio.get_running_loop()

        def emit(event: dict) -> None:
            sys.stdout.write(f"LAMBCHAT_CUA:{token}:" + json.dumps(event) + "\n")
            sys.stdout.flush()

        _control = DesktopControl(emit)
        control = _control

        def read_commands() -> None:
            for raw in sys.stdin:
                try:
                    message = json.loads(raw)
                    if not isinstance(message, dict) or message.get("token") != token:
                        continue
                    loop.call_soon_threadsafe(control.command, message)
                except (ValueError, RuntimeError):
                    continue
            # Losing the shell must not leave a worker typing into the desktop.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(control.command, {"action": "pause"})

        threading.Thread(target=read_commands, daemon=True, name="desktop-control").start()
    return _control
