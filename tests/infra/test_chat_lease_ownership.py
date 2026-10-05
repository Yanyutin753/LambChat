"""Run lease Lua against an isolated local Redis, never the developer's data."""

import asyncio
import shutil
import subprocess

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.infra.channel.chat_lease import ChatLease, release_message


@pytest_asyncio.fixture
async def lease_redis(tmp_path, monkeypatch):
    binary = shutil.which("redis-server")
    if not binary:
        pytest.skip("redis-server is required for Lua lease integration tests")
    socket = str(tmp_path / "lease.sock")
    process = subprocess.Popen(
        [binary, "--port", "0", "--unixsocket", socket, "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = Redis(unix_socket_path=socket, decode_responses=True)
    try:
        for _ in range(100):
            try:
                await client.ping()
                break
            except RedisConnectionError:
                await asyncio.sleep(0.01)
        else:
            pytest.fail("isolated Redis did not start")
        monkeypatch.setattr("src.infra.channel.chat_lease.get_redis_client", lambda: client)
        yield client
    finally:
        await client.aclose()
        process.terminate()
        await asyncio.to_thread(process.wait, timeout=5)


async def test_lease_excludes_second_reader_and_only_current_owner_can_renew(lease_redis):
    first, second = ChatLease("reader", ttl=30), ChatLease("reader", ttl=30)
    assert await first.acquire()
    assert not await second.acquire()
    assert await first.renew()
    assert not await second.renew()
    await second.release()
    assert await lease_redis.get("reader") == first.owner
    await first.release()
    assert await second.acquire()
    assert not await first.renew()
    await first.release()
    assert await lease_redis.get("reader") == second.owner


async def test_stale_message_cleanup_cannot_delete_a_new_owners_claim(lease_redis):
    await lease_redis.set("message", "new-owner")
    await release_message(lease_redis, "message", "old-owner")
    assert await lease_redis.get("message") == "new-owner"
    await release_message(lease_redis, "message", "new-owner")
    assert await lease_redis.get("message") is None
