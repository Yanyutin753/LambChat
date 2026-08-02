from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.infra.envvar import storage as envvar_storage
from src.infra.envvar.storage import MAX_ENV_VARS_PER_USER, EnvVarStorage


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self.limit_value: int | None = None

    def sort(self, *_args):
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def __aiter__(self):
        self._iter = iter(self._docs[: self.limit_value or None])
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.cursor = _FakeCursor(docs)
        self.count_calls = 0
        self.find_calls = 0
        self.update_calls = 0
        self.bulk_write_calls: list[list] = []
        self.bulk_write_ordered: list[bool] = []

    def find(self, *_args):
        self.find_calls += 1
        return self.cursor

    async def find_one(self, query: dict[str, Any], *_args):
        self.find_calls += 1
        for doc in self.cursor._docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    async def count_documents(self, *_args):
        self.count_calls += 1
        return 0

    async def update_one(self, *_args, **_kwargs):
        self.update_calls += 1

    async def bulk_write(self, operations, ordered: bool = False):
        self.bulk_write_calls.append(list(operations))
        self.bulk_write_ordered.append(ordered)


class _FakeMongoClient:
    def __init__(self, collection: Any) -> None:
        self._collection = collection

    def __getitem__(self, name: str):
        if name == envvar_storage.COLLECTION_NAME:
            return self._collection
        return self


def _env_doc(index: int) -> dict[str, Any]:
    return {
        "user_id": "user-1",
        "key": f"KEY_{index}",
        "value": {"encrypted": "ignored"},
        "created_at": "2026-04-25T00:00:00Z",
        "updated_at": "2026-04-25T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_list_vars_applies_cursor_limit() -> None:
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([_env_doc(index) for index in range(75)])

    items = await storage.list_vars("user-1")

    assert len(items) == MAX_ENV_VARS_PER_USER
    assert storage._coll.cursor.limit_value == MAX_ENV_VARS_PER_USER


@pytest.mark.asyncio
async def test_get_decrypted_vars_applies_cursor_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([_env_doc(index) for index in range(75)])

    async def _fake_decrypt(_value: Any) -> str:
        return "value"

    monkeypatch.setattr(storage, "_decrypt_value", _fake_decrypt)

    values = await storage.get_decrypted_vars("user-1")

    assert len(values) == MAX_ENV_VARS_PER_USER
    assert storage._coll.cursor.limit_value == MAX_ENV_VARS_PER_USER


@pytest.mark.asyncio
async def test_get_var_offloads_decryption(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([_env_doc(0)])

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return {"v": "secret"}

    monkeypatch.setattr(envvar_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    value = await storage.get_var("user-1", "KEY_0")

    assert calls == [envvar_storage.decrypt_value]
    assert value is not None
    assert value.value == "secret"


@pytest.mark.asyncio
async def test_get_decrypted_vars_offloads_each_decryption(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([_env_doc(0), _env_doc(1)])

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return {"v": f"secret-{len(calls)}"}

    monkeypatch.setattr(envvar_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    values = await storage.get_decrypted_vars("user-1")

    assert calls == [envvar_storage.decrypt_value, envvar_storage.decrypt_value]
    assert values == {"KEY_0": "secret-1", "KEY_1": "secret-2"}


@pytest.mark.asyncio
async def test_set_vars_bulk_rejects_oversized_payload_before_db_reads() -> None:
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([])

    with pytest.raises(ValueError):
        await storage.set_vars_bulk(
            "user-1",
            {f"KEY_{index}": "value" for index in range(MAX_ENV_VARS_PER_USER + 1)},
        )

    assert storage._coll.count_calls == 0
    assert storage._coll.find_calls == 0


@pytest.mark.asyncio
async def test_set_var_rejects_oversized_value_before_db_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([])
    monkeypatch.setattr(envvar_storage, "ENV_VAR_MAX_VALUE_CHARS", 4)

    with pytest.raises(ValueError) as exc:
        await storage.set_var("user-1", "TOKEN", "12345")

    assert "value too large" in str(exc.value)
    assert storage._coll.count_calls == 0
    assert storage._coll.find_calls == 0


@pytest.mark.asyncio
async def test_set_var_offloads_encryption(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([])

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return {"encrypted": args[0]}

    monkeypatch.setattr(envvar_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    await storage.set_var("user-1", "TOKEN", "secret")

    assert calls == [envvar_storage.encrypt_value]
    assert storage._coll.update_calls == 1


@pytest.mark.asyncio
async def test_set_vars_bulk_rejects_oversized_total_values_before_db_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([])
    monkeypatch.setattr(envvar_storage, "ENV_VAR_MAX_TOTAL_VALUE_CHARS", 8)

    with pytest.raises(ValueError) as exc:
        await storage.set_vars_bulk(
            "user-1",
            {
                "A": "1234",
                "B": "56789",
            },
        )

    assert "values too large" in str(exc.value)
    assert storage._coll.count_calls == 0
    assert storage._coll.find_calls == 0


@pytest.mark.asyncio
async def test_set_vars_bulk_limits_existing_key_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([_env_doc(index) for index in range(75)])

    async def _fake_encrypt(value: str) -> dict[str, str]:
        return {"v": value}

    monkeypatch.setattr(storage, "_encrypt_value", _fake_encrypt)

    updated = await storage.set_vars_bulk("user-1", {"KEY_0": "new"})

    assert updated == 1
    assert storage._coll.cursor.limit_value == MAX_ENV_VARS_PER_USER
    assert storage._coll.update_calls == 0
    assert len(storage._coll.bulk_write_calls) == 1
    assert len(storage._coll.bulk_write_calls[0]) == 1


@pytest.mark.asyncio
async def test_set_vars_bulk_offloads_each_encryption(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([])

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return {"encrypted": args[0]}

    monkeypatch.setattr(envvar_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    updated = await storage.set_vars_bulk("user-1", {"A": "one", "B": "two"})

    assert updated == 2
    assert calls == [envvar_storage.encrypt_value, envvar_storage.encrypt_value]
    assert storage._coll.update_calls == 0
    assert len(storage._coll.bulk_write_calls) == 1
    assert len(storage._coll.bulk_write_calls[0]) == 2


@pytest.mark.asyncio
async def test_set_vars_bulk_uses_single_ordered_bulk_write_with_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = EnvVarStorage()
    storage._collection = _FakeCollection([])

    async def _fake_encrypt(value: str) -> dict[str, str]:
        return {"v": value}

    monkeypatch.setattr(storage, "_encrypt_value", _fake_encrypt)

    variables = {"A": "one", "B": "two", "C": "three"}

    updated = await storage.set_vars_bulk("user-1", variables)

    assert updated == len(variables)
    assert storage._coll.update_calls == 0
    assert len(storage._coll.bulk_write_calls) == 1
    assert storage._coll.bulk_write_ordered == [True]
    operations = storage._coll.bulk_write_calls[0]
    assert len(operations) == len(variables)
    for operation, key in zip(operations, variables.keys()):
        assert operation._filter == {"user_id": "user-1", "key": key}
        assert operation._upsert is True
        update_doc = operation._doc
        assert "created_at" in update_doc["$setOnInsert"]
        assert "value" in update_doc["$set"]
        assert "updated_at" in update_doc["$set"]


@pytest.mark.asyncio
async def test_env_var_storage_reuses_inflight_index_task_across_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowIndexCollection(_FakeCollection):
        def __init__(self) -> None:
            super().__init__([])
            self.create_index_calls = 0

        async def create_index(self, *_args, **_kwargs) -> None:
            self.create_index_calls += 1
            started.set()
            await release.wait()

    collection = _SlowIndexCollection()
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient(collection),
    )
    monkeypatch.setattr(EnvVarStorage, "_index_task", None, raising=False)
    monkeypatch.setattr(EnvVarStorage, "_index_ensured", False, raising=False)

    first = EnvVarStorage()
    second = EnvVarStorage()

    first._coll
    await asyncio.wait_for(started.wait(), timeout=1)
    second._coll
    await asyncio.sleep(0)

    release.set()
    task = EnvVarStorage._index_task
    if task is not None:
        await task

    assert collection.create_index_calls == 1


@pytest.mark.asyncio
async def test_env_var_storage_close_cancels_index_task_and_clears_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    class _SlowIndexCollection(_FakeCollection):
        def __init__(self) -> None:
            super().__init__([])

        async def create_index(self, *_args, **_kwargs) -> None:
            started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient(_SlowIndexCollection()),
    )
    monkeypatch.setattr(EnvVarStorage, "_index_task", None, raising=False)
    monkeypatch.setattr(EnvVarStorage, "_index_ensured", False, raising=False)

    storage = EnvVarStorage()
    storage._coll
    task = EnvVarStorage._index_task
    assert task is not None
    await asyncio.wait_for(started.wait(), timeout=1)

    await storage.close()

    assert task.cancelled() is True
    assert storage._collection is None
    assert EnvVarStorage._index_task is None
    assert EnvVarStorage._index_ensured is False
