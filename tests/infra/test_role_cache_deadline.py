"""A slow optional cache must not hold up authoritative role lookups."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import ConnectionFailure

from src.infra.role import storage as role_module
from src.infra.role.storage import RoleStorage


@pytest.fixture
def lookup(monkeypatch):
    redis = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
    collection = SimpleNamespace(
        find_one=AsyncMock(
            return_value={"_id": "role-1", "name": "user", "permissions": ["chat:write"]}
        )
    )
    storage = RoleStorage()
    storage._collection = collection
    monkeypatch.setattr(role_module, "_get_redis", AsyncMock(return_value=redis))
    # raising=False lets RED exercise the old behavior, rather than fail at setup.
    monkeypatch.setattr(role_module, "_ROLE_CACHE_TIMEOUT_SECONDS", 0.01, raising=False)
    return storage, redis, collection


def hanging_operation():
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def hang(*_args, **_kwargs):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    return hang, entered, cancelled


@pytest.mark.parametrize("read_stage", ["version", "object"])
async def test_role_cache_read_deadline_returns_mongo_permissions_without_cache_write(
    lookup, read_stage
):
    storage, redis, collection = lookup
    hang, entered, cancelled = hanging_operation()

    async def read(key):
        if read_stage == "object" and key.startswith("role:obj_ver:"):
            return "7"
        return await hang()

    redis.get.side_effect = read
    role = await asyncio.wait_for(storage.get_by_name("user"), 0.3)

    assert role is not None and role.permissions == ["chat:write"]
    assert entered.is_set() and cancelled.is_set()
    assert redis.get.await_count == (1 if read_stage == "version" else 2)
    redis.set.assert_not_awaited()
    collection.find_one.assert_awaited_once_with({"name": "user"})


@pytest.mark.parametrize("write_stage", ["version", "set"])
async def test_role_cache_write_deadline_preserves_mongo_permissions(lookup, write_stage):
    storage, redis, collection = lookup
    hang, entered, cancelled = hanging_operation()
    calls = 0

    async def read(_key):
        nonlocal calls
        calls += 1
        if calls == 3 and write_stage == "version":
            return await hang()
        return None

    redis.get.side_effect = read
    if write_stage == "set":
        redis.set.side_effect = hang

    role = await asyncio.wait_for(storage.get_by_name("user"), 0.3)

    assert role is not None and role.permissions == ["chat:write"]
    assert entered.is_set() and cancelled.is_set()
    collection.find_one.assert_awaited_once()
    assert redis.set.await_count == (1 if write_stage == "set" else 0)


async def test_role_cache_read_failure_does_not_retry_cache_after_mongo(lookup):
    storage, redis, collection = lookup
    redis.get.side_effect = TimeoutError("cache unavailable")

    role = await storage.get_by_name("user")

    assert role is not None and role.permissions == ["chat:write"]
    redis.get.assert_awaited_once()
    redis.set.assert_not_awaited()
    collection.find_one.assert_awaited_once()


async def test_role_cache_failure_never_masks_mongo_authority_failure(lookup):
    storage, redis, collection = lookup
    redis.get.side_effect = TimeoutError("cache unavailable")
    failure = ConnectionFailure("authority unavailable")
    collection.find_one.side_effect = failure

    with pytest.raises(ConnectionFailure) as caught:
        await storage.get_by_name("user")

    assert caught.value is failure
    redis.set.assert_not_awaited()


@pytest.mark.parametrize("stage", ["read", "write"])
async def test_role_cache_external_cancellation_propagates_and_cleans_up(
    lookup, monkeypatch, stage
):
    storage, redis, collection = lookup
    monkeypatch.setattr(role_module, "_ROLE_CACHE_TIMEOUT_SECONDS", 10, raising=False)
    hang, entered, cancelled = hanging_operation()
    if stage == "read":
        redis.get.side_effect = hang
    else:
        redis.set.side_effect = hang
    task = asyncio.create_task(storage.get_by_name("user"))
    try:
        await asyncio.wait_for(entered.wait(), 0.3)
        task.cancel("external caller stopped")
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert caught.value.args == ("external caller stopped",)
        assert cancelled.is_set()
        assert collection.find_one.await_count == (0 if stage == "read" else 1)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("new_version, writes", [("7", 1), ("8", 0)])
async def test_role_cache_healthy_write_preserves_version_guard(lookup, new_version, writes):
    storage, redis, _collection = lookup
    redis.get.side_effect = ["7", None, new_version]

    role = await storage.get_by_name("user")

    assert role is not None and role.permissions == ["chat:write"]
    assert redis.set.await_count == writes
    if writes:
        assert redis.set.await_args.args[0] == "role:obj:user:v7"
