from __future__ import annotations

import asyncio

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver

import src.infra.storage.checkpoint as checkpoint_mod

_ORIGINAL_GET_PG_CHECKPOINTER = checkpoint_mod.get_pg_checkpointer


@pytest.fixture(autouse=True)
def _reset_memory_saver_state(monkeypatch: pytest.MonkeyPatch) -> None:
    checkpoint_mod._mongo_checkpointer = None
    checkpoint_mod._pg_checkpointer = None
    checkpoint_mod._pg_checkpointer_pool = None
    if hasattr(checkpoint_mod, "_pg_checkpointer_lock"):
        checkpoint_mod._pg_checkpointer_lock = None

    if hasattr(checkpoint_mod.get_async_checkpointer, "_memory_saver"):
        delattr(checkpoint_mod.get_async_checkpointer, "_memory_saver")
    if hasattr(checkpoint_mod.get_async_checkpointer, "_memory_saver_cache"):
        delattr(checkpoint_mod.get_async_checkpointer, "_memory_saver_cache")

    monkeypatch.setattr(
        checkpoint_mod,
        "get_mongo_checkpointer",
        lambda collection_name="checkpoints": None,
    )

    async def _fake_pg_checkpointer():
        return None

    monkeypatch.setattr(checkpoint_mod, "get_pg_checkpointer", _fake_pg_checkpointer)
    monkeypatch.setattr(checkpoint_mod, "_MEMORY_SAVER_MAX_THREADS", 3, raising=False)
    monkeypatch.setattr(checkpoint_mod, "_MEMORY_SAVER_TTL_SECONDS", 3600, raising=False)
    monkeypatch.setattr(checkpoint_mod, "_MEMORY_SAVER_CLEANUP_INTERVAL", 1, raising=False)


@pytest.mark.asyncio
async def test_memory_saver_fallback_reuses_same_thread_cache() -> None:
    saver1 = await checkpoint_mod.get_async_checkpointer(thread_id="session-1")
    saver2 = await checkpoint_mod.get_async_checkpointer(thread_id="session-1")

    assert saver1 is saver2


@pytest.mark.asyncio
async def test_memory_saver_fallback_bounds_cached_threads() -> None:
    for i in range(5):
        await checkpoint_mod.get_async_checkpointer(thread_id=f"session-{i}")

    cache = getattr(checkpoint_mod.get_async_checkpointer, "_memory_saver_cache")

    assert len(cache) == 3
    assert "session-0" not in cache
    assert "session-1" not in cache


@pytest.mark.asyncio
async def test_checkpointer_diagnostics_reports_memory_saver_cache() -> None:
    await checkpoint_mod.get_async_checkpointer(thread_id="session-1")

    diagnostics = checkpoint_mod.get_checkpointer_diagnostics()

    assert diagnostics["configured_backend"] == "mongodb"
    assert diagnostics["memory_saver_cache_active"] is True
    assert diagnostics["memory_saver_cache_size"] == 1
    assert diagnostics["mongo_checkpointer_active"] is False
    assert diagnostics["postgres_checkpointer_active"] is False


@pytest.mark.asyncio
async def test_mongo_checkpointer_accepts_string_channel_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeMongoSaver(BaseCheckpointSaver):
        pass

    saver = _FakeMongoSaver()

    monkeypatch.setattr(checkpoint_mod.settings, "CHECKPOINT_BACKEND", "mongodb")
    monkeypatch.setattr(
        checkpoint_mod,
        "get_mongo_checkpointer",
        lambda collection_name="checkpoints": saver,
    )

    checkpointer = await checkpoint_mod.get_async_checkpointer(thread_id="session-1")

    assert checkpointer is saver
    next_version = checkpointer.get_next_version("00000000000000000000000000000001.1234", None)
    assert isinstance(next_version, str)
    assert next_version > "00000000000000000000000000000001.1234"


@pytest.mark.asyncio
async def test_pg_checkpointer_initializes_once_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        checkpoint_mod,
        "get_pg_checkpointer",
        _ORIGINAL_GET_PG_CHECKPOINTER,
    )

    open_count = 0
    close_count = 0
    saver_inputs = []

    class _FakePool:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        async def open(self, wait: bool = False) -> None:
            nonlocal open_count
            open_count += 1
            await asyncio.sleep(0.01)

        async def close(self) -> None:
            nonlocal close_count
            close_count += 1

    class _FakeSaver:
        def __init__(self, conn) -> None:
            saver_inputs.append(conn)

        async def setup(self) -> None:
            await asyncio.sleep(0)

    monkeypatch.setattr(checkpoint_mod.settings, "CHECKPOINT_PG_POOL_MIN_SIZE", 1)
    monkeypatch.setattr(checkpoint_mod.settings, "CHECKPOINT_PG_POOL_MAX_SIZE", 3)
    monkeypatch.setattr(
        "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver",
        _FakeSaver,
    )
    monkeypatch.setattr("psycopg_pool.AsyncConnectionPool", _FakePool)

    savers = await asyncio.gather(*(checkpoint_mod.get_pg_checkpointer() for _ in range(5)))

    assert savers == [savers[0]] * 5
    assert open_count == 1
    assert close_count == 0
    assert len(saver_inputs) == 1
    assert isinstance(saver_inputs[0], _FakePool)
    assert saver_inputs[0].kwargs["min_size"] == 1
    assert saver_inputs[0].kwargs["max_size"] == 3
