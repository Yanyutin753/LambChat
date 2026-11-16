"""Regression contract for the isolated desktop worker (no interactive desktop needed)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import pytest


@pytest.fixture
def worker(tmp_path, monkeypatch):
    from lambchat_sandbox import cua_worker

    helper = tmp_path / "desktop_worker.py"
    helper.write_text(
        "import json, sys, time\n"
        "from pathlib import Path\n"
        "counter = 0\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    payload = request['payload']\n"
        "    if payload.get('started'):\n"
        "        Path(payload['started']).touch()\n"
        "    time.sleep(payload.get('delay', 0))\n"
        "    if payload.get('late_write'):\n"
        "        Path(payload['late_write']).touch()\n"
        "    counter += 1\n"
        "    print(json.dumps({'counter': counter}), flush=True)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cua_worker, "_worker_command", lambda: [sys.executable, str(helper)])
    return cua_worker.CuaWorker()


async def test_worker_reuses_process_between_observation_and_action(worker):
    try:
        assert await worker.call("cua_state", {}, timeout=5) == {"counter": 1}
        assert await worker.call("cua_click", {}, timeout=5) == {"counter": 2}
    finally:
        await worker.close()


async def test_driver_creates_its_own_private_state_directory(worker, monkeypatch):
    from lambchat_sandbox import cua_worker

    script = (
        "import os,json,sys; from pathlib import Path; sys.stdin.readline(); "
        "p=Path(os.environ['AGENT_DESKTOP_HOME']); "
        "print(json.dumps({'exists':p.exists(),'parent_exists':p.parent.is_dir()}),flush=True)"
    )
    monkeypatch.setattr(cua_worker, "_worker_command", lambda: [sys.executable, "-c", script])
    try:
        assert await worker.call("cua_state", {}, timeout=5) == {
            "exists": False,
            "parent_exists": True,
        }
    finally:
        await worker.close()


async def test_timeout_stops_late_input_and_restarts_with_empty_state(worker, tmp_path):
    late_write = tmp_path / "late-input"
    try:
        result = await worker.call(
            "cua_type", {"delay": 0.5, "late_write": str(late_write)}, timeout=0.1
        )
        assert result["error"] == "timeout"
        assert result["retry"] == "observe_first"
        assert await worker.call("cua_state", {}, timeout=5) == {"counter": 1}
        await asyncio.sleep(0.6)
        assert not late_write.exists()
    finally:
        await worker.close()


async def test_cancellation_reaps_worker_before_next_action(worker, tmp_path):
    started = tmp_path / "started"
    late_write = tmp_path / "late-input"
    task = asyncio.create_task(
        worker.call(
            "cua_type",
            {"delay": 1, "started": str(started), "late_write": str(late_write)},
            timeout=5,
        )
    )
    try:
        async with asyncio.timeout(5):
            while not started.exists():
                await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await worker.call("cua_state", {}, timeout=5) == {"counter": 1}
        await asyncio.sleep(1.1)
        assert not late_write.exists()
    finally:
        task.cancel()
        await worker.close()


async def test_worker_payload_round_trip_preserves_unicode_and_session(worker, monkeypatch):
    from lambchat_sandbox import cua_worker

    script = (
        "import sys,json; print(json.dumps(json.loads(sys.stdin.readline())['payload']),flush=True)"
    )
    monkeypatch.setattr(cua_worker, "_worker_command", lambda: [sys.executable, "-c", script])
    payload = {"session_id": "test-session", "text": "中文\n日本語 한국어", "target": {"index": 2}}
    try:
        result = await worker.call("cua_type", payload, timeout=5)
        assert json.dumps(result, ensure_ascii=False) == json.dumps(payload, ensure_ascii=False)
    finally:
        await worker.close()


async def test_timeout_reaps_detached_native_helper(tmp_path, monkeypatch):
    from lambchat_sandbox import cua_worker

    late = tmp_path / "late-helper-input"
    helper = (
        "import time;from pathlib import Path;time.sleep(0.6);Path(" + repr(str(late)) + ").touch()"
    )
    script = (
        "import sys,subprocess,time;sys.stdin.readline();"
        "subprocess.Popen([sys.executable,'-c'," + repr(helper) + "],start_new_session=True);"
        "time.sleep(10)"
    )
    monkeypatch.setattr(cua_worker, "_worker_command", lambda: [sys.executable, "-c", script])
    worker = cua_worker.CuaWorker()
    try:
        result = await worker.call("cua_click", {}, timeout=0.3)
        assert result["error"] == "timeout"
        await asyncio.sleep(0.8)
        assert not late.exists()
    finally:
        await worker.close()


async def test_windows_worker_is_suspended_until_job_assignment(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace

    from lambchat_sandbox import cua_worker

    events = []

    class Input:
        def write(self, data):
            events.append("write")

        async def drain(self):
            pass

    class Output:
        async def readline(self):
            return b'{"ok":true}\n'

    async def spawn(*args, **kwargs):
        events.append(("spawn", kwargs["creationflags"]))
        return SimpleNamespace(pid=10, stdin=Input(), stdout=Output())

    monkeypatch.setattr(
        cua_worker, "os", SimpleNamespace(name="nt", environ=os.environ, pathsep=os.pathsep)
    )
    monkeypatch.setattr(cua_worker.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(
        cua_worker.psutil,
        "Process",
        lambda pid: SimpleNamespace(resume=lambda: events.append("resume")),
    )
    worker = cua_worker.CuaWorker()
    monkeypatch.setattr(worker, "_attach_job", lambda pid: events.append("assign"))
    try:
        assert await worker.call("cua_state", {}, timeout=5) == {"ok": True}
        assert events == [("spawn", 4), "assign", "resume", "write"]
    finally:
        worker._process = None
        await worker.close()


async def test_job_close_reaps_worker_without_inspecting_terminated_process(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from lambchat_sandbox import cua_worker, executor

    worker = cua_worker.CuaWorker()
    process = SimpleNamespace(pid=123, wait=AsyncMock(return_value=0), kill=Mock())
    worker._process = process
    worker._job = 456
    state = Mock()
    state.name = str(tmp_path)
    worker._state = state
    close_handle = Mock()
    monkeypatch.setattr(executor, "_winapi", SimpleNamespace(close_handle=close_handle))
    inspect = Mock(side_effect=cua_worker.psutil.AccessDenied(123))
    monkeypatch.setattr(cua_worker.psutil, "Process", inspect)
    await worker.close()
    close_handle.assert_called_once_with(456)
    inspect.assert_not_called()
    process.wait.assert_awaited_once()
    state.cleanup.assert_called_once()
    assert worker._process is None and worker._job is None and worker._state is None


def test_failed_job_assignment_closes_handle_without_marking_worker_attached(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from lambchat_sandbox import cua_worker, executor

    api = SimpleNamespace(
        create_job_object=Mock(return_value=456),
        set_information_job_object=Mock(),
        open_process=Mock(return_value=789),
        assign_process_to_job_object=Mock(side_effect=OSError("assignment failed")),
        close_handle=Mock(),
    )
    monkeypatch.setattr(executor, "_winapi", api)
    worker = cua_worker.CuaWorker()
    with pytest.raises(OSError, match="assignment failed"):
        worker._attach_job(123)
    assert worker._job is None
    assert [call.args[0] for call in api.close_handle.call_args_list] == [789, 456]


async def test_local_takeover_kills_native_worker_before_acknowledging_pause(worker, tmp_path):
    from lambchat_sandbox.desktop_control import DesktopControl

    events = []
    control = DesktopControl(events.append)
    started, late = tmp_path / "started", tmp_path / "late"

    async def action():
        return await worker.call(
            "cua_type", {"delay": 1, "started": str(started), "late_write": str(late)}, timeout=5
        )

    task = asyncio.create_task(control.execute("cua_type", action))
    try:
        await asyncio.sleep(0)
        control.command({"action": "permit", "request": events[0]["request"], "allowed": True})
        async with asyncio.timeout(5):
            while not started.exists():
                await asyncio.sleep(0.01)
        control.command({"action": "pause"})
        assert (await task)["error"] == "desktop_control_paused"
        assert worker._process is None
        assert events[-1] == {"state": "paused"}
        await asyncio.sleep(1.1)
        assert not late.exists()
    finally:
        task.cancel()
        await worker.close()


async def test_close_ends_only_owned_driver_sessions_after_reaping_input(worker, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    from lambchat_sandbox import agent_desktop

    await worker.call("cua_state", {}, timeout=5)
    process = worker._process
    driver_home = Path(worker._state.name) / "driver"
    driver_home.mkdir()
    calls = []

    def run(args, **kwargs):
        assert process.returncode is not None
        assert driver_home.is_dir()
        assert kwargs["env"]["AGENT_DESKTOP_HOME"] == str(driver_home)
        calls.append(args[1:])
        data = (
            {"sessions": [{"session_id": "owned-session"}]}
            if args[1:] == ["session", "list"]
            else {}
        )
        return SimpleNamespace(stdout=json.dumps({"ok": True, "data": data}))

    monkeypatch.setattr(agent_desktop, "binary_path", lambda: Path(sys.executable))
    monkeypatch.setattr(subprocess, "run", run)
    await worker.close()
    assert calls == [["session", "list"], ["session", "end", "owned-session"]]
    assert not driver_home.exists()


def test_driver_cursor_cleanup_is_bounded_and_does_not_scan_other_homes(
    tmp_path, monkeypatch, caplog
):
    from types import SimpleNamespace

    from lambchat_sandbox import agent_desktop, cua_worker

    ticks = iter([0, 1, 4])
    calls = []
    monkeypatch.setattr(cua_worker.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(agent_desktop, "binary_path", lambda: tmp_path / "driver")

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] == 2
        assert kwargs["env"]["AGENT_DESKTOP_HOME"] == str(tmp_path)
        return SimpleNamespace(
            stdout=json.dumps({"ok": True, "data": {"sessions": [{"session_id": "owned"}]}})
        )

    monkeypatch.setattr(cua_worker.subprocess, "run", run)
    cua_worker._close_driver_sessions(tmp_path)
    assert len(calls) == 1
    assert "cleanup deadline exceeded" in caplog.text.lower()
