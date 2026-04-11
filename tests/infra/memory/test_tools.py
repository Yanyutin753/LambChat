import asyncio

import pytest


@pytest.mark.asyncio
async def test_auto_memory_capture_serializes_per_user(monkeypatch):
    from src.infra.memory import tools as memory_tools

    state = {"active": 0, "max_active": 0, "calls": 0}
    release = asyncio.Event()

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> None:
            state["calls"] += 1
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            if state["calls"] == 1:
                await release.wait()
            state["active"] -= 1

    async def fake_get_backend():
        return FakeBackend()

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)

    t1 = asyncio.create_task(memory_tools._auto_retain_user_memory("u1", "first"))
    await asyncio.sleep(0)
    t2 = asyncio.create_task(memory_tools._auto_retain_user_memory("u1", "second"))
    await asyncio.sleep(0.05)

    assert state["calls"] == 1
    assert state["max_active"] == 1

    release.set()
    await asyncio.gather(t1, t2)

    assert state["calls"] == 2
    assert state["max_active"] == 1


@pytest.mark.asyncio
async def test_auto_memory_capture_uses_distributed_lock(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> None:
            events.append(("retain", user_id))

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1"), ("retain", "u1"), ("release", "u1")]


@pytest.mark.asyncio
async def test_auto_memory_capture_skips_when_distributed_lock_not_acquired(monkeypatch):
    from src.infra.memory import tools as memory_tools

    events: list[tuple[str, str]] = []

    class FakeBackend:
        name = "native"

        async def auto_retain_from_text(self, user_id: str, user_input: str) -> None:
            events.append(("retain", user_id))

    async def fake_get_backend():
        return FakeBackend()

    async def fake_acquire(user_id: str, instance_id: str) -> str:
        events.append(("acquire", user_id))
        return "not_acquired"

    async def fake_release(user_id: str, instance_id: str) -> None:
        events.append(("release", user_id))

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    await memory_tools._auto_retain_user_memory("u1", "hello")

    assert events == [("acquire", "u1")]
