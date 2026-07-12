from __future__ import annotations

import asyncio

import pytest

from src.infra.session import trace_storage as trace_storage_module
from src.infra.session.trace_storage import TraceStorage


class _FakeMongoClient:
    def __init__(self, collections: dict[str, object]) -> None:
        self._collections = collections

    def __getitem__(self, name: str):
        if name in self._collections:
            return self._collections[name]
        return self


@pytest.mark.asyncio
async def test_close_trace_storage_releases_singleton_without_creating_one() -> None:
    trace_storage_module._trace_storage = None

    await trace_storage_module.close_trace_storage()

    assert trace_storage_module._trace_storage is None


@pytest.mark.asyncio
async def test_ensure_indexes_initializes_collection_and_tracks_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Collection:
        def __init__(self) -> None:
            self.create_index_names: list[str] = []

        async def create_index(self, *_args, **_kwargs) -> None:
            self.create_index_names.append(_kwargs["name"])

    traces_collection = _Collection()
    chunks_collection = _Collection()
    monkeypatch.setattr(
        trace_storage_module,
        "get_mongo_client",
        lambda: _FakeMongoClient(
            {
                trace_storage_module.settings.MONGODB_TRACES_COLLECTION: traces_collection,
                trace_storage_module.settings.MONGODB_TRACE_EVENT_CHUNKS_COLLECTION: chunks_collection,
            }
        ),
    )
    monkeypatch.setattr(trace_storage_module.settings, "ENABLE_EVENT_MERGER", False)

    storage = TraceStorage()

    await storage.ensure_indexes_if_needed()
    task = storage._indexes_task
    assert task is not None
    await task

    assert storage._collection is traces_collection
    assert storage._chunks_collection is chunks_collection
    assert "trace_id_unique_idx" in traces_collection.create_index_names
    assert chunks_collection.create_index_names == [
        "trace_chunk_unique_idx",
        "session_run_chunk_idx",
        "session_trace_started_chunk_idx",
        "trace_end_seq_idx",
    ]


@pytest.mark.asyncio
async def test_close_trace_storage_cancels_inflight_index_task_and_clears_refs() -> None:
    started = asyncio.Event()

    class _SlowIndexStorage(TraceStorage):
        async def _ensure_indexes(self) -> None:
            started.set()
            await asyncio.Event().wait()

    storage = _SlowIndexStorage()
    storage._collection = object()
    storage._chunks_collection = object()
    storage._merger = object()
    storage._start_merger = lambda: None
    trace_storage_module._trace_storage = storage

    await storage.ensure_indexes_if_needed()
    task = storage._indexes_task
    assert task is not None
    await asyncio.wait_for(started.wait(), timeout=1)

    await trace_storage_module.close_trace_storage()

    assert task.cancelled() is True
    assert storage._indexes_task is None
    assert storage._collection is None
    assert storage._chunks_collection is None
    assert storage._merger is None
    assert not hasattr(storage, "_indexes_ensured")
    assert trace_storage_module._trace_storage is None

    storage = TraceStorage()
    trace_storage_module._trace_storage = storage

    await trace_storage_module.close_trace_storage()

    assert trace_storage_module._trace_storage is None


@pytest.mark.asyncio
async def test_delete_trace_deletes_event_chunks() -> None:
    class _TraceCollection:
        async def delete_one(self, query):
            assert query == {"trace_id": "trace-1"}
            return type("_Result", (), {"deleted_count": 1})()

    class _ChunkCollection:
        def __init__(self) -> None:
            self.delete_queries = []

        async def delete_many(self, query):
            self.delete_queries.append(query)

    chunks = _ChunkCollection()
    storage = TraceStorage()
    storage._collection = _TraceCollection()
    storage._chunks_collection = chunks

    assert await storage.delete_trace("trace-1") is True
    assert chunks.delete_queries == [{"trace_id": "trace-1"}]


@pytest.mark.asyncio
async def test_delete_session_traces_deletes_event_chunks_for_session_traces() -> None:
    class _Cursor:
        async def to_list(self, length=None):
            del length
            return [{"trace_id": "trace-1"}, {"trace_id": "trace-2"}]

    class _TraceCollection:
        def __init__(self) -> None:
            self.find_calls = []
            self.delete_many_calls = []

        def find(self, query, projection):
            self.find_calls.append((query, projection))
            return _Cursor()

        async def delete_many(self, query):
            self.delete_many_calls.append(query)
            return type("_Result", (), {"deleted_count": 2})()

    class _ChunkCollection:
        def __init__(self) -> None:
            self.delete_queries = []

        async def delete_many(self, query):
            self.delete_queries.append(query)

    traces = _TraceCollection()
    chunks = _ChunkCollection()
    storage = TraceStorage()
    storage._collection = traces
    storage._chunks_collection = chunks

    assert await storage.delete_session_traces("session-1") == 2
    assert traces.find_calls == [({"session_id": "session-1"}, {"_id": 0, "trace_id": 1})]
    assert chunks.delete_queries == [{"trace_id": {"$in": ["trace-1", "trace-2"]}}]
    assert traces.delete_many_calls == [{"session_id": "session-1"}]
