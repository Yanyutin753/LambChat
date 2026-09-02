import asyncio

import pytest

from src.infra.memory.client.native import backend as backend_module
from src.infra.memory.client.native.backend import NativeMemoryBackend


@pytest.mark.asyncio
async def test_delete_removes_store_payload_for_long_memory():
    seen: dict[str, object] = {}

    class FakeCollection:
        async def find_one(self, query, _projection=None):
            seen["find_query"] = query
            return {
                "user_id": "u1",
                "memory_id": "m1",
                "content_storage_mode": "store",
                "content_store_key": "memory:m1",
            }

        async def delete_one(self, query):
            seen["delete_query"] = query

            class Result:
                deleted_count = 1

            return Result()

    class FakeStore:
        async def aput(self, namespace, key, value):
            seen["store_delete"] = {"namespace": namespace, "key": key, "value": value}

    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()
    backend._store = FakeStore()

    async def fake_invalidate(_user_id):
        seen["invalidated"] = True

    backend._invalidate_cache = fake_invalidate  # type: ignore[method-assign]

    result = await backend.delete("u1", "m1")

    assert result["success"] is True
    assert seen["find_query"] == {"user_id": "u1", "memory_id": "m1"}
    assert seen["delete_query"] == {"user_id": "u1", "memory_id": "m1"}
    assert seen["store_delete"] == {
        "namespace": ("memories", "u1", "content"),
        "key": "memory:m1",
        "value": None,
    }
    assert seen["invalidated"] is True


@pytest.mark.asyncio
async def test_maybe_embed_offloads_sync_embedding_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    backend = NativeMemoryBackend()

    def sync_embedding(text: str) -> list[float]:
        assert text == "hello"
        return [1.0, 2.0]

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    backend._embedding_fn = sync_embedding
    monkeypatch.setattr(backend_module, "run_blocking_io", fake_run_blocking_io)

    result = await backend._maybe_embed("hello")

    assert result == [1.0, 2.0]
    assert calls == [sync_embedding]


@pytest.mark.asyncio
async def test_maybe_embed_awaits_future_returned_by_embedding_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = NativeMemoryBackend()

    def future_embedding(text: str) -> asyncio.Future[list[float]]:
        assert text == "hello"
        future = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_later(0.01, future.set_result, [3.0, 4.0])
        return future

    async def fake_run_blocking_io(func, *args, **kwargs):
        return func(*args, **kwargs)

    backend._embedding_fn = future_embedding
    monkeypatch.setattr(backend_module, "run_blocking_io", fake_run_blocking_io)

    result = await backend._maybe_embed("hello")

    assert result == [3.0, 4.0]


@pytest.mark.asyncio
async def test_get_memory_model_uses_native_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    async def fake_get_model(**kwargs):
        calls.append(kwargs)
        return object()

    async def fake_resolve_model_reference(_value):
        return "memory-model-id", None

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", fake_get_model)
    monkeypatch.setattr(
        "src.infra.llm.models_service.resolve_model_reference",
        fake_resolve_model_reference,
    )
    monkeypatch.setattr(backend_module.settings, "NATIVE_MEMORY_MODEL", "memory-model-id")
    # 钉住 max_tokens——测试不得依赖开发者本地 .env 的覆盖值
    monkeypatch.setattr(backend_module.settings, "NATIVE_MEMORY_MAX_TOKENS", 2000)
    monkeypatch.setattr(backend_module.settings, "NATIVE_MEMORY_API_BASE", "https://unused.test/v1")
    monkeypatch.setattr(backend_module.settings, "NATIVE_MEMORY_API_KEY", "unused-key")

    await NativeMemoryBackend._get_memory_model()

    assert calls == [
        {
            "model_id": "memory-model-id",
            "temperature": 0.1,
            "max_tokens": 2000,
        }
    ]


@pytest.mark.asyncio
async def test_get_memory_model_uses_default_model_when_native_model_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_get_model(**kwargs):
        calls.append(kwargs)
        return object()

    async def fake_resolve_model_reference(_value):
        return None, None

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", fake_get_model)
    monkeypatch.setattr(
        "src.infra.llm.models_service.resolve_model_reference",
        fake_resolve_model_reference,
    )
    monkeypatch.setattr(backend_module.settings, "NATIVE_MEMORY_MODEL", "")
    monkeypatch.setattr(backend_module.settings, "NATIVE_MEMORY_MAX_TOKENS", 2000)

    await NativeMemoryBackend._get_memory_model()

    assert calls == [
        {
            "model_id": None,
            "temperature": 0.1,
            "max_tokens": 2000,
        }
    ]


class _FakeVectorCollection:
    def __init__(self, existing_names, fail_create=False):
        self._existing_names = existing_names
        self._fail_create = fail_create
        self.create_calls: list[dict] = []

    def list_search_indexes(self):
        return iter({"name": name} for name in self._existing_names)

    def create_search_index(self, definition):
        self.create_calls.append(definition)
        if self._fail_create:
            raise RuntimeError("mongot unavailable")


def _fake_mongo_delegate(col):
    class _Db(dict):
        def __getitem__(self, name):
            return col

    class _Delegate:
        def __getitem__(self, name):
            return _Db()

    class _Client:
        delegate = _Delegate()

    return _Client()


@pytest.mark.asyncio
async def test_vector_index_created_when_embedding_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    col = _FakeVectorCollection(existing_names=[])
    backend = NativeMemoryBackend()
    backend._embedding_fn = lambda _text: [0.0]
    monkeypatch.setattr(backend_module, "get_mongo_client", lambda: _fake_mongo_delegate(col))
    monkeypatch.setattr(backend_module.settings, "NATIVE_MEMORY_EMBEDDING_DIMENSIONS", 1536)

    async def direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(backend_module, "run_blocking_io", direct)

    await backend._maybe_create_vector_index()

    assert len(col.create_calls) == 1
    definition = col.create_calls[0]
    assert definition["name"] == "native_mem_vector_idx"
    assert definition["type"] == "vectorSearch"
    field = definition["definition"]["fields"][0]
    assert field["path"] == "embedding"
    assert field["numDimensions"] == 1536
    assert field["similarity"] == "cosine"


@pytest.mark.asyncio
async def test_vector_index_skipped_when_already_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    col = _FakeVectorCollection(existing_names=["native_mem_vector_idx"])
    backend = NativeMemoryBackend()
    backend._embedding_fn = lambda _text: [0.0]
    monkeypatch.setattr(backend_module, "get_mongo_client", lambda: _fake_mongo_delegate(col))

    async def direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(backend_module, "run_blocking_io", direct)

    await backend._maybe_create_vector_index()

    assert col.create_calls == []


@pytest.mark.asyncio
async def test_vector_index_skipped_without_embedding_fn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    col = _FakeVectorCollection(existing_names=[])
    backend = NativeMemoryBackend()
    backend._embedding_fn = None
    monkeypatch.setattr(backend_module, "get_mongo_client", lambda: _fake_mongo_delegate(col))

    await backend._maybe_create_vector_index()

    assert col.create_calls == []


@pytest.mark.asyncio
async def test_vector_index_failure_is_non_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    col = _FakeVectorCollection(existing_names=[], fail_create=True)
    backend = NativeMemoryBackend()
    backend._embedding_fn = lambda _text: [0.0]
    monkeypatch.setattr(backend_module, "get_mongo_client", lambda: _fake_mongo_delegate(col))

    async def direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(backend_module, "run_blocking_io", direct)

    await backend._maybe_create_vector_index()  # 不抛异常即通过


@pytest.mark.asyncio
async def test_embedding_client_keeps_connections_warm(monkeypatch: pytest.MonkeyPatch):
    """embedding 客户端 keepalive 必须拉长：httpx 默认 5s 闲置断连，
    每条隔闲消息重付 ~1.5s TLS 握手，恰好击穿 1.5s 注入预算
    （staging 实测：冷 1.99s 注入失败 → 热 0.44s 注入成功）。"""
    import httpx

    recorded: dict[str, object] = {}
    real_client = httpx.AsyncClient

    def spy_client(**kwargs):
        recorded.update(kwargs)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", spy_client)
    backend = NativeMemoryBackend()
    monkeypatch.setattr(
        backend_module.settings, "NATIVE_MEMORY_EMBEDDING_API_BASE", "https://unused.test/v1"
    )
    monkeypatch.setattr(backend_module.settings, "NATIVE_MEMORY_EMBEDDING_API_KEY", "unused-key")

    backend._setup_embedding_fn()

    assert backend._embedding_fn is not None, "应创建 embedding 函数"
    limits = recorded.get("limits")
    assert limits is not None and limits.keepalive_expiry >= 60  # type: ignore[union-attr]
    await backend.close()
