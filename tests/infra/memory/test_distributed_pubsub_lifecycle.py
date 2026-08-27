from __future__ import annotations

import pytest

from src.infra.memory import distributed
from src.infra.memory.distributed import close_memory_pubsub


class _FakeMemoryPubSub:
    def __init__(self) -> None:
        self.stop_calls = 0

    async def stop_listener(self) -> None:
        self.stop_calls += 1


@pytest.mark.asyncio
async def test_close_memory_pubsub_stops_and_releases_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pubsub = _FakeMemoryPubSub()
    monkeypatch.setattr(distributed, "_memory_pubsub", fake_pubsub)

    await close_memory_pubsub()

    assert fake_pubsub.stop_calls == 1
    assert distributed._memory_pubsub is None


@pytest.mark.asyncio
async def test_close_memory_pubsub_does_not_create_singleton_when_unused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(distributed, "_memory_pubsub", None)

    await close_memory_pubsub()

    assert distributed._memory_pubsub is None


class _FakeStartablePubSub:
    def __init__(self) -> None:
        self.start_calls = 0

    async def start_listener(self) -> None:
        self.start_calls += 1

    @property
    def is_running(self) -> bool:
        return self.start_calls > 0


@pytest.mark.asyncio
async def test_backend_reset_starts_pubsub_listener_when_memory_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.memory import tools as tools_module

    fake_pubsub = _FakeStartablePubSub()
    monkeypatch.setattr(tools_module.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(distributed, "get_memory_pubsub", lambda: fake_pubsub)
    monkeypatch.setattr(tools_module, "start_memory_compaction_agent", lambda: None)

    await tools_module._close_and_reset_backend()

    assert fake_pubsub.start_calls == 1


@pytest.mark.asyncio
async def test_backend_reset_skips_pubsub_when_memory_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.memory import tools as tools_module

    fake_pubsub = _FakeStartablePubSub()
    monkeypatch.setattr(tools_module.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(distributed, "get_memory_pubsub", lambda: fake_pubsub)

    await tools_module._close_and_reset_backend()

    assert fake_pubsub.start_calls == 0
