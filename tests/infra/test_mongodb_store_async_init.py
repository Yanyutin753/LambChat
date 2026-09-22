import asyncio
from types import SimpleNamespace

import pytest
from langgraph.store.base import GetOp, ListNamespacesOp, SearchOp

from src.infra.storage import mongodb_store as store_module


@pytest.fixture(autouse=True)
def reset_store_singleton() -> None:
    store_module._store_instance = None
    store_module._store_initialized = False
    yield
    store_module._store_instance = None
    store_module._store_initialized = False


@pytest.mark.asyncio
async def test_acreate_store_uses_async_setup_for_mongodb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"setup": 0, "asetup": 0}

    monkeypatch.setattr(store_module.settings, "ENABLE_POSTGRES_STORAGE", False)

    def fake_setup(self) -> None:
        calls["setup"] += 1

    async def fake_asetup(self) -> None:
        calls["asetup"] += 1

    monkeypatch.setattr(store_module.MongoDBStore, "setup", fake_setup)
    monkeypatch.setattr(store_module.MongoDBStore, "asetup", fake_asetup)

    store = await store_module.acreate_store()

    assert isinstance(store, store_module.MongoDBStore)
    assert calls == {"setup": 0, "asetup": 1}


@pytest.mark.asyncio
async def test_acreate_store_initializes_singleton_once_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store_module.settings, "ENABLE_POSTGRES_STORAGE", False)

    created = 0

    async def fake_acreate_mongodb_store():
        nonlocal created
        created += 1
        await asyncio.sleep(0)
        return object()

    monkeypatch.setattr(store_module, "acreate_mongodb_store", fake_acreate_mongodb_store)

    first, second = await asyncio.gather(
        store_module.acreate_store(),
        store_module.acreate_store(),
    )

    assert created == 1
    assert first is second


@pytest.mark.asyncio
async def test_close_store_releases_singleton_and_calls_backend_close() -> None:
    class _ClosableStore:
        def __init__(self) -> None:
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    store = _ClosableStore()
    store_module._store_instance = store
    store_module._store_initialized = True

    await store_module.close_store()

    assert store.close_calls == 1
    assert store_module._store_instance is None
    assert store_module._store_initialized is False


@pytest.mark.asyncio
async def test_close_store_awaits_future_returned_by_backend_close() -> None:
    class _FutureClosableStore:
        def __init__(self) -> None:
            self.close_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        def close(self) -> asyncio.Future[None]:
            asyncio.get_running_loop().call_later(0.01, self.close_future.set_result, None)
            return self.close_future

    store = _FutureClosableStore()
    store_module._store_instance = store
    store_module._store_initialized = True

    await store_module.close_store()

    assert store.close_future.done() is True
    assert store_module._store_instance is None
    assert store_module._store_initialized is False


@pytest.mark.asyncio
async def test_abatch_limits_concurrent_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        store_module,
        "settings",
        SimpleNamespace(MONGODB_DB="agent_state", MONGODB_STORE_BATCH_CONCURRENCY=3),
    )

    class SlowGetStore(store_module.MongoDBStore):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.max_active = 0

        async def _aget(self, col, op):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return op.key

    store = SlowGetStore()
    store._collection = object()

    results = await store.abatch(GetOp(("ns",), f"key-{i}") for i in range(20))

    assert results == [f"key-{i}" for i in range(20)]
    assert store.max_active <= 3


@pytest.mark.asyncio
async def test_abatch_rejects_oversized_batches_before_materializing_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store_module, "MONGODB_STORE_BATCH_MAX_OPS", 2, raising=False)
    consumed: list[int] = []

    def _ops():
        for index in range(10):
            consumed.append(index)
            yield GetOp(("ns",), f"key-{index}")

    class _NoopStore(store_module.MongoDBStore):
        async def _aget(self, col, op):
            return op.key

    store = _NoopStore()
    store._collection = object()

    with pytest.raises(ValueError, match="too many store operations"):
        await store.abatch(_ops())

    assert consumed == [0, 1, 2]


@pytest.mark.asyncio
async def test_abatch_clamps_search_and_namespace_limits() -> None:
    class _FakeCursor:
        def __init__(self, docs: list[dict]) -> None:
            self.docs = docs
            self.skip_value = None
            self.limit_value = None
            self.to_list_length = None

        def skip(self, value: int):
            self.skip_value = value
            return self

        def limit(self, value: int):
            self.limit_value = value
            return self

        async def to_list(self, length: int | None = None):
            self.to_list_length = length
            return self.docs[: length or None]

    class _FakeCollection:
        def __init__(self) -> None:
            self.find_cursor = _FakeCursor(
                [
                    {
                        "namespace": ["users", "user-1"],
                        "key": "memory-1",
                        "value": {"text": "hello"},
                    }
                ]
            )
            self.aggregate_cursor = _FakeCursor([{"_id": ["users", "user-1"]}])
            self.aggregate_pipeline = None

        def find(self, *_args, **_kwargs):
            return self.find_cursor

        async def aggregate(self, pipeline):
            self.aggregate_pipeline = pipeline
            return self.aggregate_cursor

    collection = _FakeCollection()
    store = store_module.MongoDBStore()
    store._collection = collection

    await store.abatch(
        [
            SearchOp(("users",), limit=100_000, offset=-5),
            ListNamespacesOp(limit=100_000, offset=-5),
        ]
    )

    assert collection.find_cursor.skip_value == 0
    assert collection.find_cursor.limit_value == 100
    assert collection.find_cursor.to_list_length == 100
    assert {"$skip": 0} in collection.aggregate_pipeline
    assert {"$limit": 100} in collection.aggregate_pipeline
    assert collection.aggregate_cursor.to_list_length == 100
