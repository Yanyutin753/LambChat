from __future__ import annotations

import json

import pytest

from src.infra.storage import redis as redis_storage


class _FakePool:
    closed = False

    async def aclose(self) -> None:
        self.closed = True


class _FakeConnectionPoolFactory:
    @staticmethod
    def from_url(*args, **kwargs):
        return _FakePool()


class _FakeAsyncRedisModule:
    ConnectionPool = _FakeConnectionPoolFactory


class _FakeRedisWithClosablePool:
    def __init__(self, *, connection_pool) -> None:
        self.connection_pool = connection_pool

    async def aclose(self) -> None:
        return None


class _FakeLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warning(self, message: str) -> None:
        self.messages.append(message)


class _FakeRedisClient:
    def __init__(self, *, connection_pool, **kwargs) -> None:
        self.connection_pool = connection_pool


class _FakeScanRedisClient:
    async def keys(self, pattern: str) -> list[str]:
        raise AssertionError(f"Redis KEYS must not be used for pattern {pattern}")

    async def scan(
        self,
        cursor: int | str = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        assert match == "task:*"
        assert count == 100
        if int(cursor) == 0:
            return 1, ["task:a", "task:b"]
        return 0, ["task:c"]


class _LargeFakeScanRedisClient:
    def __init__(self) -> None:
        self.calls = 0

    async def keys(self, pattern: str) -> list[str]:
        raise AssertionError(f"Redis KEYS must not be used for pattern {pattern}")

    async def scan(
        self,
        cursor: int | str = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        assert match == "task:*"
        assert count == 100
        self.calls += 1
        start = int(cursor) * 100
        batch = [f"task:{index}" for index in range(start, start + 100)]
        next_cursor = int(cursor) + 1
        if next_cursor >= 20:
            return 0, batch
        return next_cursor, batch


class _FakeSetRedisClient:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, object, int | None]] = []

    async def set(self, key: str, value: object, ex: int | None = None) -> None:
        self.set_calls.append((key, value, ex))


class _FakeGetRedisClient:
    async def get(self, key: str) -> str:
        assert key == "cache:large"
        return '{"items": ["' + ("x" * 20_000) + '"]}'


class _FakeXaddRedisClient:
    def __init__(self) -> None:
        self.xadd_calls: list[tuple[str, dict[str, str], int | None]] = []

    async def xadd(
        self,
        stream_key: str,
        fields: dict[str, str],
        maxlen: int | None = None,
    ) -> str:
        self.xadd_calls.append((stream_key, fields, maxlen))
        return "1-0"


class _FakeStreamReadRedisClient:
    async def xrange(
        self,
        stream_key: str,
        min: str = "-",
        max: str = "+",
        count: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        assert stream_key == "stream:events"
        assert min == "-"
        assert max == "+"
        assert count == 10
        return [("1-0", {"data": '{"content": "' + ("x" * 20_000) + '"}'})]

    async def xread(
        self,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        assert streams == {"stream:events": "0"}
        assert count == 10
        assert block == 100
        return [
            (
                "stream:events",
                [("1-0", {"data": '{"content": "' + ("x" * 20_000) + '"}'})],
            )
        ]


def test_get_redis_client_returns_distinct_clients_sharing_one_pool(
    monkeypatch,
) -> None:
    pool = _FakePool()
    fake_module = _FakeAsyncRedisModule()
    fake_module.ConnectionPool.from_url = lambda *args, **kwargs: pool

    monkeypatch.setattr(redis_storage, "redis", fake_module)
    monkeypatch.setattr(redis_storage, "Redis", _FakeRedisClient)
    redis_storage.get_redis_connection_pool.cache_clear()

    client_a = redis_storage.get_redis_client()
    client_b = redis_storage.get_redis_client()

    assert client_a is not client_b
    assert client_a.connection_pool is pool
    assert client_b.connection_pool is pool


def test_create_redis_client_can_use_an_isolated_pool(monkeypatch) -> None:
    pools: list[_FakePool] = []

    def _from_url(*args, **kwargs):
        pool = _FakePool()
        pools.append(pool)
        return pool

    fake_module = _FakeAsyncRedisModule()
    fake_module.ConnectionPool.from_url = _from_url

    monkeypatch.setattr(redis_storage, "redis", fake_module)
    monkeypatch.setattr(redis_storage, "Redis", _FakeRedisClient)
    redis_storage.get_redis_connection_pool.cache_clear()

    shared_client = redis_storage.create_redis_client()
    isolated_client = redis_storage.create_redis_client(isolated_pool=True)

    assert shared_client.connection_pool is redis_storage.get_redis_connection_pool()
    assert isolated_client.connection_pool is not shared_client.connection_pool
    assert isolated_client.connection_pool is pools[-1]


def test_create_redis_client_can_override_socket_timeout(monkeypatch) -> None:
    captured_kwargs: list[dict] = []

    def _from_url(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return _FakePool()

    fake_module = _FakeAsyncRedisModule()
    fake_module.ConnectionPool.from_url = _from_url

    monkeypatch.setattr(redis_storage, "redis", fake_module)
    monkeypatch.setattr(redis_storage, "Redis", _FakeRedisClient)
    redis_storage.get_redis_connection_pool.cache_clear()

    redis_storage.create_redis_client(isolated_pool=True, socket_timeout=None)

    assert captured_kwargs[-1]["socket_timeout"] is None


@pytest.mark.asyncio
async def test_close_redis_client_closes_shared_connection_pool(monkeypatch) -> None:
    pool = _FakePool()
    fake_module = _FakeAsyncRedisModule()
    fake_module.ConnectionPool.from_url = lambda *args, **kwargs: pool
    fake_logger = _FakeLogger()

    monkeypatch.setattr(redis_storage, "redis", fake_module)
    monkeypatch.setattr(redis_storage, "Redis", _FakeRedisWithClosablePool)
    monkeypatch.setattr(redis_storage, "logger", fake_logger)
    redis_storage.get_redis_connection_pool.cache_clear()
    redis_storage.get_redis_connection_pool()

    await redis_storage.close_redis_client()

    assert pool.closed is True
    assert redis_storage.get_redis_connection_pool.cache_info().currsize == 0


@pytest.mark.asyncio
async def test_close_redis_client_does_not_create_pool_when_unused(monkeypatch) -> None:
    created = 0
    fake_module = _FakeAsyncRedisModule()

    def _from_url(*args, **kwargs):
        nonlocal created
        created += 1
        return _FakePool()

    fake_module.ConnectionPool.from_url = _from_url
    monkeypatch.setattr(redis_storage, "redis", fake_module)
    redis_storage.get_redis_connection_pool.cache_clear()

    await redis_storage.close_redis_client()

    assert created == 0


@pytest.mark.asyncio
async def test_redis_storage_keys_uses_scan_instead_of_blocking_keys() -> None:
    storage = redis_storage.RedisStorage()
    storage._client = _FakeScanRedisClient()

    keys = await storage.keys("task:*")

    assert keys == ["task:a", "task:b", "task:c"]


@pytest.mark.asyncio
async def test_redis_storage_keys_limits_scan_results_by_default() -> None:
    storage = redis_storage.RedisStorage()
    client = _LargeFakeScanRedisClient()
    storage._client = client

    keys = await storage.keys("task:*")

    assert len(keys) == redis_storage.REDIS_STORAGE_KEYS_LIMIT
    assert keys[0] == "task:0"
    assert keys[-1] == f"task:{redis_storage.REDIS_STORAGE_KEYS_LIMIT - 1}"
    assert client.calls == redis_storage.REDIS_STORAGE_KEYS_LIMIT // 100


@pytest.mark.asyncio
async def test_redis_storage_set_serializes_json_inline_for_structured_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = redis_storage.RedisStorage()
    client = _FakeSetRedisClient()
    storage._client = client
    calls = []

    async def _fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(redis_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    await storage.set("cache:large", {"items": ["x" * 20_000]}, ttl=60)

    assert calls == []
    assert client.set_calls == [("cache:large", '{"items": ["' + ("x" * 20_000) + '"]}', 60)]


@pytest.mark.asyncio
async def test_redis_storage_get_parses_json_inline_for_structured_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = redis_storage.RedisStorage()
    storage._client = _FakeGetRedisClient()
    calls = []

    async def _fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(redis_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    value = await storage.get("cache:large")

    assert value == {"items": ["x" * 20_000]}
    assert calls == []


@pytest.mark.asyncio
async def test_redis_storage_xadd_serializes_json_inline_for_dict_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = redis_storage.RedisStorage()
    client = _FakeXaddRedisClient()
    storage._client = client
    calls = []

    async def _fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(redis_storage, "run_blocking_io", _fake_run_blocking_io)

    entry_id = await storage.xadd(
        "stream:events",
        {"event_type": "message", "data": {"content": "x" * 20_000}},
        maxlen=100,
    )

    assert entry_id == "1-0"
    assert calls == []
    assert client.xadd_calls == [
        (
            "stream:events",
            {"event_type": "message", "data": '{"content": "' + ("x" * 20_000) + '"}'},
            100,
        )
    ]


@pytest.mark.asyncio
async def test_redis_storage_xrange_offloads_stream_field_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = redis_storage.RedisStorage()
    storage._client = _FakeStreamReadRedisClient()
    calls = []

    async def _fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(redis_storage, "run_blocking_io", _fake_run_blocking_io)

    entries = await storage.xrange("stream:events", count=10)

    assert calls == ["_parse_stream_entries_sync"]
    assert entries == [("1-0", {"data": {"content": "x" * 20_000}})]


@pytest.mark.asyncio
async def test_redis_storage_xread_offloads_stream_field_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = redis_storage.RedisStorage()
    storage._client = _FakeStreamReadRedisClient()
    calls = []

    async def _fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(redis_storage, "run_blocking_io", _fake_run_blocking_io)

    entries = await storage.xread({"stream:events": "0"}, count=10, block=100)

    assert calls == ["_parse_stream_read_result_sync"]
    assert entries == [("stream:events", [("1-0", {"data": {"content": "x" * 20_000}})])]


class _FakeJsonRedisClient:
    """Redis client stub for get/set/xadd JSON round-trip checks."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.xadd_calls: list[tuple[str, dict]] = []

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value, ex=None):
        self.store[key] = value
        return True

    async def xadd(self, stream_key: str, fields: dict, maxlen=None):
        self.xadd_calls.append((stream_key, fields))
        return "1-0"


def _recording_run_blocking_io(calls: list[str]):
    async def _fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    return _fake_run_blocking_io


@pytest.mark.asyncio
async def test_redis_storage_get_parses_json_inline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = redis_storage.RedisStorage()
    client = _FakeJsonRedisClient()
    client.store["k"] = json.dumps({"a": 1})
    storage._client = client
    calls: list[str] = []
    monkeypatch.setattr(redis_storage, "run_blocking_io", _recording_run_blocking_io(calls))

    assert await storage.get("k") == {"a": 1}
    # json.loads is a microsecond pure-CPU call and must not hit the thread pool
    assert calls == []


@pytest.mark.asyncio
async def test_redis_storage_set_serializes_json_inline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = redis_storage.RedisStorage()
    client = _FakeJsonRedisClient()
    storage._client = client
    calls: list[str] = []
    monkeypatch.setattr(redis_storage, "run_blocking_io", _recording_run_blocking_io(calls))

    await storage.set("k", {"b": [1, 2]})
    assert json.loads(client.store["k"]) == {"b": [1, 2]}
    assert calls == []


@pytest.mark.asyncio
async def test_redis_storage_xadd_serializes_dict_fields_inline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = redis_storage.RedisStorage()
    client = _FakeJsonRedisClient()
    storage._client = client
    calls: list[str] = []
    monkeypatch.setattr(redis_storage, "run_blocking_io", _recording_run_blocking_io(calls))

    entry_id = await storage.xadd("stream:events", {"data": {"x": 1}, "n": 5})
    assert entry_id == "1-0"
    stream_key, fields = client.xadd_calls[0]
    assert stream_key == "stream:events"
    assert json.loads(fields["data"]) == {"x": 1}
    assert fields["n"] == "5"
    assert calls == []
