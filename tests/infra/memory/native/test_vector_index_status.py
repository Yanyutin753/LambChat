import logging

from pymongo.errors import OperationFailure

from src.infra.memory.client.native import backend as module
from src.infra.memory.client.native import vector_store


async def test_qdrant_does_not_attempt_an_unused_mongo_vector_index(monkeypatch):
    backend = module.NativeMemoryBackend()
    backend._embedding_fn = object()
    monkeypatch.setattr(vector_store, "vector_backend_enabled", lambda: True)

    def no_mongo():
        raise AssertionError("Qdrant must not request Atlas search indexes")

    monkeypatch.setattr(module, "get_mongo_sync_client", no_mongo)
    await backend._maybe_create_vector_index()
    assert backend.search_status["vector_backend"] == "qdrant"
    assert backend.search_status["mongodb_index"] == "not_required"


async def test_unsupported_mongo_search_exposes_cosine_fallback_without_warning(
    monkeypatch, caplog
):
    backend = module.NativeMemoryBackend()
    backend._embedding_fn = object()
    monkeypatch.setattr(vector_store, "vector_backend_enabled", lambda: False)
    monkeypatch.setattr(
        module,
        "get_mongo_sync_client",
        lambda: {module.settings.MONGODB_DB: {module.COLLECTION_NAME: object()}},
    )

    def unsupported(_collection):
        raise OperationFailure("SearchNotEnabled", code=31082)

    monkeypatch.setattr(backend, "_create_vector_index_sync", unsupported)
    with caplog.at_level(logging.INFO):
        await backend._maybe_create_vector_index()
    assert backend.search_status["mongodb_index"] == "unavailable"
    assert backend.search_status["fallback"] == "cosine"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_memory_listing_exposes_backend_search_status(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.api.routes import memory

    class Cursor:
        def sort(self, *args):
            return self

        def skip(self, *args):
            return self

        def limit(self, *args):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    status = {"vector_backend": "qdrant", "mongodb_index": "not_required", "fallback": "cosine"}
    collection = SimpleNamespace(
        count_documents=AsyncMock(return_value=0), find=lambda *args: Cursor()
    )
    monkeypatch.setattr(
        memory,
        "_get_backend",
        AsyncMock(return_value=SimpleNamespace(_collection=collection, search_status=status)),
    )
    result = await memory.list_memories(
        memory_type=None,
        search=None,
        context=None,
        source=None,
        limit=50,
        offset=0,
        user=SimpleNamespace(sub="owner"),
    )
    assert result["search_status"] == status
