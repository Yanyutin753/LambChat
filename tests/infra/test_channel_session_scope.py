"""Channel sessions must be isolated across owners and bot instances."""

import asyncio
import time

import pytest

from src.infra.channel.feishu.handler_helpers import (
    _create_new_feishu_session,
    _get_feishu_session_id,
)
from src.infra.channel.weixin.handler import (
    _create_new_weixin_session,
    _get_weixin_session_id,
)


@pytest.fixture(
    params=[
        (_get_feishu_session_id, _create_new_feishu_session),
        (_get_weixin_session_id, _create_new_weixin_session),
    ]
)
def session_helpers(request):
    return request.param


@pytest.fixture
def storage(monkeypatch):
    class Storage:
        def __init__(self):
            self.values = {}
            self.read_started = None
            self.finish_read = None

        async def get(self, key):
            value = self.values.get(key)
            if self.read_started is not None:
                self.read_started.set()
                await self.finish_read.wait()
            return value

        async def set(self, key, value):
            self.values[key] = value

    result = Storage()
    monkeypatch.setattr("src.infra.storage.redis.RedisStorage", lambda: result)
    return result


async def test_default_sessions_are_isolated_by_owner_and_instance(session_helpers, storage):
    resolve, create = session_helpers
    scopes = [("alice", "bot-a"), ("bob", "bot-a"), ("alice", "bot-b")]
    defaults = [await resolve("same-chat", user_id=u, instance_id=i) for u, i in scopes]
    assert len(set(defaults)) == 3
    new_session = await create("same-chat", user_id="alice", instance_id="bot-a")
    assert await resolve("same-chat", user_id="alice", instance_id="bot-a") == new_session
    for (user, instance), original in zip(scopes[1:], defaults[1:], strict=True):
        assert await resolve("same-chat", user_id=user, instance_id=instance) == original


async def test_new_sessions_are_unique_in_same_second(session_helpers, storage, monkeypatch):
    _, create = session_helpers
    monkeypatch.setattr(time, "time", lambda: 1234567890)
    first = await create("chat", user_id="alice", instance_id="bot")
    second = await create("chat", user_id="alice", instance_id="bot")
    assert first != second


async def test_default_lookup_never_overwrites_concurrent_new_session(session_helpers, storage):
    resolve, create = session_helpers
    storage.read_started = asyncio.Event()
    storage.finish_read = asyncio.Event()
    pending = asyncio.create_task(resolve("chat", user_id="alice", instance_id="bot"))
    await asyncio.wait_for(storage.read_started.wait(), timeout=1)
    new_session = await create("chat", user_id="alice", instance_id="bot")
    storage.finish_read.set()
    await pending
    assert await resolve("chat", user_id="alice", instance_id="bot") == new_session


async def test_scope_identity_cannot_collide_via_delimiters(session_helpers, storage):
    resolve, _ = session_helpers
    first = await resolve("chat", user_id="a:b", instance_id="c")
    second = await resolve("chat", user_id="a", instance_id="b:c")
    assert first != second
