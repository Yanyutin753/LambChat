import asyncio
import json
from datetime import timedelta

import pytest

from src.infra.memory.client.native.consolidation import (
    consolidate_memories,
    do_consolidate,
)
from src.infra.utils.datetime import utc_now


@pytest.mark.asyncio
async def test_consolidation_skips_when_lock_service_is_unavailable():
    called = {"do": False}

    class DummyBackend:
        async def _do_consolidate(self, _user_id):
            called["do"] = True
            return {"merged": 1}

    async def lock_unavailable(*_args, **_kwargs):
        return "unavailable"

    async def release(*_args, **_kwargs):
        return None

    result = await consolidate_memories(
        DummyBackend(),
        "u1",
        acquire_lock=lock_unavailable,
        release_lock=release,
    )

    assert result["skipped"] is True
    assert result["reason"] == "lock_unavailable"
    assert called["do"] is False


@pytest.mark.asyncio
async def test_consolidation_skips_when_lock_is_not_acquired():
    called = {"do": False}

    class DummyBackend:
        async def _do_consolidate(self, _user_id):
            called["do"] = True
            return {"merged": 1}

    async def lock_not_acquired(*_args, **_kwargs):
        return "not_acquired"

    async def release(*_args, **_kwargs):
        return None

    result = await consolidate_memories(
        DummyBackend(),
        "u1",
        acquire_lock=lock_not_acquired,
        release_lock=release,
    )

    assert result["skipped"] is True
    assert result["reason"] == "lock_not_acquired"
    assert called["do"] is False


@pytest.mark.asyncio
async def test_consolidation_runs_only_when_lock_is_acquired():
    called = {"do": False, "release": False}

    class DummyBackend:
        async def _do_consolidate(self, _user_id):
            called["do"] = True
            return {"merged": 2, "pruned": 1}

    async def lock_acquired(*_args, **_kwargs):
        return "acquired"

    async def release(*_args, **_kwargs):
        called["release"] = True

    result = await consolidate_memories(
        DummyBackend(),
        "u1",
        acquire_lock=lock_acquired,
        release_lock=release,
    )

    assert result["merged"] == 2
    assert called["do"] is True
    assert called["release"] is True


@pytest.mark.asyncio
async def test_llm_batch_consolidate_uses_store_for_long_content(monkeypatch):
    from src.infra.memory.client.native import consolidation as consolidation_module

    long_content = "A" * 1600

    class FakeModel:
        async def ainvoke(self, _messages):
            class Response:
                content = (
                    '[{"content": "%s", "summary": "Long summary", "title": "Long title"}]'
                    % long_content
                )

            return Response()

    class FakeBackend:
        def __init__(self):
            self._logger = None
            self._store = FakeStore()

        @staticmethod
        def _get_memory_model():
            return FakeModel()

        async def _maybe_embed(self, _text):
            return None

    class FakeStore:
        async def aput(self, _namespace, _key, _value):
            return None

    docs = await consolidation_module.llm_batch_consolidate(
        FakeBackend(),
        [
            {
                "memory_id": "m1",
                "user_id": "u1",
                "content": "old",
                "created_at": None,
                "source_refs": [{"session_id": "s1", "run_id": "r1"}],
            },
            {
                "memory_id": "m2",
                "user_id": "u1",
                "content": "old2",
                "created_at": None,
                "source_refs": [{"session_id": "s2", "run_id": "r2"}],
            },
            {
                "memory_id": "m3",
                "user_id": "u1",
                "content": "old3",
                "created_at": None,
                "source_refs": [{"session_id": "s1", "run_id": "r1"}],
            },
        ],
        expected_type="user",
    )

    assert docs is not None
    assert docs[0]["content_storage_mode"] == "store"
    assert docs[0]["content_store_key"] is not None
    assert docs[0]["content"].endswith("...")
    assert docs[0]["source"] == "consolidated"
    assert docs[0]["source_refs"] == [
        {"session_id": "s2", "run_id": "r2"},
        {"session_id": "s1", "run_id": "r1"},
    ]


@pytest.mark.asyncio
async def test_llm_batch_consolidate_offloads_llm_json_parse(monkeypatch):
    from src.infra.memory.client.native import consolidation as consolidation_module

    calls: list[object] = []

    class FakeModel:
        async def ainvoke(self, _messages):
            class Response:
                content = '[{"content": "memory one", "summary": "Summary", "title": "Title"}]'

            return Response()

    class FakeBackend:
        def __init__(self):
            self._logger = None
            self._store = FakeStore()

        @staticmethod
        def _get_memory_model():
            return FakeModel()

        async def _maybe_embed(self, _text):
            return None

    class FakeStore:
        async def aput(self, _namespace, _key, _value):
            return None

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        consolidation_module, "run_blocking_io", _fake_run_blocking_io, raising=False
    )

    docs = await consolidation_module.llm_batch_consolidate(
        FakeBackend(),
        [
            {
                "memory_id": "m1",
                "user_id": "u1",
                "content": "old",
                "created_at": None,
            },
            {
                "memory_id": "m2",
                "user_id": "u1",
                "content": "old2",
                "created_at": None,
            },
            {
                "memory_id": "m3",
                "user_id": "u1",
                "content": "old3",
                "created_at": None,
            },
        ],
        expected_type="user",
    )

    assert calls == [json.loads]
    assert docs is not None


@pytest.mark.asyncio
async def test_llm_batch_consolidate_clips_oversized_input_memory_content(
    monkeypatch,
) -> None:
    from src.infra.memory.client.native import consolidation as consolidation_module

    captured_prompt: dict[str, str] = {}
    oversized = "important-prefix " + ("middle " * 20) + "secret-tail"

    class FakeModel:
        async def ainvoke(self, messages):
            captured_prompt["content"] = messages[1].content

            class Response:
                content = (
                    '[{"content": "retained memory content", '
                    '"summary": "Summary", "title": "Title"}]'
                )

            return Response()

    class FakeBackend:
        def __init__(self):
            self._logger = None
            self._store = FakeStore()

        @staticmethod
        def _get_memory_model():
            return FakeModel()

        async def _maybe_embed(self, _text):
            return None

    class FakeStore:
        async def aput(self, _namespace, _key, _value):
            return None

    monkeypatch.setattr(
        consolidation_module.settings,
        "NATIVE_MEMORY_CONSOLIDATION_INPUT_MAX_CHARS",
        24,
    )

    docs = await consolidation_module.llm_batch_consolidate(
        FakeBackend(),
        [
            {
                "memory_id": f"m{index}",
                "user_id": "u1",
                "content": oversized,
                "created_at": None,
            }
            for index in range(3)
        ],
        expected_type="user",
    )

    assert docs is not None
    assert "important-prefix" in captured_prompt["content"]
    assert "secret-tail" not in captured_prompt["content"]
    assert "truncated from" in captured_prompt["content"]


@pytest.mark.asyncio
async def test_llm_batch_consolidate_limits_concurrent_item_enrichment(
    monkeypatch,
) -> None:
    from src.infra.memory.client.native import consolidation as consolidation_module

    active = 0
    max_active = 0
    release = asyncio.Event()
    started = asyncio.Event()

    class FakeModel:
        async def ainvoke(self, _messages):
            class Response:
                content = (
                    "["
                    '{"content": "first retained memory content"},'
                    '{"content": "second retained memory content"},'
                    '{"content": "third retained memory content"},'
                    '{"content": "fourth retained memory content"}'
                    "]"
                )

            return Response()

    class FakeBackend:
        def __init__(self):
            self._logger = None
            self._store = None

        @staticmethod
        def _get_memory_model():
            return FakeModel()

        async def _maybe_embed(self, _text):
            return None

    async def fake_enrich_item(*_args):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            started.set()
        await release.wait()
        active -= 1
        return {"summary": "summary", "title": "title", "tags": ["tag"]}

    monkeypatch.setattr(consolidation_module, "_enrich_item", fake_enrich_item)
    monkeypatch.setattr(
        consolidation_module.settings,
        "NATIVE_MEMORY_CONSOLIDATION_ENRICH_CONCURRENCY",
        2,
        raising=False,
    )

    task = asyncio.create_task(
        consolidation_module.llm_batch_consolidate(
            FakeBackend(),
            [
                {
                    "memory_id": "m1",
                    "user_id": "u1",
                    "content": "old",
                    "created_at": None,
                },
                {
                    "memory_id": "m2",
                    "user_id": "u1",
                    "content": "old2",
                    "created_at": None,
                },
                {
                    "memory_id": "m3",
                    "user_id": "u1",
                    "content": "old3",
                    "created_at": None,
                },
            ],
            expected_type="user",
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    assert max_active == 2

    release.set()
    docs = await task

    assert docs is not None
    assert len(docs) == 4


@pytest.mark.asyncio
async def test_delete_memory_contents_limits_concurrency(monkeypatch) -> None:
    from src.infra.memory.client.native import consolidation as consolidation_module

    active = 0
    max_active = 0
    release = asyncio.Event()
    started = asyncio.Event()

    async def fake_delete(_backend, _user_id, _key):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            started.set()
        await release.wait()
        active -= 1

    monkeypatch.setattr(consolidation_module, "delete_memory_content", fake_delete)
    monkeypatch.setattr(
        consolidation_module.settings,
        "NATIVE_MEMORY_CONTENT_DELETE_CONCURRENCY",
        2,
        raising=False,
    )

    task = asyncio.create_task(
        consolidation_module._delete_memory_contents_limited(
            object(),
            "u1",
            [f"memory:{i}" for i in range(8)],
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    assert max_active == 2

    release.set()
    await task


@pytest.mark.asyncio
async def test_do_consolidate_streams_memory_cursor_without_bulk_to_list(monkeypatch) -> None:
    from src.infra.memory.client.native import consolidation as consolidation_module

    now = utc_now()
    docs = [
        {
            "memory_id": f"m{i}",
            "user_id": "u1",
            "content": f"durable preference {i}",
            "memory_type": "user",
            "source": "auto_retained",
            "created_at": now - timedelta(days=10 - i),
            "updated_at": now,
            "access_count": 2,
        }
        for i in range(5)
    ]

    class StreamingOnlyCursor:
        def __init__(self, items):
            self._items = list(items)

        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def __aiter__(self):
            self._iter = iter(self._items)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

        async def to_list(self, length=None):
            raise AssertionError(f"bulk cursor materialization is not allowed: {length}")

    class FakeDeleteResult:
        deleted_count = 0

    class FakeCollection:
        def find(self, *_args, **_kwargs):
            return StreamingOnlyCursor(docs)

        async def count_documents(self, _query):
            return len(docs)

        async def delete_many(self, _query):
            return FakeDeleteResult()

        async def insert_many(self, _docs):
            return None

    class FakeBackend:
        _collection = FakeCollection()

        async def _invalidate_cache(self, _user_id):
            return None

    async def fake_batch_consolidate(_backend, batch, _expected_type):
        return list(batch)

    monkeypatch.setattr(
        consolidation_module,
        "_llm_batch_consolidate",
        fake_batch_consolidate,
    )

    result = await do_consolidate(FakeBackend(), "u1")

    assert result["total_before"] == 5
    assert result["merged"] == 0


@pytest.mark.asyncio
async def test_do_consolidate_prunes_cap_overflow_in_bounded_batches(monkeypatch) -> None:
    from src.infra.memory.client.native import consolidation as consolidation_module

    now = utc_now()
    scanned_docs = [
        {
            "memory_id": f"scan-{index}",
            "user_id": "u1",
            "content": f"manual memory {index}",
            "memory_type": "user",
            "source": "manual",
            "created_at": now,
            "updated_at": now,
            "access_count": 0,
        }
        for index in range(5)
    ]
    overflow_docs = [
        {
            "memory_id": f"old-{index}",
            "user_id": "u1",
            "content_storage_mode": "inline",
            "created_at": now,
        }
        for index in range(250)
    ]

    class StreamingCursor:
        def __init__(self, items):
            self._items = list(items)

        def limit(self, *_args, **_kwargs):
            return self

        def __aiter__(self):
            self._iter = iter(self._items)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    class BoundedListCursor:
        def __init__(self, collection):
            self.collection = collection
            self.limit_value = None

        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, value):
            self.limit_value = value
            self.collection.limit_values.append(value)
            return self

        async def to_list(self, length=None):
            self.collection.to_list_lengths.append(length)
            assert length <= 100
            batch = self.collection.overflow_docs[:length]
            return [dict(doc) for doc in batch]

    class FakeDeleteResult:
        def __init__(self, deleted_count):
            self.deleted_count = deleted_count

    class FakeCollection:
        def __init__(self):
            self.overflow_docs = list(overflow_docs)
            self.find_calls = 0
            self.limit_values = []
            self.to_list_lengths = []

        def find(self, *_args, **_kwargs):
            self.find_calls += 1
            if self.find_calls == 1:
                return StreamingCursor(scanned_docs)
            return BoundedListCursor(self)

        async def count_documents(self, _query):
            return 200 + len(self.overflow_docs)

        async def delete_many(self, query):
            ids = set(query["memory_id"]["$in"])
            before = len(self.overflow_docs)
            self.overflow_docs = [doc for doc in self.overflow_docs if doc["memory_id"] not in ids]
            return FakeDeleteResult(before - len(self.overflow_docs))

    class FakeBackend:
        def __init__(self):
            self._collection = FakeCollection()
            self.invalidated = 0

        async def _invalidate_cache(self, _user_id):
            self.invalidated += 1

    monkeypatch.setattr(
        consolidation_module,
        "_CONSOLIDATION_CAP_PRUNE_BATCH_SIZE",
        100,
        raising=False,
    )

    backend = FakeBackend()
    result = await do_consolidate(backend, "u1")

    assert result["pruned"] == 250
    assert result["total_after"] == 200
    assert backend._collection.to_list_lengths == [100, 100, 50]
    assert backend._collection.limit_values == [100, 100, 50]
    assert backend.invalidated >= 1


def test_native_memory_content_delete_concurrency_setting_default() -> None:
    from src.kernel.config.base import Settings
    from src.kernel.config.definitions import SETTING_DEFINITIONS

    definition = SETTING_DEFINITIONS["NATIVE_MEMORY_CONTENT_DELETE_CONCURRENCY"]

    assert Settings(_env_file=None).NATIVE_MEMORY_CONTENT_DELETE_CONCURRENCY == 4
    assert definition["default"] == 4
    assert definition["depends_on"] == "ENABLE_MEMORY"
