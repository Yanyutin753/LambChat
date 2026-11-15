"""Android launcher: private stdin pairing, otherwise the existing daemon protocol."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

from lambchat_sandbox.audit import Auditor
from lambchat_sandbox.config import SandboxConfig, server_origin


def parse_pairing(raw: dict) -> tuple[SandboxConfig, str]:
    server_origin(raw["serverUrl"])
    policy = raw.get("confirmPolicy", "all")
    machine = raw.get("machineId", "")
    token = raw.get("pat", "")
    if policy not in {"all", "commands", "none"}:
        raise ValueError("Invalid confirmation policy")
    if not re.fullmatch(r"[a-f0-9]{12}", machine):
        raise ValueError("Invalid device identity")
    if not token or any(not 33 <= ord(c) <= 126 for c in token):
        raise ValueError("Invalid pairing token")
    return SandboxConfig(
        server_url=raw["serverUrl"],
        data_root=Path("/lambchat/workspaces"),
        embedded_python=False,
        confirm_policy=policy,
        machine_id=machine,
        machine_name=str(raw.get("machineName", "Android"))[:64],
    ), token


def emit_activity(event: dict) -> None:
    print("LAMBCHAT_DEVICE_STATE " + json.dumps(event), flush=True)


class ActivityAuditor(Auditor):
    """The floating window receives counts/status only, never commands or file content."""

    def __init__(self, root: Path, emit: Callable[[dict], None] = emit_activity) -> None:
        super().__init__(root)
        self._active: set[str] = set()
        self._emit = emit
        self._failed = False

    def connection(self, state: str) -> None:
        self._active.clear()
        self._failed = False
        with contextlib.suppress(Exception):
            self._emit({"state": state, "active": 0})

    def log(self, session_id: str, event: dict) -> None:
        super().log(session_id, event)
        kind, call_id = event.get("event"), event.get("call_id")
        if not isinstance(call_id, str):
            return
        if kind == "allowed":
            if not self._active:
                self._failed = False
            self._active.add(call_id)
        elif kind in {"executed", "expired", "result_rejected"} and call_id in self._active:
            self._active.remove(call_id)
            self._failed |= kind != "executed" or event.get("status") != "ok"
        else:
            return
        state = "executing" if self._active else "failed" if self._failed else "completed"
        with contextlib.suppress(Exception):
            self._emit({"state": state, "active": len(self._active)})


def main() -> None:
    os.environ["LAMBCHAT_ANDROID"] = "1"
    os.environ["LAMBCHAT_HOME"] = "/lambchat"
    from lambchat_sandbox.daemon import run_daemon

    # The PAT never appears in argv, environment, runtime archives or logs.
    cfg, token = parse_pairing(json.loads(sys.stdin.buffer.readline(16385)))
    from lambchat_sandbox.transport import ChannelClient

    audit = ActivityAuditor(Path("/lambchat/audit"))

    class AndroidChannel(ChannelClient):
        async def connect(self):
            audit.connection("connecting")
            result = await super().connect()
            audit.connection("idle")
            return result

        async def close(self) -> None:
            try:
                await super().close()
            finally:
                audit.connection("offline")

    try:
        asyncio.run(
            run_daemon(
                cfg,
                pat=token,
                auditor=audit,
                client_factory=lambda: AndroidChannel(
                    cfg.server_url,
                    token,
                    confirm_policy=cfg.confirm_policy,
                    machine_id=cfg.machine_id,
                    machine_name=cfg.machine_name,
                ),
            )
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    main()
