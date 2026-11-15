"""Native toolbar fixture: exercises the real pipe protocol without desktop input."""

import asyncio

from lambchat_sandbox.desktop_control import local_control


async def main():
    control = local_control()
    assert control is not None

    async def observe():
        await asyncio.sleep(30)
        return {"state": "fixture; no desktop input"}

    for _ in range(120):
        if not control.paused:
            result = await control.execute("cua_state", observe)
            if result.get("error") not in (None, "desktop_control_paused"):
                raise RuntimeError(f"Native control readiness failed: {result['error']}")
        await asyncio.sleep(0.25)


asyncio.run(main())
