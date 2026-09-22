from __future__ import annotations

import asyncio

import pytest

from src.infra.tool import mcp_pool


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


@pytest.fixture(autouse=True)
async def _reset_pool_state() -> None:
    await mcp_pool.close_all_connections()
    mcp_pool._cleanup_counter = 0
    yield
    await mcp_pool.close_all_connections()
    mcp_pool._cleanup_counter = 0


@pytest.mark.asyncio
async def test_mcp_pool_eviction_closes_oldest_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_pool, "MAX_CONNECTIONS", 2)
    first = _FakeClient()
    second = _FakeClient()
    third = _FakeClient()

    await mcp_pool.add_pooled_connection("first", {"url": "1"}, first, [])
    await mcp_pool.add_pooled_connection("second", {"url": "2"}, second, [])
    await mcp_pool.add_pooled_connection("third", {"url": "3"}, third, [])

    stats = await mcp_pool.get_pool_stats()

    assert stats["total_connections"] == 2
    assert first.close_calls == 1
    assert second.close_calls == 0
    assert third.close_calls == 0


@pytest.mark.asyncio
async def test_mcp_pool_closes_discarded_duplicate_connection() -> None:
    existing = _FakeClient()
    duplicate = _FakeClient()

    await mcp_pool.add_pooled_connection("server", {"url": "1"}, existing, ["tool-1"])
    await mcp_pool.add_pooled_connection("server", {"url": "1"}, duplicate, ["tool-2"])

    pooled_client, tools = await mcp_pool.get_pooled_connection("server", {"url": "1"})

    assert pooled_client is existing
    assert tools == ["tool-1"]
    assert existing.close_calls == 0
    assert duplicate.close_calls == 1


@pytest.mark.asyncio
async def test_mcp_pool_close_client_awaits_future_returned_by_close() -> None:
    client = _FutureCloseClient()

    await mcp_pool._close_client(client)  # type: ignore[arg-type]

    assert client.close_future.done() is True


@pytest.mark.asyncio
async def test_mcp_pool_close_all_connections_closes_and_clears_pool() -> None:
    first = _FakeClient()
    second = _FakeClient()

    await mcp_pool.add_pooled_connection("first", {"url": "1"}, first, [])
    await mcp_pool.add_pooled_connection("second", {"url": "2"}, second, [])

    await mcp_pool.close_all_connections()

    assert first.close_calls == 1
    assert second.close_calls == 1
    assert (await mcp_pool.get_pool_stats())["total_connections"] == 0


@pytest.mark.asyncio
async def test_mcp_pool_offloads_server_hash_computation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    client = _FakeClient()
    config = {"url": "https://example.test", "headers": {"token": "secret"}}

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(mcp_pool, "run_long_blocking_io", fake_run_long_blocking_io)

    await mcp_pool.add_pooled_connection("server-1", config, client, ["tool-1"])
    pooled_client, tools = await mcp_pool.get_pooled_connection("server-1", config)

    assert pooled_client is client
    assert tools == ["tool-1"]
    assert calls == [mcp_pool._compute_server_hash, mcp_pool._compute_server_hash]
