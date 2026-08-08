from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.kernel.config import SETTING_DEFINITIONS


class _FakeCursor:
    def __init__(self) -> None:
        self.length = None

    async def to_list(self, length=None):
        self.length = length
        return []


class _FakeCollection:
    def __init__(self) -> None:
        self.cursor = _FakeCursor()
        self.find_calls = []

    def find(self, query, projection=None):
        self.find_calls.append((query, projection))
        return self.cursor


class _SettingsWriteCollection:
    def __init__(self, values: dict[str, Any]) -> None:
        self.docs = {key: {"_id": key, "value": value} for key, value in values.items()}
        self.deleted_keys: list[str] = []

    async def find_one(self, query, projection=None):
        del projection
        doc = self.docs.get(query["_id"])
        return dict(doc) if doc else None

    async def find_one_and_update(self, query, update, **_kwargs):
        key = query["_id"]
        await asyncio.sleep(0)
        current = self.docs.get(key)
        if current is None:
            return None
        for field, condition in query.items():
            if field == "_id":
                continue
            if "$gte" in condition and current[field] < condition["$gte"]:
                return None
            if "$lte" in condition and current[field] > condition["$lte"]:
                return None
        doc = {**current, **update["$set"]}
        self.docs[key] = doc
        return dict(doc)

    async def update_one(self, query, update, **_kwargs):
        await asyncio.sleep(0)
        key = query["_id"]
        current = self.docs.get(key)
        if current is None:
            current = {"_id": key}
            current.update(update.get("$setOnInsert", {}))
        current.update(update.get("$set", {}))
        self.docs[key] = current

    async def delete_one(self, query):
        key = query["_id"]
        current = self.docs.get(key)
        owner = query.get("owner")
        if current and (owner is None or current.get("owner") == owner):
            del self.docs[key]
            self.deleted_keys.append(key)

            class _Result:
                deleted_count = 1

            return _Result()

        class _Result:
            deleted_count = 0

        return _Result()

    async def delete_many(self, query):
        keys = set(query["_id"]["$in"])
        deleted = [key for key in self.docs if key in keys]
        for key in deleted:
            del self.docs[key]

        class _Result:
            deleted_count = len(deleted)

        return _Result()


@pytest.mark.asyncio
async def test_get_all_bounds_settings_query() -> None:
    from src.infra.settings.storage import SettingsStorage

    collection = _FakeCollection()
    storage = SettingsStorage()
    storage._collection = collection

    await storage.get_all(admin_mode=True)

    assert collection.cursor.length == len(SETTING_DEFINITIONS) + 2
    query, projection = collection.find_calls[0]
    assert query == {
        "_id": {
            "$in": [
                *SETTING_DEFINITIONS.keys(),
                "__settings_atomic__:mongodb_pool:business",
                "__settings_atomic__:mongodb_pool:checkpoint",
            ]
        }
    }
    assert projection == {
        "_id": 1,
        "value": 1,
        "min": 1,
        "max": 1,
        "updated_at": 1,
        "updated_by": 1,
    }


@pytest.mark.asyncio
async def test_settings_storage_close_clears_local_client_reference() -> None:
    from src.infra.settings.storage import SettingsStorage

    storage = SettingsStorage()
    storage._client = object()
    storage._collection = _FakeCollection()

    await storage.close()

    assert storage._client is None
    assert storage._collection is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("MONGODB_POOL_MIN_SIZE", -1),
        ("MONGODB_POOL_MAX_SIZE", 0),
        ("CHECKPOINT_MONGO_POOL_MIN_SIZE", 1.5),
        ("CHECKPOINT_MONGO_POOL_MAX_SIZE", True),
    ],
)
async def test_set_rejects_invalid_mongodb_pool_sizes_before_persisting(
    key: str,
    value: object,
) -> None:
    from src.infra.settings.storage import SettingsStorage

    class _MustNotWriteCollection:
        async def update_one(self, *_args, **_kwargs):
            raise AssertionError("invalid pool setting must not be persisted")

    storage = SettingsStorage()
    storage._collection = _MustNotWriteCollection()

    with pytest.raises(ValueError, match="pool size"):
        await storage.set(key, value, "admin-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "value", "paired_key", "paired_value"),
    [
        ("MONGODB_POOL_MIN_SIZE", 21, "MONGODB_POOL_MAX_SIZE", 20),
        ("MONGODB_POOL_MAX_SIZE", 1, "MONGODB_POOL_MIN_SIZE", 2),
        (
            "CHECKPOINT_MONGO_POOL_MIN_SIZE",
            11,
            "CHECKPOINT_MONGO_POOL_MAX_SIZE",
            10,
        ),
        (
            "CHECKPOINT_MONGO_POOL_MAX_SIZE",
            1,
            "CHECKPOINT_MONGO_POOL_MIN_SIZE",
            2,
        ),
    ],
)
async def test_set_rejects_inverted_mongodb_pool_ranges(
    key: str,
    value: int,
    paired_key: str,
    paired_value: int,
) -> None:
    from src.infra.settings.storage import SettingsStorage

    collection = _SettingsWriteCollection({paired_key: paired_value})
    storage = SettingsStorage()
    storage._collection = collection

    with pytest.raises(ValueError, match="must not exceed|must be at least"):
        await storage.set(key, value, "admin-1")

    assert key not in collection.docs


@pytest.mark.asyncio
async def test_set_validates_pool_pair_against_persisted_effective_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.settings import storage as storage_module

    collection = _SettingsWriteCollection({"MONGODB_POOL_MAX_SIZE": 50})
    storage = storage_module.SettingsStorage()
    storage._collection = collection
    monkeypatch.setattr(storage_module.settings, "MONGODB_POOL_MAX_SIZE", 20)

    await storage.set("MONGODB_POOL_MIN_SIZE", 30, "admin-1")

    assert collection.docs["MONGODB_POOL_MIN_SIZE"]["value"] == 30


@pytest.mark.asyncio
async def test_pool_writes_are_serialized_across_storage_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.settings import storage as storage_module

    collection = _SettingsWriteCollection({"MONGODB_POOL_MIN_SIZE": 5, "MONGODB_POOL_MAX_SIZE": 20})
    first = storage_module.SettingsStorage()
    second = storage_module.SettingsStorage()
    first._collection = collection
    second._collection = collection
    monkeypatch.setattr(storage_module.settings, "MONGODB_POOL_MIN_SIZE", 5)
    monkeypatch.setattr(storage_module.settings, "MONGODB_POOL_MAX_SIZE", 20)

    outcomes = await asyncio.gather(
        first.set("MONGODB_POOL_MIN_SIZE", 15, "admin-1"),
        second.set("MONGODB_POOL_MAX_SIZE", 10, "admin-2"),
        return_exceptions=True,
    )

    assert sum(isinstance(outcome, ValueError) for outcome in outcomes) == 1
    pair = collection.docs["__settings_atomic__:mongodb_pool:business"]
    assert pair["min"] <= pair["max"]


@pytest.mark.asyncio
async def test_reset_rejects_default_that_would_invert_persisted_pool_pair() -> None:
    from src.infra.settings.storage import SettingsStorage

    collection = _SettingsWriteCollection(
        {"MONGODB_POOL_MIN_SIZE": 30, "MONGODB_POOL_MAX_SIZE": 50}
    )
    storage = SettingsStorage()
    storage._collection = collection

    with pytest.raises(ValueError, match="must be at least"):
        await storage.reset("MONGODB_POOL_MAX_SIZE")

    assert collection.docs["MONGODB_POOL_MAX_SIZE"]["value"] == 50
    assert "MONGODB_POOL_MAX_SIZE" not in collection.deleted_keys


@pytest.mark.asyncio
async def test_reset_all_serializes_with_concurrent_pool_write() -> None:
    class _ResetRaceCollection(_SettingsWriteCollection):
        def __init__(self) -> None:
            super().__init__({"MONGODB_POOL_MIN_SIZE": 30, "MONGODB_POOL_MAX_SIZE": 50})
            self.pair_read_started = asyncio.Event()
            self.allow_pair_read = asyncio.Event()

        async def find_one(self, query, projection=None):
            if query["_id"] == "MONGODB_POOL_MAX_SIZE" and not self.pair_read_started.is_set():
                doc = await super().find_one(query, projection)
                self.pair_read_started.set()
                await self.allow_pair_read.wait()
                return doc
            return await super().find_one(query, projection)

    from src.infra.settings.storage import SettingsStorage

    collection = _ResetRaceCollection()
    writer = SettingsStorage()
    resetter = SettingsStorage()
    writer._collection = collection
    resetter._collection = collection

    write_task = asyncio.create_task(writer.set("MONGODB_POOL_MIN_SIZE", 40, "admin-1"))
    await collection.pair_read_started.wait()
    reset_task = asyncio.create_task(resetter.reset())
    await asyncio.sleep(0.01)
    collection.allow_pair_read.set()
    await asyncio.gather(write_task, reset_task, return_exceptions=True)

    pair = collection.docs["__settings_atomic__:mongodb_pool:business"]
    assert pair["min"] <= pair["max"]


@pytest.mark.asyncio
async def test_settings_service_get_offloads_env_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.settings import service as service_module
    from src.infra.settings.service import SettingsService

    inside_blocking_io = False

    class _NoDbSettingStorage:
        async def get(self, _key: str) -> None:
            return None

    async def fake_run_blocking_io(func, /, *args: Any, **kwargs: Any) -> Any:
        nonlocal inside_blocking_io
        assert inside_blocking_io is False
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    def fake_json_loads(value: str) -> dict[str, Any]:
        assert inside_blocking_io, "JSON environment setting parsing must be offloaded"
        assert value == '{"en":[]}'
        return {"en": []}

    monkeypatch.setenv("WELCOME_SUGGESTIONS", '{"en":[]}')
    monkeypatch.setattr(service_module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(service_module.json, "loads", fake_json_loads)

    settings_service = SettingsService()
    settings_service._storage = _NoDbSettingStorage()  # type: ignore[assignment]

    value = await settings_service.get("WELCOME_SUGGESTIONS")

    assert value == {"en": []}
