"""Hot-path authorization shares storage initialization, never authorization decisions."""

import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api import main
from src.infra.logging.context import TraceContext
from src.infra.upload import access, file_record, shared_files
from src.kernel.errors import AppError


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield dict(row)

        return iterate()


@pytest.fixture
def database(monkeypatch):
    record = {"_id": "id", "key": "image/owner/a.png", "uploaded_by": "owner"}
    instances = []
    initialize = file_record.FileRecordStorage.__init__

    def track_initialization(storage):
        initialize(storage)
        instances.append(storage)

    async def find_one(query):
        return dict(record)

    collection = SimpleNamespace(
        create_index=AsyncMock(),
        list_indexes=AsyncMock(return_value=Cursor([])),
        find_one=AsyncMock(side_effect=find_one),
        find=lambda query, *args: Cursor([{**record, "key": key} for key in query["key"]["$in"]]),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(file_record, "_file_record_storage", None, raising=False)
    monkeypatch.setattr(file_record.FileRecordStorage, "__init__", track_initialization)
    monkeypatch.setattr(
        file_record.FileRecordStorage, "collection", property(lambda storage: collection)
    )
    TraceContext.clear_request_context()
    yield SimpleNamespace(record=record, instances=instances, collection=collection)
    TraceContext.clear_request_context()


async def drain_indexes(database):
    await asyncio.gather(
        *(storage._indexes_task for storage in database.instances if storage._indexes_task)
    )


async def test_download_share_and_generated_registration_initialize_indexes_once(
    database, monkeypatch
):
    from src.infra.storage.s3.service import S3StorageService
    from src.infra.storage.s3.types import UploadResult

    service = S3StorageService()
    result = UploadResult(
        key="revealed_files/owned.png",
        url="/api/upload/file/revealed_files/owned.png",
        size=3,
        content_type="image/png",
    )
    monkeypatch.setattr(
        service, "_get_backend", lambda: SimpleNamespace(upload=AsyncMock(return_value=result))
    )
    TraceContext.set_request_context(user_id="owner", session_id="session")
    for _ in range(2):
        await access.require_file_access(database.record["key"], "owner")
        assert await shared_files.owned_file_keys({database.record["key"]}, "owner") == {
            database.record["key"]
        }
        await service.upload_file(BytesIO(b"abc"), "revealed_files", "owned.png")
    await drain_indexes(database)
    assert len(database.instances) == 1
    assert database.collection.create_index.await_count == 4
    assert database.collection.update_one.await_count == 2

    database.record["deleting_at"] = "revoked"
    with pytest.raises(AppError):
        await access.require_file_access(database.record["key"], "owner")
    assert database.collection.find_one.await_count == 3


async def test_startup_initialized_storage_is_reused_by_later_access(database):
    await dict(main._startup_index_initializers())["file_record_storage"]()
    await access.require_file_access(database.record["key"], "owner")
    await access.require_file_access(database.record["key"], "owner")
    await drain_indexes(database)
    assert len(database.instances) == 1
    assert database.collection.create_index.await_count == 4
