from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from src.infra.share.storage import ShareStorage
from src.kernel.schemas.share import ShareType, ShareVisibility


class _FakeShareCollection:
    def __init__(self, doc: dict) -> None:
        self.doc = doc

    async def find_one(self, query: dict):
        assert query == {"share_id": "legacy-share"}
        return dict(self.doc)


class _FakeUpdateShareCollection:
    def __init__(self, doc: dict) -> None:
        self.doc = dict(doc)
        self.update_query: dict | None = None
        self.update_payload: dict | None = None

    async def find_one(self, query: dict):
        return dict(self.doc)

    async def update_one(self, query: dict, payload: dict):
        self.update_query = query
        self.update_payload = payload
        self.doc.update(payload["$set"])

        class _Result:
            matched_count = 1
            modified_count = 1

        return _Result()


@pytest.mark.asyncio
async def test_get_by_share_id_defaults_legacy_share_fields() -> None:
    created_at = datetime(2026, 4, 25, tzinfo=timezone.utc)
    storage = ShareStorage()
    storage._collection = _FakeShareCollection(
        {
            "_id": ObjectId(),
            "share_id": "legacy-share",
            "session_id": "session-1",
            "owner_id": "owner-1",
            "created_at": created_at,
        }
    )

    share = await storage.get_by_share_id("legacy-share")

    assert share is not None
    assert share.share_type == ShareType.FULL
    assert share.visibility == ShareVisibility.PUBLIC
    assert share.run_ids is None
    assert share.updated_at == created_at
    assert share.allow_files is False


@pytest.mark.asyncio
async def test_update_changes_share_settings_without_changing_public_id() -> None:
    created_at = datetime(2026, 4, 25, tzinfo=timezone.utc)
    share_db_id = ObjectId()
    collection = _FakeUpdateShareCollection(
        {
            "_id": share_db_id,
            "share_id": "stable-share",
            "session_id": "session-1",
            "owner_id": "owner-1",
            "share_type": "full",
            "run_ids": None,
            "visibility": "public",
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    storage = ShareStorage()
    storage._collection = collection

    share = await storage.update(
        str(share_db_id),
        owner_id="owner-1",
        share_type=ShareType.PARTIAL,
        run_ids=["run-1", "run-2"],
        visibility=ShareVisibility.AUTHENTICATED,
    )

    assert share is not None
    assert share.share_id == "stable-share"
    assert share.share_type == ShareType.PARTIAL
    assert share.run_ids == ["run-1", "run-2"]
    assert share.visibility == ShareVisibility.AUTHENTICATED
    assert share.updated_at > created_at
    assert collection.update_query == {"_id": share_db_id, "owner_id": "owner-1"}


@pytest.mark.parametrize("allow_files", [False, True])
async def test_file_consent_round_trips_create_list_and_update(allow_files):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.kernel.schemas.share import ShareCreate

    storage = ShareStorage()
    created_id = ObjectId()
    insert = AsyncMock(return_value=SimpleNamespace(inserted_id=created_id))
    storage._collection = SimpleNamespace(insert_one=insert)
    created = await storage.create(
        ShareCreate(session_id="session-1", allow_files=allow_files), "owner-1"
    )
    doc = {**insert.call_args.args[0], "_id": created_id}
    assert doc["allow_files"] is allow_files
    assert created.allow_files is allow_files
    assert storage._build_shared_session(doc).allow_files is allow_files
    assert storage._build_list_item(doc).allow_files is allow_files

    collection = _FakeUpdateShareCollection(doc)
    storage._collection = collection
    updated = await storage.update(
        str(created_id),
        owner_id="owner-1",
        share_type=ShareType.FULL,
        run_ids=None,
        visibility=ShareVisibility.PUBLIC,
        allow_files=not allow_files,
    )
    assert updated.allow_files is not allow_files
    assert updated.updated_at > created.updated_at
    await storage.update(
        str(created_id),
        owner_id="owner-1",
        share_type=ShareType.FULL,
        run_ids=None,
        visibility=ShareVisibility.AUTHENTICATED,
    )
    assert collection.doc["allow_files"] is not allow_files
