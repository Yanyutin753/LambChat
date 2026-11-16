import asyncio

import pytest

from lambchat_sandbox.desktop_control import DesktopControl


async def test_ended_execution_cancels_input_before_releasing_surface():
    events = []
    control = DesktopControl(events.append)
    started = asyncio.Event()
    disposed = []

    async def action():
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            disposed.append(True)

    task = asyncio.create_task(control.execute("cua_type", action))
    await asyncio.sleep(0)
    control.command({"action": "permit", "request": events[0]["request"], "allowed": True})
    await started.wait()
    await control.finish("completed")
    assert (await task)["error"] == "desktop_control_ended"
    assert disposed
    assert events[-1] == {"state": "ended", "reason": "completed"}


async def test_concurrent_end_keeps_owner_until_input_cleanup_finishes():
    events = []
    control = DesktopControl(events.append)
    control.owner = ("session", "run")
    started = asyncio.Event()
    cleaning = asyncio.Event()
    release = asyncio.Event()

    async def action():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()

    operation = asyncio.create_task(control.execute("cua_type", action))
    await asyncio.sleep(0)
    control.command({"action": "permit", "request": events[0]["request"], "allowed": True})
    await started.wait()
    first = asyncio.create_task(control.finish("completed"))
    await cleaning.wait()
    try:
        await control.finish("disconnected")
        assert control.owner == ("session", "run")
        assert not any(event["state"] == "ended" for event in events)
    finally:
        release.set()
        await first
        await operation
    assert control.owner is None


async def test_thinking_keeps_control_until_exact_run_finishes():
    from unittest.mock import AsyncMock

    events = []
    control = DesktopControl(events.append)
    client = AsyncMock()
    client.control_active.return_value = True
    assert await control.bind("session", "run", client)
    await asyncio.sleep(0)
    assert not any(event.get("state") == "ended" for event in events)
    assert not await control.bind("other", "other-run", client)
    await control.finish("completed")
    assert control.owner is None
    assert control.watcher is None


@pytest.mark.parametrize("failure", [False, True])
async def test_owner_monitor_releases_on_terminal_or_connection_failure(failure, caplog):
    from unittest.mock import AsyncMock

    released = asyncio.Event()
    events = []

    def emit(event):
        events.append(event)
        if event["state"] == "ended":
            released.set()

    client = AsyncMock()
    client.control_active.side_effect = [True, OSError("private-pat-value") if failure else False]
    control = DesktopControl(emit)
    assert await control.bind("session", "run", client)
    await asyncio.wait_for(released.wait(), 3)
    assert control.owner is None
    assert control.watcher is None
    assert events[-1]["reason"] == ("disconnected" if failure else "completed")
    assert not control.paused
    if failure:
        assert "authority check failed (OSError)" in caplog.text
    assert "private-pat-value" not in caplog.text


@pytest.mark.parametrize("user_paused", [False, True])
async def test_idle_disconnect_rebind_preserves_user_takeover_without_inventing_it(user_paused):
    from unittest.mock import AsyncMock

    ended = asyncio.Event()
    events = []

    def emit(event):
        events.append(event)
        if event["state"] == "ended":
            ended.set()

    client = AsyncMock()
    client.control_active.side_effect = [True, OSError("offline"), True]
    control = DesktopControl(emit)
    assert await control.bind("session", "run", client)
    if user_paused:
        control.command({"action": "pause"})
    await asyncio.wait_for(ended.wait(), 3)
    assert events[-1] == {"state": "ended", "reason": "disconnected"}
    assert await control.bind("session", "run", client)
    try:
        assert control.paused is user_paused
        assert control.needs_observation
        action = AsyncMock(return_value={"ok": True})
        result = await control.execute("cua_type", action)
        assert result["error"] == (
            "desktop_control_paused" if user_paused else "observation_required"
        )
        action.assert_not_awaited()
    finally:
        await control.finish("completed")


async def test_disconnect_during_active_operation_keeps_pause_after_rebind():
    from unittest.mock import AsyncMock

    events = []
    ended = asyncio.Event()

    def emit(event):
        events.append(event)
        if event["state"] == "ended":
            ended.set()

    client = AsyncMock()
    client.control_active.side_effect = [True, OSError("offline"), True]
    control = DesktopControl(emit)
    assert await control.bind("session", "run", client)
    control.needs_observation = False
    operation = asyncio.create_task(control.execute("cua_type", asyncio.Event().wait))
    await asyncio.sleep(0)
    control.command({"action": "permit", "request": events[-1]["request"], "allowed": True})
    await asyncio.wait_for(ended.wait(), 3)
    assert (await operation)["error"] == "desktop_control_ended"
    assert await control.bind("session", "run", client)
    try:
        assert control.paused
    finally:
        await control.finish("completed")


async def test_local_takeover_survives_execution_end_and_new_execution():
    from unittest.mock import AsyncMock

    events = []
    control = DesktopControl(events.append)
    client = AsyncMock()
    client.control_active.return_value = True
    assert await control.bind("session", "run-1", client)
    control.command({"action": "pause"})
    await control.finish("completed")
    assert await control.bind("session", "run-2", client)
    assert control.paused
    assert events[-1] == {
        "state": "session",
        "session_id": "session",
        "run_id": "run-2",
        "paused": True,
    }
    await control.finish("completed")


async def test_no_input_before_visible_overlay_acknowledges():
    events = []
    control = DesktopControl(events.append)
    ran = []

    async def action():
        ran.append(True)
        return {"ok": True}

    task = asyncio.create_task(control.execute("cua_state", action))
    await asyncio.sleep(0)
    assert not ran
    control.command({"action": "permit", "request": "wrong", "allowed": True})
    await asyncio.sleep(0)
    assert not ran
    control.command({"action": "permit", "request": events[0]["request"], "allowed": True})
    assert await task == {"ok": True}


async def test_takeover_cancels_input_and_requires_fresh_observation():
    events = []
    control = DesktopControl(events.append)
    started = asyncio.Event()
    cancelled = []

    async def action():
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)

    task = asyncio.create_task(control.execute("cua_type", action))
    await asyncio.sleep(0)
    control.command({"action": "permit", "request": events[0]["request"], "allowed": True})
    await started.wait()
    control.command({"action": "pause"})
    assert (await task)["error"] == "desktop_control_paused"
    assert cancelled
    assert (await control.execute("cua_click", action))["error"] == "desktop_control_paused"
    control.command({"action": "resume"})
    assert (await control.execute("cua_click", action))["error"] == "observation_required"


async def test_missing_shell_fails_closed():
    control = DesktopControl(lambda event: None, timeout=0.01)

    async def action():
        pytest.fail("must not execute without the visible control")

    assert (await control.execute("cua_state", action))["error"] == "desktop_control_unavailable"


async def test_valid_accessibility_observation_survives_optional_screenshot_failure():
    events = []
    control = DesktopControl(events.append)
    control.needs_observation = True

    async def observe():
        return {"state": "[1] button Save", "screenshot": {"error": "screen_recording_denied"}}

    task = asyncio.create_task(control.execute("cua_state", observe))
    await asyncio.sleep(0)
    control.command({"action": "permit", "request": events[0]["request"], "allowed": True})
    await task
    assert not control.needs_observation
    assert control.observed


async def test_external_cancellation_is_not_misreported_as_takeover():
    control = DesktopControl(lambda event: None)

    async def action():
        return {}

    task = asyncio.create_task(control.execute("cua_state", action))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert control.pending is None


async def test_focus_conflict_pauses_following_actions():
    events = []
    control = DesktopControl(events.append)
    control.observed = True

    async def action():
        return {"screenshot": {"error": "foreground_required"}}

    task = asyncio.create_task(control.execute("cua_state", action))
    await asyncio.sleep(0)
    control.command({"action": "permit", "request": events[0]["request"], "allowed": True})
    await task
    assert control.paused
    assert (await control.execute("cua_activate", action))["error"] == "desktop_control_paused"


async def test_failed_overlay_creation_is_not_reported_as_user_takeover():
    events = []
    control = DesktopControl(events.append)

    async def action():
        pytest.fail("unavailable overlay must prevent input")

    task = asyncio.create_task(control.execute("cua_state", action))
    await asyncio.sleep(0)
    control.command({"action": "permit", "request": events[0]["request"], "allowed": False})
    assert (await task)["error"] == "desktop_control_unavailable"
    assert not control.paused


async def test_worker_loss_requires_new_observation_before_more_input():
    events = []
    control = DesktopControl(events.append)

    async def action():
        return {"error": "worker_failed", "retry": "observe_first"}

    task = asyncio.create_task(control.execute("cua_type", action))
    await asyncio.sleep(0)
    control.command({"action": "permit", "request": events[0]["request"], "allowed": True})
    assert (await task)["error"] == "worker_failed"
    assert (await control.execute("cua_type", action))["error"] == "observation_required"


async def test_terminal_run_cleans_idle_worker_before_releasing_control():
    events = []
    cleaning = asyncio.Event()
    release = asyncio.Event()

    async def cleanup():
        cleaning.set()
        await release.wait()

    control = DesktopControl(events.append, cleanup=cleanup)
    control.owner = ("session", "run")
    finishing = asyncio.create_task(control.finish("completed"))
    await cleaning.wait()
    try:
        assert control.owner == ("session", "run")
        assert not events
    finally:
        release.set()
        await finishing
    assert control.owner is None
    assert events == [{"state": "ended", "reason": "completed"}]


async def test_idle_takeover_cleans_cursor_before_ack_and_resume():
    events = []
    cleaning = asyncio.Event()
    release = asyncio.Event()

    async def cleanup():
        cleaning.set()
        await release.wait()

    control = DesktopControl(events.append, cleanup=cleanup)
    control.command({"action": "pause"})
    try:
        await asyncio.wait_for(cleaning.wait(), 0.2)
        control.command({"action": "resume"})
        assert control.paused
        assert not events
    finally:
        release.set()
        await control.finish("completed")


async def test_cleanup_failure_does_not_allow_resume():
    from unittest.mock import AsyncMock

    events = []
    control = DesktopControl(
        events.append, cleanup=AsyncMock(side_effect=OSError("cleanup failed"))
    )
    control.command({"action": "pause"})
    await asyncio.sleep(0)
    control.command({"action": "resume"})
    assert control.paused
    assert events[-1] == {"state": "unavailable"}


@pytest.mark.parametrize("failures", [1, 2])
async def test_failed_terminal_cleanup_can_recover_for_next_agent_without_auto_resume(failures):
    from unittest.mock import AsyncMock

    events = []
    cleanup = AsyncMock(side_effect=[OSError("worker still stopping")] * failures + [None, None])
    client = AsyncMock()
    client.control_active.return_value = True
    control = DesktopControl(events.append, cleanup=cleanup)
    assert await control.bind("first", "run-1", client)
    await control.finish("completed")
    assert control.owner == ("first", "run-1")
    assert control.cleanup_failed
    assert control.paused
    control.command({"action": "resume"})
    assert control.paused
    for _ in range(failures - 1):
        assert not await control.bind("second", "run-2", client)
        assert control.owner == ("first", "run-1")
        assert control.paused
    assert await control.bind("second", "run-2", client)
    try:
        assert control.owner == ("second", "run-2")
        assert not control.cleanup_failed
        assert control.paused
        assert events[-1]["state"] == "session"
        control.command({"action": "resume"})
        assert not control.paused
        assert control.needs_observation
    finally:
        await control.finish("completed")


@pytest.mark.parametrize("stop", ["pause", "end"])
async def test_takeover_after_permit_before_dispatch_never_starts_input(stop):
    events = []
    ran = []
    control = DesktopControl(events.append)

    async def action():
        ran.append(True)
        return {"ok": True}

    task = asyncio.create_task(control.execute("cua_click", action))
    await asyncio.sleep(0)
    control.command({"action": "permit", "request": events[0]["request"], "allowed": True})
    if stop == "pause":
        control.command({"action": "pause"})
    else:
        await control.finish("completed")
    result = await task
    assert not ran
    assert result["error"] == (
        "desktop_control_paused" if stop == "pause" else "desktop_control_ended"
    )
