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


async def test_weixin_poll_lock_lua_preserves_new_owner(lease_redis):
    from src.infra.channel.weixin.channel import (
        _acquire_poll_lock,
        _release_poll_lock,
        _renew_poll_lock,
    )

    key = "weixin:poll-lock:test-user:test-instance"
    assert await _acquire_poll_lock("test-user", "test-instance", "old", client=lease_redis)
    assert await _renew_poll_lock("test-user", "test-instance", "old", client=lease_redis)
    await lease_redis.set(key, "new", ex=150)
    assert not await _renew_poll_lock("test-user", "test-instance", "old", client=lease_redis)
    await _release_poll_lock("test-user", "test-instance", "old", client=lease_redis)
    assert await lease_redis.get(key) == "new"
    await _release_poll_lock("test-user", "test-instance", "new", client=lease_redis)
    assert await lease_redis.get(key) is None


async def test_weixin_reader_credentials_exclude_other_tenant_and_keep_other_bots_independent(
    lease_redis, monkeypatch
):
    from src.infra.channel.weixin.channel import WeixinChannel
    from src.kernel.schemas.weixin import WeixinConfig

    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: lease_redis)
    first = WeixinChannel(WeixinConfig(user_id="a", instance_id="one", bot_token="shared-token"))
    duplicate = WeixinChannel(
        WeixinConfig(user_id="b", instance_id="two", bot_token="shared-token")
    )
    distinct = WeixinChannel(
        WeixinConfig(user_id="c", instance_id="three", bot_token="other-token")
    )
    assert await first._acquire_reader("first")
    assert not await duplicate._acquire_reader("duplicate")
    assert await distinct._acquire_reader("distinct")
    assert first._inbox_worker.inbox.scope != duplicate._inbox_worker.inbox.scope
    assert first._context_key("chat") != duplicate._context_key("chat")
    assert first._reader_scope == duplicate._reader_scope
    assert first._reader_scope != distinct._reader_scope
    assert all("token" not in key for key in await lease_redis.keys("weixin:*"))
    await first._release_reader("first")
    assert await duplicate._acquire_reader("duplicate")


async def test_weixin_reader_waits_for_legacy_owner_during_rolling_upgrade(
    lease_redis, monkeypatch
):
    from src.infra.channel.weixin.channel import (
        WeixinChannel,
        _acquire_poll_lock,
        _lock_key,
        _release_poll_lock,
    )
    from src.kernel.schemas.weixin import WeixinConfig

    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: lease_redis)
    channel = WeixinChannel(WeixinConfig(user_id="a", instance_id="one", bot_token="shared-token"))
    assert await _acquire_poll_lock("a", "one", "old-version")
    assert not await channel._acquire_reader("new-version")
    assert not await lease_redis.exists(_lock_key(*channel._reader_scope))
    assert await lease_redis.get(_lock_key("a", "one")) == "old-version"
    await _release_poll_lock("a", "one", "old-version")
    assert await channel._acquire_reader("new-version")
    channel._lock_owner = "new-version"
    await channel._check_poll_owner()
    await lease_redis.set(_lock_key("a", "one"), "replacement", ex=30)
    with pytest.raises(RuntimeError, match="lease"):
        await channel._check_poll_owner()
    await channel._release_reader("new-version")
    assert await lease_redis.get(_lock_key("a", "one")) == "replacement"
