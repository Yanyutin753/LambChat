"""Native toolbar fixture: exercises the real pipe protocol without desktop input."""

import asyncio

from lambchat_sandbox.desktop_control import local_control


class FixtureAuthority:
    async def control_active(self, session_id, run_id):
        return True


async def main():
    control = local_control()
    assert control is not None
    authority = FixtureAuthority()
    generation = 0
    assert await control.bind("fixture", f"run-{generation}", authority)
    takeovers = 0

    async def observe():
        await asyncio.sleep(30)
        return {"state": "fixture; no desktop input"}

    for _ in range(120):
        if not control.paused:
            result = await control.execute("cua_state", observe)
            if result.get("error") not in (None, "desktop_control_paused"):
                raise RuntimeError(f"Native control readiness failed: {result['error']}")
            if result.get("error") == "desktop_control_paused":
                takeovers += 1
                if takeovers % 5 == 0:
                    await control.finish("completed")
                    generation += 1
                    assert await control.bind("fixture", f"run-{generation}", authority)
        await asyncio.sleep(0.25)


asyncio.run(main())
