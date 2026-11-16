"""Real Windows UIA + packaged CUA smoke against an isolated WinForms fixture."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lambchat_sandbox import cua_worker

FORM = r"""
Add-Type -AssemblyName System.Windows.Forms
$form = New-Object System.Windows.Forms.Form
$form.Text = 'LambChat CUA Acceptance'
$form.TopMost = $true
$form.Width = 640
$form.Height = 320
$field = New-Object System.Windows.Forms.TextBox
$field.AccessibleName = 'Acceptance text'
$field.Location = New-Object System.Drawing.Point(20,40)
$field.Width = 540
$keys = New-Object 'System.Collections.Generic.List[string]'
$field.Add_KeyDown({
    param($sender, $event)
    $keys.Add([string]$event.KeyData)
    # Define the fixture shortcut explicitly across Windows PowerShell's WinForms versions.
    if ($event.Control -and $event.KeyCode -eq [System.Windows.Forms.Keys]::A) {
        $sender.SelectAll()
        $event.SuppressKeyPress = $true
        $event.Handled = $true
    }
})
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 100
$timer.Add_Tick({
    $command = Join-Path $env:LAMBCHAT_CUA_FIXTURE 'minimize'
    if (Test-Path $command) {
        Remove-Item $command
        $form.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
    }
    $state = @{ text = $field.Text; start = $field.SelectionStart; length = $field.SelectionLength; keys = @($keys.ToArray()); window_state = $form.WindowState.ToString() } | ConvertTo-Json
    [IO.File]::WriteAllText((Join-Path $env:LAMBCHAT_CUA_FIXTURE 'input.json'), $state)
})
$timer.Start()
$check = New-Object System.Windows.Forms.CheckBox
$check.Text = 'Enable option'
$check.Location = New-Object System.Drawing.Point(20,90)
$check.Width = 200
$button = New-Object System.Windows.Forms.Button
$button.Text = 'Save result'
$button.Location = New-Object System.Drawing.Point(20,140)
$button.Width = 150
$button.Add_Click({
    $result = @{ text = $field.Text; enabled = $check.Checked } | ConvertTo-Json
    [IO.File]::WriteAllText((Join-Path $env:LAMBCHAT_CUA_FIXTURE 'result.json'), $result)
})
$form.Controls.Add($field)
$form.Controls.Add($check)
$form.Controls.Add($button)
$form.Add_Shown({
    $form.Activate()
    [IO.File]::WriteAllText((Join-Path $env:LAMBCHAT_CUA_FIXTURE 'shown'), 'ready')
})
[System.Windows.Forms.Application]::Run($form)
"""


def wait_fixture_window(driver, pid: int) -> dict:
    from lambchat_sandbox.cua_ops import CuaOpError

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            windows = [w for w in driver.windows(pid) if w["title"] == "LambChat CUA Acceptance"]
        except CuaOpError as exc:
            if exc.code not in {"app_not_found", "window_not_found"}:
                raise
            windows = []
        if len(windows) == 1:
            return windows[0]
        assert not windows, "Own fixture has ambiguous windows"
        time.sleep(0.1)
    raise AssertionError("Own fixture did not become visible within five seconds")


def stage_fixture_foreground(pid: int) -> None:
    """Click only an independently verified point on our own visible fixture."""
    import ctypes
    from ctypes import wintypes

    from lambchat_sandbox.agent_desktop import AgentDesktopBackend, binary_path

    binary = binary_path()
    assert binary, "Pinned driver is needed to stage the isolated fixture"
    driver = AgentDesktopBackend(binary)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    try:
        window = wait_fixture_window(driver, pid)
        left, top, width, _ = window["bounds"]
        point = wintypes.POINT(round(left + width / 2), round(top + 12))
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(user32.WindowFromPoint(point), ctypes.byref(owner))
        assert owner.value == pid, "Fixture title bar is covered; no input sent"
        driver.click_point(point.x, point.y)
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(owner))
        assert owner.value == pid, "Desktop refused fixture foreground"
    finally:
        for session in driver.sessions.values():
            driver._run(["--session", session, "session", "end"])


def index_of(state: dict, title: str) -> int:
    matches = re.findall(r"\[(\d+)\][^\n]*? '" + re.escape(title) + r"'", state["state"])
    if len(matches) != 1:
        raise AssertionError(f"Expected one {title!r}: {state}")
    return int(matches[0])


async def verify(daemon: Path, directory: Path, report: dict) -> None:
    cua_worker._worker_command = lambda: [str(daemon), "--cua-worker"]
    worker = cua_worker.CuaWorker()
    with tempfile.TemporaryDirectory(prefix="lambchat-cua-fixture-") as temporary:
        root = Path(temporary)
        with (directory / "fixture.log").open("w", encoding="utf-8") as log:
            fixture = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", FORM],
                env={**os.environ, "LAMBCHAT_CUA_FIXTURE": str(root)},
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            base = {"pid": fixture.pid, "session_id": "native-cua-acceptance"}

            async def call(op: str, **payload) -> dict:
                started = time.monotonic()
                result = await worker.call(op, {**base, **payload}, timeout=20)
                report["operations"].append(
                    {
                        "op": op,
                        "seconds": time.monotonic() - started,
                        "result": {k: v for k, v in result.items() if k != "screenshot"},
                    }
                )
                if "error" in result:
                    raise AssertionError(result)
                return result

            async def saved(expected: dict) -> dict:
                async with asyncio.timeout(5):
                    while True:
                        try:
                            value = json.loads((root / "result.json").read_text(encoding="utf-8"))
                            if all(value.get(key) == wanted for key, wanted in expected.items()):
                                return value
                        except (FileNotFoundError, json.JSONDecodeError):
                            pass
                        await asyncio.sleep(0.05)

            try:
                async with asyncio.timeout(20):
                    while not (root / "shown").exists():
                        if fixture.poll() is not None:
                            raise AssertionError("Fixture exited; see fixture.log")
                        await asyncio.sleep(0.1)
                await asyncio.to_thread(stage_fixture_foreground, fixture.pid)
                state = await call("cua_state")
                assert state["window"]["title"] == "LambChat CUA Acceptance"
                await call("cua_activate", window_id=state["window"]["window_id"])
                window_id = state["window"]["window_id"]
                (root / "minimize").touch()
                async with asyncio.timeout(5):
                    while True:
                        try:
                            native = json.loads((root / "input.json").read_text(encoding="utf-8"))
                            if native["window_state"] == "Minimized":
                                break
                        except (FileNotFoundError, json.JSONDecodeError):
                            pass
                        await asyncio.sleep(0.05)
                minimized = await call("cua_state", window_id=window_id)
                assert minimized["window"]["minimized"] is True, minimized
                assert minimized["window"]["window_id"] == window_id
                assert "LambChat CUA Acceptance" in minimized["state"]
                report["minimized_observation"] = True
                await call("cua_activate", window_id=window_id)
                for expected in ("Windows 中文验收 ①", "Windows 中文验收 ②"):
                    state = await call("cua_state")
                    await call(
                        "cua_set_value",
                        target={"type": "element", "index": index_of(state, "Acceptance text")},
                        value=expected,
                    )
                    live = await call(
                        "cua_state",
                        target={"type": "element", "index": index_of(state, "Acceptance text")},
                    )
                    assert expected in live["state"], live
                    state = await call("cua_state")
                    await call(
                        "cua_click",
                        target={"type": "element", "index": index_of(state, "Save result")},
                    )
                    await saved({"text": expected})
                state = await call("cua_state")
                await call(
                    "cua_action",
                    target={"type": "element", "index": index_of(state, "Acceptance text")},
                    action="Focus",
                )
                await call("cua_key", text="ctrl+a")
                async with asyncio.timeout(3):
                    while True:
                        try:
                            selection = json.loads(
                                (root / "input.json").read_text(encoding="utf-8")
                            )
                            report["selection_after_ctrl_a"] = selection
                            if selection["start"] == 0 and selection["length"] == len(
                                selection["text"]
                            ):
                                assert "A, Control" in selection["keys"], selection
                                break
                        except (FileNotFoundError, json.JSONDecodeError):
                            pass
                        await asyncio.sleep(0.1)
                expected = "Windows 原生输入 😀 {ENTER}+^%"
                await call("cua_type", text=expected)
                state = await call("cua_state")
                assert expected in state["state"], state
                await call(
                    "cua_click",
                    target={"type": "element", "index": index_of(state, "Enable option")},
                )
                fresh = await call("cua_state")
                refused = await worker.call(
                    "cua_snapshot_action",
                    {
                        **base,
                        "operation": "click",
                        "snapshot_id": state["snapshot_id"],
                        "target": {"type": "element", "index": index_of(state, "Enable option")},
                    },
                    timeout=10,
                )
                assert refused.get("error") == "stale_state", refused
                await call(
                    "cua_click", target={"type": "element", "index": index_of(fresh, "Save result")}
                )
                await saved({"text": expected, "enabled": True})
                state = await call("cua_state", include_screenshot=True)
                screenshot = state.get("screenshot", {})
                assert screenshot.get("data_b64"), screenshot
                (directory / "window.jpg").write_bytes(
                    base64.b64decode(screenshot["data_b64"], validate=True)
                )
                report["oracle"] = json.loads((root / "result.json").read_text(encoding="utf-8"))
                report["success"] = True
            finally:
                try:
                    await worker.close()
                finally:
                    if fixture.poll() is None:
                        fixture.terminate()
                    fixture.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daemon", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This smoke requires a Windows desktop")
    directory = args.report_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    report: dict = {"success": False, "operations": []}
    try:
        asyncio.run(verify(args.daemon.resolve(strict=True), directory, report))
    except Exception as exc:
        report["success"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        (directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print("PACKAGED_WINDOWS_CUA_PASS" if report["success"] else "PACKAGED_WINDOWS_CUA_FAILED")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
