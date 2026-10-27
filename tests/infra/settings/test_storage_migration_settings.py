import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.settings import storage_migration as migration
from src.infra.storage.s3.cutover import StorageGate
from src.kernel.errors import AppError, ErrorCode


class Cursor:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class Store:
    def __init__(self, source):
        values = {
            **migration.runtime_values(),
            "S3_ENABLED": False,
            "LOCAL_STORAGE_PATH": str(source),
        }
        self.doc = {
            "_id": migration.STORAGE_STATE_ID,
            "values": values,
            "identity": migration.config_identity(migration.make_config(values)),
            "revision": 0,
            "writers": [],
        }
        records = SimpleNamespace(find=lambda *a, **kw: Cursor())
        self.database = SimpleNamespace(
            direct_uploads=SimpleNamespace(find_one=AsyncMock(return_value=None)),
            file_records=records,
            revealed_files=records,
        )

    async def find_one(self, query):
        return copy.deepcopy(self.doc)

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
        for key, value in update.get("$pull", {}).items():
            self.doc[key].remove(value)


async def test_missing_destination_file_never_changes_active_config(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "keep.txt").write_text("original")
    store = Store(source)
    before = copy.deepcopy(store.doc)
    with pytest.raises(AppError) as error:
        await migration.change_storage(
            {"LOCAL_STORAGE_PATH": str(tmp_path / "target")}, "admin", store
        )
    assert error.value.error_code == ErrorCode.STORAGE_MIGRATION_BLOCKED
    assert store.doc == before


async def test_verified_local_migration_commits_one_bundle(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    for directory in (source, target):
        directory.mkdir()
        (directory / "keep.txt").write_text("original")
    store = Store(source)
    updated = await migration.change_storage({"LOCAL_STORAGE_PATH": str(target)}, "admin", store)
    assert updated["values"]["LOCAL_STORAGE_PATH"] == str(target)
    assert updated["verification"] == {"objects": 1, "bytes": 8}
    assert (source / "keep.txt").read_text() == "original"


async def test_write_during_actual_verification_refuses_cutover(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    store = Store(source)
    verify = migration.verify_contents

    async def while_uploading(*args):
        async with StorageGate(store).write(store.doc["identity"]):
            (source / "late.txt").write_text("late upload")
        return await verify(*args)

    monkeypatch.setattr(migration, "verify_contents", while_uploading)
    with pytest.raises(AppError):
        await migration.change_storage({"LOCAL_STORAGE_PATH": str(target)}, "admin", store)
    assert store.doc["values"]["LOCAL_STORAGE_PATH"] == str(source)


async def test_active_multipart_ticket_blocks_verification_before_reading_files(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "source")
    store.database.direct_uploads.find_one.return_value = {"state": "active"}
    verify = AsyncMock()
    monkeypatch.setattr(migration, "verify_contents", verify)
    with pytest.raises(AppError) as error:
        await migration.change_storage(
            {"LOCAL_STORAGE_PATH": str(tmp_path / "target")}, "admin", store
        )
    assert error.value.error_code == ErrorCode.STORAGE_MIGRATION_BUSY
    verify.assert_not_awaited()


async def test_bootstrap_rejects_unverified_environment_before_loading_services(monkeypatch):
    from src.kernel.config import service as config

    values = migration.runtime_values()
    boot = migration.config_identity(migration.make_config(values))
    monkeypatch.setattr(
        migration,
        "ensure_state",
        AsyncMock(
            return_value={
                "boot_identity": "different",
                "identity": "another",
                "values": values,
            }
        ),
    )
    initialize = AsyncMock()
    monkeypatch.setattr("src.infra.settings.service.SettingsService.initialize", initialize)
    with pytest.raises(ValueError, match="Unverified storage"):
        await config.initialize_settings()
    initialize.assert_not_awaited()
    assert boot not in {"different", "another"}


async def test_read_only_destination_cannot_be_activated(tmp_path, monkeypatch):
    from src.infra.storage.s3.backends.local import LocalStorageBackend

    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    store = Store(source)
    monkeypatch.setattr(LocalStorageBackend, "upload_bytes", AsyncMock(side_effect=PermissionError))
    with pytest.raises(AppError):
        await migration.change_storage({"LOCAL_STORAGE_PATH": str(target)}, "admin", store)
    assert store.doc["values"]["LOCAL_STORAGE_PATH"] == str(source)


@pytest.mark.parametrize("operation", ["set", "reset", "reset_all"])
async def test_all_settings_mutation_paths_use_migration_gate(operation, monkeypatch):
    from src.infra.settings import storage as storage_module

    storage = storage_module.SettingsStorage()
    storage._collection = object()
    gate = AsyncMock(side_effect=AppError(ErrorCode.STORAGE_MIGRATION_BLOCKED))
    monkeypatch.setattr(storage_module, "change_storage", gate)
    with pytest.raises(AppError):
        if operation == "set":
            await storage.set("S3_BUCKET_NAME", "new", "admin")
        else:
            await storage.reset("S3_BUCKET_NAME" if operation == "reset" else None)
    assert gate.await_count == 1
    assert "S3_BUCKET_NAME" in gate.call_args.args[0]


async def test_verified_active_storage_overrides_old_boot_environment(monkeypatch):
    from src.kernel.config import service as config

    values = migration.runtime_values()
    identity = migration.config_identity(migration.make_config(values))
    active = {**values, "S3_ENABLED": False, "LOCAL_STORAGE_PATH": "/verified/active"}
    monkeypatch.setattr(
        migration,
        "ensure_state",
        AsyncMock(
            return_value={
                "boot_identity": identity,
                "identity": migration.config_identity(migration.make_config(active)),
                "values": active,
            }
        ),
    )
    service = SimpleNamespace(initialize=AsyncMock(), get_all=AsyncMock(return_value={}))
    monkeypatch.setattr("src.infra.settings.service.SettingsService.get_instance", lambda: service)
    monkeypatch.setattr(config, "_settings_service", None)
    monkeypatch.setattr(config, "_settings_cache", {})
    for key, value in values.items():
        monkeypatch.setattr(config.settings, key, value)
    monkeypatch.setattr(config.settings, "_vapid_keys_generated", False)
    await config.initialize_settings()
    assert config.settings.LOCAL_STORAGE_PATH == "/verified/active"
    assert config._settings_cache["LOCAL_STORAGE_PATH"] == "/verified/active"
