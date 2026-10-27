import copy

import pytest

from src.infra.storage.s3.cutover import StorageGate


class Collection:
    def __init__(self):
        self.doc = {
            "_id": "__settings_atomic__:storage",
            "identity": "old",
            "revision": 0,
            "writers": [],
        }

    async def find_one_and_update(self, query, update, **kwargs):
        if any(self.doc.get(k) != v for k, v in query.items()):
            return None
        self.doc.update(copy.deepcopy(update.get("$set", {})))
        for key, value in update.get("$inc", {}).items():
            self.doc[key] += value
        for key, value in update.get("$push", {}).items():
            self.doc[key].append(value)
        return copy.deepcopy(self.doc)

    async def update_one(self, query, update):
        assert query["_id"] == self.doc["_id"]
        for key, value in update.get("$pull", {}).items():
            self.doc[key].remove(value)


async def test_upload_during_verification_invalidates_cutover_even_after_upload_finishes():
    collection = Collection()
    gate = StorageGate(collection)
    snapshot = copy.deepcopy(collection.doc)
    async with gate.write("old"):
        pass
    with pytest.raises(ValueError, match="changed"):
        await gate.commit(snapshot, {"S3_BUCKET_NAME": "new"}, "new", "admin", {})
    assert collection.doc["identity"] == "old"


async def test_active_upload_prevents_cutover_and_cancellation_releases_writer():
    collection = Collection()
    gate = StorageGate(collection)
    snapshot = copy.deepcopy(collection.doc)
    with pytest.raises(RuntimeError):
        async with gate.write("old"):
            with pytest.raises(ValueError):
                await gate.commit(snapshot, {}, "new", "admin", {})
            raise RuntimeError("cancel upload")
    assert collection.doc["writers"] == []


async def test_atomic_cutover_rejects_stale_replica_writes():
    collection = Collection()
    gate = StorageGate(collection)
    await gate.commit(
        copy.deepcopy(collection.doc), {"S3_BUCKET_NAME": "new"}, "new", "admin", {"objects": 3}
    )
    with pytest.raises(ValueError, match="changed"):
        async with gate.write("old"):
            pytest.fail("stale replica wrote to old bucket")
    async with gate.write("new"):
        assert collection.doc["values"] == {"S3_BUCKET_NAME": "new"}


async def test_failed_verification_cannot_change_configuration():
    # Commit requires the exact revision used by verification, not a fresh snapshot.
    collection = Collection()
    gate = StorageGate(collection)
    snapshot = copy.deepcopy(collection.doc)
    collection.doc["revision"] = 2
    with pytest.raises(ValueError):
        await gate.commit(snapshot, {}, "new", "admin", {})
    assert "values" not in collection.doc


async def test_cancelled_sdk_write_keeps_fence_until_operator_confirms_worker_stopped():
    import asyncio

    collection = Collection()
    gate = StorageGate(collection)
    with pytest.raises(asyncio.CancelledError):
        async with gate.write("old"):
            # Cancelling an await does not stop a blocking SDK upload thread.
            raise asyncio.CancelledError
    assert len(collection.doc["writers"]) == 1
    with pytest.raises(ValueError):
        await gate.commit(copy.deepcopy(collection.doc), {}, "new", "admin", {})


async def test_configuration_reload_does_not_retarget_inflight_service(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from src.infra.settings import storage_migration as migration
    from src.infra.storage.s3 import service

    old_values = {
        **migration.runtime_values(),
        "S3_ENABLED": False,
        "LOCAL_STORAGE_PATH": str(tmp_path / "old"),
    }
    new_values = {**old_values, "LOCAL_STORAGE_PATH": str(tmp_path / "new")}
    old = service.S3StorageService(migration.make_config(old_values), managed=True)
    monkeypatch.setattr(service, "_storage_service", old)
    monkeypatch.setattr(migration, "ensure_state", AsyncMock(return_value={"values": new_values}))
    new = await service.get_or_init_storage()
    assert new is not old
    assert old._config.storage_path == str(tmp_path / "old")
    assert new._config.storage_path == str(tmp_path / "new")


async def test_cancelled_request_keeps_sdk_write_fenced_until_it_finishes(monkeypatch):
    import asyncio

    from src.infra.settings import storage_migration as migration
    from src.infra.storage.s3.cutover import storage_write

    collection = Collection()
    started, finish, completed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(migration, "collection", lambda: collection)
    monkeypatch.setattr(migration, "config_identity", lambda config: "old")

    async def ensure():
        return collection.doc

    monkeypatch.setattr(migration, "ensure_state", ensure)

    class Storage:
        _managed = True
        _config = object()

        @storage_write
        async def upload(self):
            started.set()
            await finish.wait()
            completed.set()

    task = asyncio.create_task(Storage().upload())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert collection.doc["writers"]
    finish.set()
    # Let the protected operation and its cleanup callbacks run.
    for _ in range(20):
        await asyncio.sleep(0)
    assert completed.is_set()
    assert collection.doc["writers"] == []
