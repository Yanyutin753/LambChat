from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from src.infra.tool import mcp_global


class _FakeHub:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[str, object]] = []
        self.unsubscribed: list[str] = []
        self.start_calls = 0
        self.stop_if_idle_calls = 0

    def subscribe(self, channel: str, handler) -> str:
        token = f"token-{len(self.subscriptions) + 1}"
        self.subscriptions.append((channel, handler))
        return token

    def unsubscribe(self, token: str) -> None:
        self.unsubscribed.append(token)

    async def start(self) -> None:
        self.start_calls += 1

    async def stop_if_idle(self) -> None:
        self.stop_if_idle_calls += 1


class _FakeRedisClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


class _FakeManager:
    def __init__(self) -> None:
        self.close_calls = 0
        self._initialized = True

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_mcp_cache_pubsub_subscribes_to_invalidation_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_hub = _FakeHub()
    monkeypatch.setattr("src.infra.tool.mcp_global.get_pubsub_hub", lambda: fake_hub)

    pubsub = mcp_global.MCPGlobalCachePubSub()
    await pubsub.start_listener()

    assert fake_hub.start_calls == 1
    assert fake_hub.subscriptions[0][0] == mcp_global.MCP_CACHE_INVALIDATE_CHANNEL

    await pubsub.stop_listener()
    assert fake_hub.unsubscribed == ["token-1"]


@pytest.mark.asyncio
async def test_close_mcp_cache_pubsub_stops_and_releases_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_hub = _FakeHub()
    monkeypatch.setattr("src.infra.tool.mcp_global.get_pubsub_hub", lambda: fake_hub)
    pubsub = mcp_global.get_mcp_cache_pubsub()
    await pubsub.start_listener()

    await mcp_global.close_mcp_cache_pubsub()

    assert mcp_global._mcp_cache_pubsub is None
    assert fake_hub.unsubscribed == ["token-1"]


@pytest.mark.asyncio
async def test_close_mcp_cache_pubsub_does_not_create_singleton_when_unused() -> None:
    mcp_global._mcp_cache_pubsub = None

    await mcp_global.close_mcp_cache_pubsub()

    assert mcp_global._mcp_cache_pubsub is None


@pytest.mark.asyncio
async def test_mcp_cache_pubsub_invalidates_foreign_user_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = _FakeManager()
    mcp_global._global_entries["user-1"] = mcp_global.GlobalMCPEntry(
        manager=fake_manager,
        tools=[],
    )

    pubsub = mcp_global.MCPGlobalCachePubSub()
    pubsub._instance_id = "instance-a"

    await pubsub._handle_message(
        {
            "data": json.dumps(
                {
                    "instance_id": "instance-b",
                    "scope": "user",
                    "user_id": "user-1",
                }
            )
        }
    )

    assert "user-1" not in mcp_global._global_entries
    assert fake_manager.close_calls == 1


@pytest.mark.asyncio
async def test_invalidate_global_cache_publishes_cross_instance_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr("src.infra.tool.mcp_global.get_redis_client", lambda: fake_redis)

    fake_manager = _FakeManager()
    mcp_global._global_entries["user-1"] = mcp_global.GlobalMCPEntry(
        manager=fake_manager,
        tools=[],
    )

    pubsub = mcp_global.MCPGlobalCachePubSub()
    pubsub._instance_id = "instance-a"
    monkeypatch.setattr(mcp_global, "get_mcp_cache_pubsub", lambda: pubsub)

    await mcp_global.invalidate_global_cache("user-1")

    assert fake_redis.published == [
        (
            mcp_global.MCP_CACHE_INVALIDATE_CHANNEL,
            json.dumps(
                {
                    "instance_id": "instance-a",
                    "scope": "user",
                    "user_id": "user-1",
                }
            ),
        )
    ]


@pytest.mark.asyncio
async def test_close_global_mcp_cache_closes_managers_without_publishing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr("src.infra.tool.mcp_global.get_redis_client", lambda: fake_redis)

    first_manager = _FakeManager()
    second_manager = _FakeManager()
    mcp_global._global_entries["user-1"] = mcp_global.GlobalMCPEntry(
        manager=first_manager,
        tools=[],
    )
    mcp_global._global_entries["user-2"] = mcp_global.GlobalMCPEntry(
        manager=second_manager,
        tools=[],
    )

    count = await mcp_global.close_global_mcp_cache()

    assert count == 2
    assert mcp_global._global_entries == {}
    assert first_manager.close_calls == 1
    assert second_manager.close_calls == 1
    assert fake_redis.published == []


@pytest.mark.asyncio
async def test_schedule_manager_close_accepts_future_returned_by_close() -> None:
    class _FutureCloseManager:
        def __init__(self) -> None:
            self.close_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        def close(self) -> asyncio.Future[None]:
            asyncio.get_running_loop().call_later(0.01, self.close_future.set_result, None)
            return self.close_future

    mcp_global._background_tasks.clear()
    manager = _FutureCloseManager()

    mcp_global._schedule_manager_close(manager)  # type: ignore[arg-type]
    await mcp_global.drain_background_tasks(timeout=1)

    assert manager.close_future.done() is True


def test_global_mcp_cache_uses_configured_max_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_global.settings, "MCP_GLOBAL_MAX_ENTRIES", 1, raising=False)

    first_manager = _FakeManager()
    second_manager = _FakeManager()
    mcp_global._global_entries["user-old"] = mcp_global.GlobalMCPEntry(
        manager=first_manager,
        tools=[],
    )
    mcp_global._global_entries["user-new"] = mcp_global.GlobalMCPEntry(
        manager=second_manager,
        tools=[],
    )
    mcp_global._global_entries["user-new"].touch()

    removed = mcp_global._cleanup_excess_entries()

    assert removed == 1
    assert "user-old" not in mcp_global._global_entries
    assert "user-new" in mcp_global._global_entries


@pytest.mark.asyncio
async def test_global_mcp_does_not_cache_all_failed_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import mcp_client

    class _FailedDiscoveryManager:
        def __init__(self, **_kwargs) -> None:
            self._initialized = False
            self.failed_servers = {"server-a": "[ConnectionError] no route"}

        async def initialize(self) -> None:
            self._initialized = True

        async def get_tools(self) -> list:
            return []

        def all_configured_servers_failed(self) -> bool:
            return True

    mark_calls: list[str] = []

    async def fake_acquire_distributed_lock(_lock_key: str):
        return True, "lock-value"

    async def fake_release_distributed_lock(_lock_key: str, _lock_value: str) -> None:
        return None

    async def fake_renew_lock_until_stopped(*_args) -> None:
        stop_event = _args[3]
        await stop_event.wait()

    async def fake_mark_init_done(user_id: str) -> None:
        mark_calls.append(user_id)

    mcp_global._global_entries.clear()
    mcp_global._local_locks.clear()
    monkeypatch.setattr(mcp_client, "MCPClientManager", _FailedDiscoveryManager)
    monkeypatch.setattr(mcp_global, "acquire_distributed_lock", fake_acquire_distributed_lock)
    monkeypatch.setattr(mcp_global, "release_distributed_lock", fake_release_distributed_lock)
    monkeypatch.setattr(mcp_global, "_renew_lock_until_stopped", fake_renew_lock_until_stopped)
    monkeypatch.setattr(mcp_global, "mark_init_done", fake_mark_init_done)

    tools, manager = await mcp_global.get_global_mcp_tools("user-1")

    assert tools == []
    assert isinstance(manager, _FailedDiscoveryManager)
    assert "user-1" not in mcp_global._global_entries
    assert mark_calls == []


def test_global_mcp_warmup_limit_setting_default() -> None:
    from src.kernel.config.base import Settings
    from src.kernel.config.definitions import SETTING_DEFINITIONS

    definition = SETTING_DEFINITIONS["MCP_GLOBAL_WARMUP_MAX_USERS"]

    assert Settings(_env_file=None).MCP_GLOBAL_WARMUP_MAX_USERS == 100
    assert definition["default"] == 100
    assert definition.get("frontend_visible", False) is False


def test_global_mcp_init_wait_setting_default() -> None:
    from src.kernel.config.base import Settings
    from src.kernel.config.definitions import SETTING_DEFINITIONS

    definition = SETTING_DEFINITIONS["MCP_GLOBAL_INIT_WAIT_SECONDS"]

    assert Settings(_env_file=None).MCP_GLOBAL_INIT_WAIT_SECONDS == 5
    assert definition["default"] == 5
    assert definition.get("frontend_visible", False) is False


def test_mcp_effective_config_server_limit_setting_default() -> None:
    from src.kernel.config.base import Settings
    from src.kernel.config.definitions import SETTING_DEFINITIONS

    definition = SETTING_DEFINITIONS["MCP_EFFECTIVE_CONFIG_MAX_SERVERS"]

    assert Settings(_env_file=None).MCP_EFFECTIVE_CONFIG_MAX_SERVERS == 100
    assert definition["default"] == 100
    assert definition.get("frontend_visible", False) is False


def test_mcp_effective_config_tool_limit_setting_default() -> None:
    from src.kernel.config.base import Settings
    from src.kernel.config.definitions import SETTING_DEFINITIONS

    definition = SETTING_DEFINITIONS["MCP_EFFECTIVE_CONFIG_MAX_TOOLS"]

    assert Settings(_env_file=None).MCP_EFFECTIVE_CONFIG_MAX_TOOLS == 200
    assert definition["default"] == 200
    assert definition.get("frontend_visible", False) is False


@pytest.mark.asyncio
async def test_global_mcp_warmup_uses_configured_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = 0
    max_active = 0
    release = asyncio.Event()
    started = asyncio.Event()

    async def _fake_get_tools(user_id: str):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            started.set()
        await release.wait()
        active -= 1
        return [], None

    monkeypatch.setattr(mcp_global, "get_global_mcp_tools", _fake_get_tools)
    monkeypatch.setattr(mcp_global.settings, "MCP_GLOBAL_WARMUP_CONCURRENCY", 2)

    task = asyncio.create_task(
        mcp_global.warmup_global_cache([f"user-{index}" for index in range(5)])
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    assert max_active == 2

    release.set()
    await task


@pytest.mark.asyncio
async def test_global_mcp_warmup_caps_direct_user_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warmed: list[str] = []

    async def _fake_get_tools(user_id: str):
        warmed.append(user_id)
        return [], None

    monkeypatch.setattr(mcp_global, "get_global_mcp_tools", _fake_get_tools)
    monkeypatch.setattr(mcp_global.settings, "MCP_GLOBAL_WARMUP_MAX_USERS", 2)
    monkeypatch.setattr(mcp_global.settings, "MCP_GLOBAL_WARMUP_CONCURRENCY", 10)

    await mcp_global.warmup_global_cache([f"user-{index}" for index in range(5)])

    assert warmed == ["user-0", "user-1"]


@pytest.mark.asyncio
async def test_warmup_active_users_iterates_cursor_without_unbounded_to_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warmed: list[str] = []

    class _FakeCursor:
        def __init__(self) -> None:
            self.docs = [{"_id": f"user-{index}"} for index in range(3)]

        def __aiter__(self):
            self._iter = iter(self.docs)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def to_list(self, length=None):
            raise AssertionError("warmup should not materialize an unbounded cursor")

    class _FakeCollection:
        def aggregate(self, pipeline):
            assert {"$limit": 0} not in pipeline
            return _FakeCursor()

    class _FakeClient:
        def __getitem__(self, _name):
            return {"users": _FakeCollection()}

    async def _fake_warmup_global_cache(user_ids: list[str]) -> None:
        warmed.extend(user_ids)

    monkeypatch.setattr(mcp_global, "get_mongo_client", lambda: _FakeClient(), raising=False)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: _FakeClient())
    monkeypatch.setattr(mcp_global, "warmup_global_cache", _fake_warmup_global_cache)

    await mcp_global.warmup_active_users_mcp(limit=0)

    assert warmed == ["user-0", "user-1", "user-2"]


@pytest.mark.asyncio
async def test_global_mcp_initialization_renews_distributed_lock_during_slow_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renew_started = asyncio.Event()
    allow_initialize = asyncio.Event()
    renew_calls: list[tuple[str, str, int]] = []

    class _SlowManager:
        def __init__(self, **_kwargs) -> None:
            self._initialized = False

        async def initialize(self) -> None:
            await renew_started.wait()
            self._initialized = True
            allow_initialize.set()

        async def get_tools(self) -> list:
            return []

        async def close(self) -> None:
            return None

    async def _fake_acquire(lock_key: str, ttl: int = mcp_global.DISTRIBUTED_LOCK_TTL):
        return True, "lock-value"

    async def _fake_renew(lock_key: str, lock_value: str, ttl: int) -> bool:
        renew_calls.append((lock_key, lock_value, ttl))
        renew_started.set()
        return True

    async def _fake_release(_lock_key: str, _lock_value: str) -> bool:
        return True

    monkeypatch.setattr(mcp_global, "acquire_distributed_lock", _fake_acquire)
    monkeypatch.setattr(mcp_global, "renew_distributed_lock", _fake_renew)
    monkeypatch.setattr(mcp_global, "release_distributed_lock", _fake_release)
    monkeypatch.setattr(mcp_global, "_get_lock_renew_interval", lambda _ttl: 0.01)
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.infra.tool.mcp_client",
        SimpleNamespace(MCPClientManager=_SlowManager),
    )

    tools, manager = await mcp_global.get_global_mcp_tools("user-1")

    assert tools == []
    assert manager is not None
    assert allow_initialize.is_set()
    assert renew_calls
    assert all(
        call == ("mcp_init_lock:user-1", "lock-value", mcp_global.DISTRIBUTED_LOCK_TTL)
        for call in renew_calls
    )


@pytest.mark.asyncio
async def test_global_mcp_lock_wait_uses_configured_attempt_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[float] = []
    check_calls = 0

    class _FastManager:
        def __init__(self, **_kwargs) -> None:
            self._initialized = False

        async def initialize(self) -> None:
            self._initialized = True

        async def get_tools(self) -> list:
            return []

        async def close(self) -> None:
            return None

    async def _fake_acquire(lock_key: str, ttl: int = mcp_global.DISTRIBUTED_LOCK_TTL):
        return False, ""

    async def _fake_check_done(user_id: str) -> bool:
        nonlocal check_calls
        check_calls += 1
        return False

    async def _fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    async def _fake_mark_done(_user_id: str) -> None:
        return None

    monkeypatch.setattr(mcp_global, "acquire_distributed_lock", _fake_acquire)
    monkeypatch.setattr(mcp_global, "check_init_done", _fake_check_done)
    monkeypatch.setattr(mcp_global, "mark_init_done", _fake_mark_done)
    monkeypatch.setattr(mcp_global.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(
        mcp_global,
        "settings",
        SimpleNamespace(
            MCP_GLOBAL_INIT_WAIT_SECONDS=2,
            MCP_GLOBAL_CACHE_TTL_SECONDS=900,
            MCP_GLOBAL_MAX_ENTRIES=100,
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.infra.tool.mcp_client",
        SimpleNamespace(MCPClientManager=_FastManager),
    )

    tools, manager = await mcp_global.get_global_mcp_tools("user-1")

    assert tools == []
    assert manager is not None
    assert check_calls == 2
    assert sleep_calls == [1.0, 1.0]


@pytest.fixture(autouse=True)
def _reset_mcp_global_state() -> None:
    mcp_global._global_entries.clear()
    mcp_global._local_locks.clear()
