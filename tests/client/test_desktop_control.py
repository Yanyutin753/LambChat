import asyncio

import pytest

from lambchat_sandbox.desktop_control import DesktopControl


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
