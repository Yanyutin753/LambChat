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
            await control.execute("cua_state", observe)
        await asyncio.sleep(0.25)


asyncio.run(main())
