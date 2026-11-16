"""Local shell takeover over inherited pipes; no network or Agent-callable resume."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
import threading
import uuid
from collections.abc import Callable, Coroutine
from typing import Any


class DesktopControl:
    def __init__(
        self,
        emit: Callable[[dict], None],
        *,
        timeout: float = 10,
        cleanup: Callable[[], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.emit = emit
        self.timeout = timeout
        self.cleanup = cleanup
        self.pausing: asyncio.Task[None] | None = None
        self.cleanup_failed = False
        self.paused = False
        self.needs_observation = False
        self.observed = False
        self.observed_apps = False
        self.pending: tuple[str, asyncio.Future[bool]] | None = None
        self.active: asyncio.Task[dict] | None = None
        self.owner: tuple[str, str] | None = None
        self.watcher: asyncio.Task[None] | None = None
        self.ended: str | None = None

    async def bind(self, session_id: str, run_id: str, client: Any) -> bool:
        owner = (session_id, run_id)
        if self.ended is not None and self.cleanup_failed:
            await self.finish(self.ended)
        if self.owner == owner:
            if self.ended is not None:
                return False
            if await client.control_active(*owner):
                return True
            await self.finish("completed")
            return False
        if self.owner is not None or not await client.control_active(*owner):
            return False
        self.owner = owner
        self.ended = None
        self.needs_observation = True
        self.observed_apps = False
        self.emit(
            {
                "state": "session",
                "session_id": session_id,
                "run_id": run_id,
                "paused": self.paused,
            }
        )

        async def watch() -> None:
            try:
                while self.owner == owner:
                    await asyncio.sleep(1)
                    if not await client.control_active(*owner):
                        await self.finish("completed")
                        return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Desktop control authority check failed (%s)", type(exc).__name__
                )
                # Idle transport loss is not user takeover; interrupted operations stay paused.
                if self.active is not None:
                    self.paused = True
                await self.finish("disconnected")

        self.watcher = asyncio.create_task(watch())
        return True

    async def finish(self, reason: str) -> None:
        if self.ended is not None and not self.cleanup_failed:
            return
        self.ended = reason
        self.cleanup_failed = False
        self.needs_observation = True
        self.observed = False
        self.observed_apps = False
        watcher, self.watcher = self.watcher, None
        if watcher and watcher is not asyncio.current_task():
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        if self.pending and not self.pending[1].done():
            self.pending[1].set_result(False)
        if self.active:
            if not self.active.cancelling():
                self.active.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.active
        if self.pausing is not None:
            await asyncio.shield(self.pausing)
        if self.cleanup is not None:
            try:
                await self.cleanup()
            except Exception:
                self.cleanup_failed = True
                self.paused = True
                self.emit({"state": "unavailable"})
                return
        self.cleanup_failed = False
        self.owner = None
        self.emit({"state": "ended", "reason": reason})

    async def _finish_pause(self, active: asyncio.Task[dict] | None) -> None:
        try:
            if active is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await active
            if self.cleanup is not None:
                await self.cleanup()
            self.cleanup_failed = False
        except Exception:
            self.cleanup_failed = True
        finally:
            self.pausing = None
            if self.ended is None:
                self.emit({"state": "unavailable" if self.cleanup_failed else "paused"})

    def command(self, message: dict) -> None:
        action = message.get("action")
        if action == "pause":
            self.paused = True
            self.needs_observation = True
            self.observed = False
            self.observed_apps = False
            if self.active and not self.active.cancelling():
                self.active.cancel()
            if self.pending and not self.pending[1].done():
                self.pending[1].set_result(False)
            if self.cleanup is not None:
                if self.pausing is None:
                    self.pausing = asyncio.create_task(self._finish_pause(self.active))
            elif not self.active:
                self.emit({"state": "paused"})
        elif action == "resume":
            # Do not allow resume to race the disposal of an in-flight input.
            if self.active or self.ended or self.pausing or self.cleanup_failed:
                return
            self.paused = False
            self.emit({"state": "idle"})
        elif action == "permit" and self.pending:
            request, future = self.pending
            if message.get("request") == request and not future.done():
                future.set_result(message.get("allowed") is True and not self.paused)

    async def execute(self, op: str, run: Callable[[], Coroutine[Any, Any, dict]]) -> dict:
        if self.ended:
            return self._not_started_result()
        if self.paused:
            return self._paused_result()
        if (
            self.needs_observation
            and not (op == "cua_launch" and self.observed_apps)
            and op
            not in {
                "cua_state",
                "cua_status",
                "cua_apps",
                "cua_windows",
                "cua_activate",
            }
        ):
            return {
                "error": "observation_required",
                "detail": "Observe target state before input; refresh apps before launching an application",
            }
        if op in {"cua_apps", "cua_launch"}:
            self.observed_apps = False
        request = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending = request, future
        try:
            self.emit({"state": "request", "request": request})
            if not await asyncio.wait_for(future, self.timeout) or self.paused or self.ended:
                if self.ended:
                    return self._not_started_result()
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
                self.observed_apps = False
            screenshot = result.get("screenshot") or {}
            focus_lost = (
                result.get("error") == "foreground_required"
                or screenshot.get("error") == "foreground_required"
            )
            if focus_lost and self.observed:
                self.command({"action": "pause"})
            if op == "cua_apps" and not result.get("error") and not self.paused:
                self.observed_apps = isinstance(result.get("apps"), list)
            if op == "cua_state" and not result.get("error") and not self.paused:
                self.needs_observation = False
                self.observed = True
            return result
        except TimeoutError:
            if self.active is not None:
                self.needs_observation = True
                self.observed_apps = False
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
            if self.ended and current is not None and not current.cancelling():
                return {"error": "desktop_control_ended", "disposition": "unknown"}
            if self.paused and current is not None and not current.cancelling():
                return self._paused_result()
            raise
        finally:
            # Channel cancellation must not leave a finished input blocking local resume.
            self.pending = None
            self.active = None
            if self.pausing is not None:
                await asyncio.shield(self.pausing)
            self.emit(
                {"state": "ended", "reason": self.ended}
                if self.ended
                else {
                    "state": "unavailable"
                    if self.cleanup_failed
                    else "paused"
                    if self.paused
                    else "idle"
                }
            )

    def _not_started_result(self) -> dict:
        if self.ended == "disconnected" and not self.paused and not self.cleanup_failed:
            return {
                "error": "desktop_control_disconnected",
                "disposition": "not_started",
                "retry": "observe_first",
                "detail": "Control authority connection was lost before the action started. "
                "Try one fresh observation to revalidate the same live run; do not replay input.",
            }
        return {
            "error": "desktop_control_ended",
            "detail": "Owning execution ended; no input started",
        }

    @staticmethod
    def _paused_result() -> dict:
        return {
            "error": "desktop_control_paused",
            "disposition": "unknown",
            "detail": "The user took control locally. Stop computer actions and wait for the user to resume. An interrupted action may have partially completed; do not replay it. Observe again after resuming.",
        }


_control: DesktopControl | None = None


def local_control(
    *,
    cleanup: Callable[[], Coroutine[Any, Any, None]] | None = None,
) -> DesktopControl | None:
    global _control
    token = os.environ.get("LAMBCHAT_DESKTOP_CONTROL")
    if not token:
        return None  # Standalone CLI daemon retains its existing non-shell contract.
    if _control is None:
        loop = asyncio.get_running_loop()

        def emit(event: dict) -> None:
            sys.stdout.write(f"LAMBCHAT_CUA:{token}:" + json.dumps(event) + "\n")
            sys.stdout.flush()

        _control = DesktopControl(emit, cleanup=cleanup)
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
    if cleanup is not None:
        _control.cleanup = cleanup
    return _control
