from __future__ import annotations

import asyncio

import pytest

from src.infra.tool import mcp_cache


class _FakeClient:
    def __init__(self) -> None:
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


class _FutureCloseClient:
    def __init__(self) -> None:
        self.close_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def close(self) -> asyncio.Future[None]:
        asyncio.get_running_loop().call_later(0.01, self.close_future.set_result, None)
        return self.close_future


class _PagedRedis:
    def __init__(self, key_count: int, page_size: int = 25) -> None:
        self.keys = [f"mcp_config_hash:user-{index:03d}" for index in range(key_count)]
        self.page_size = page_size
        self.scan_calls = 0
        self.deleted: list[str] = []

    async def scan(self, cursor: int = 0, match: str | None = None, count: int | None = None):
        assert match == "mcp_config_hash:*"
        del count
        self.scan_calls += 1
        start = int(cursor)
        end = min(start + self.page_size, len(self.keys))
        next_cursor = 0 if end >= len(self.keys) else end
        return next_cursor, self.keys[start:end]

    async def delete(self, *keys: str) -> int:
        self.deleted.extend(keys)
        return len(keys)


@pytest.fixture(autouse=True)
async def _reset_mcp_cache_state() -> None:
    await mcp_cache.invalidate_all_cache()
    mcp_cache._cache_locks.clear()
    yield
    await mcp_cache.invalidate_all_cache()
    mcp_cache._cache_locks.clear()


@pytest.mark.asyncio
async def test_cleanup_expired_cache_drains_scheduled_client_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient()
    mcp_cache._tools_cache["user-1"] = mcp_cache.CachedMCPEntry(
        tools=[],
        client=client,
        config_hash="hash",
    )
    monkeypatch.setattr(mcp_cache.settings, "MCP_USER_CACHE_TTL_SECONDS", 1, raising=False)
    mcp_cache._tools_cache["user-1"].created_at -= 2

    removed = mcp_cache._cleanup_expired_cache()
    await mcp_cache.drain_background_tasks()

    assert removed == 1
    assert client.close_calls == 1
    assert not mcp_cache._background_tasks


@pytest.mark.asyncio
async def test_close_client_awaits_future_returned_by_close() -> None:
    client = _FutureCloseClient()

    await mcp_cache._close_client(client)  # type: ignore[arg-type]

    assert client.close_future.done() is True


@pytest.mark.asyncio
async def test_drain_background_tasks_cancels_tasks_that_exceed_timeout() -> None:
    started = asyncio.Event()

    async def _never_finishes() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(_never_finishes())
    mcp_cache._track_background_task(task)
    await asyncio.wait_for(started.wait(), timeout=1)

    await mcp_cache.drain_background_tasks(timeout=0.01)

    assert task.cancelled() is True
    assert not mcp_cache._background_tasks


@pytest.mark.asyncio
async def test_invalidate_all_cache_limits_redis_hash_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_cache, "MCP_CONFIG_HASH_SCAN_LIMIT", 50, raising=False)
    fake_redis = _PagedRedis(key_count=125, page_size=25)
    monkeypatch.setattr(mcp_cache, "get_redis_client", lambda: fake_redis)

    count = await mcp_cache.invalidate_all_cache()

    assert count == 0
    assert len(fake_redis.deleted) == 50
    assert fake_redis.scan_calls == 2


@pytest.mark.asyncio
async def test_get_cache_stats_limits_redis_hash_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_cache, "MCP_CONFIG_HASH_SCAN_LIMIT", 50, raising=False)
    fake_redis = _PagedRedis(key_count=125, page_size=25)
    monkeypatch.setattr(mcp_cache, "get_redis_client", lambda: fake_redis)

    stats = await mcp_cache.get_cache_stats()

    assert stats["redis_hash_keys"] == 50
    assert fake_redis.scan_calls == 2


@pytest.mark.asyncio
async def test_get_cached_tools_offloads_config_hash_computation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    class _FakeRedis:
        async def get(self, _key: str):
            return None

        async def set(self, *_args, **_kwargs):
            return True

    async def create_client(_config):
        return ["tool-1"], _FakeClient()

    monkeypatch.setattr(mcp_cache, "get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(mcp_cache, "run_long_blocking_io", fake_run_long_blocking_io)

    tools, client = await mcp_cache.get_cached_tools(
        "user-1",
        {"mcpServers": {"alpha": {"command": "cmd"}}},
        create_client,
    )

    assert tools == ["tool-1"]
    assert client is not None
    assert calls == [mcp_cache.compute_config_hash]


@pytest.mark.asyncio
async def test_get_cached_tools_closes_replaced_cached_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_client = _FakeClient()
    new_client = _FakeClient()
    mcp_cache._tools_cache["user-1"] = mcp_cache.CachedMCPEntry(
        tools=["old-tool"],
        client=old_client,
        config_hash="old-hash",
    )

    class _FakeRedis:
        async def get(self, _key: str):
            return "old-hash"

        async def set(self, *_args, **_kwargs):
            return True

    async def create_client(_config):
        return ["new-tool"], new_client

    monkeypatch.setattr(mcp_cache, "get_redis_client", lambda: _FakeRedis())

    tools, client = await mcp_cache.get_cached_tools(
        "user-1",
        {"mcpServers": {"alpha": {"command": "new-cmd"}}},
        create_client,
    )

    assert tools == ["new-tool"]
    assert client is new_client
    assert old_client.close_calls == 1
    assert new_client.close_calls == 0
