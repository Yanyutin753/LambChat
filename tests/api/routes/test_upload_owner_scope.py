from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.routes import upload
from src.kernel.errors import AppError


@pytest.mark.asyncio
async def test_live_hash_lookup_and_stale_cleanup_are_limited_to_the_current_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Records:
        def __init__(self) -> None:
            self.find_calls: list[tuple[str, str]] = []
            self.delete_calls: list[tuple[str, str]] = []

        async def find_by_hash(self, file_hash: str, uploaded_by: str):
            self.find_calls.append((file_hash, uploaded_by))
            return {"key": "docs/owner-a/missing.txt"}

        async def delete_by_hash(self, file_hash: str, uploaded_by: str):
            self.delete_calls.append((file_hash, uploaded_by))
            return True

    class _Objects:
        async def file_exists(self, _key: str) -> bool:
            return False

    records = _Records()
    monkeypatch.setattr(upload, "_file_record_storage", records)

    result = await upload._get_live_record_by_hash("same-content", "owner-a", _Objects())

    assert result is None
    assert records.find_calls == [("same-content", "owner-a")]
    assert records.delete_calls == [("same-content", "owner-a")]


@pytest.mark.asyncio
async def test_live_owner_dedupe_rejects_record_when_atomic_cleanup_refresh_loses_tombstone_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Records:
        def __init__(self) -> None:
            self.refreshed: list[tuple[str, str]] = []

        async def find_by_hash(self, file_hash: str, uploaded_by: str):
            assert (file_hash, uploaded_by) == ("same-content", "owner-a")
            return {"key": "docs/owner-a/draft.txt"}

        async def refresh_owned_cleanup(self, key: str, uploaded_by: str) -> bool:
            self.refreshed.append((key, uploaded_by))
            return False

    class _Objects:
        async def file_exists(self, key: str) -> bool:
            assert key == "docs/owner-a/draft.txt"
            return True

    records = _Records()
    monkeypatch.setattr(upload, "_file_record_storage", records)

    assert await upload._get_live_record_by_hash("same-content", "owner-a", _Objects()) is None
    assert records.refreshed == [("docs/owner-a/draft.txt", "owner-a")]


@pytest.mark.asyncio
async def test_duplicate_upload_conflict_removes_new_object_when_conflicting_record_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Upload:
        filename = "note.txt"
        content_type = "text/plain"

        def __init__(self) -> None:
            self._chunks = [b"contents", b""]

        async def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

    class _Records:
        def __init__(self) -> None:
            self.find_attempts = 0
            self.deleted_hashes: list[tuple[str, str]] = []

        async def find_by_hash(self, file_hash: str, uploaded_by: str):
            assert uploaded_by == "owner-a"
            self.find_attempts += 1
            if self.find_attempts == 1:
                return None
            return {"key": "documents/owner-a/stale.txt"}

        async def create(self, **_kwargs):
            from pymongo.errors import DuplicateKeyError

            raise DuplicateKeyError(
                "duplicate hash",
                11000,
                {"keyPattern": {"uploaded_by": 1, "hash": 1}},
            )

        async def delete_by_hash(self, file_hash: str, uploaded_by: str):
            self.deleted_hashes.append((file_hash, uploaded_by))
            return True

    class _Objects:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def file_exists(self, key: str) -> bool:
            return key != "documents/owner-a/stale.txt"

        async def upload_stream_to_key(self, **_kwargs):
            return SimpleNamespace(key="documents/owner-a/new.txt")

        async def delete_file(self, key: str) -> None:
            self.deleted.append(key)

    objects = _Objects()
    monkeypatch.setattr(upload, "_file_record_storage", _Records())

    async def _get_storage():
        return objects

    monkeypatch.setattr(upload, "get_or_init_storage", _get_storage)

    with pytest.raises(AppError) as exc_info:
        await upload.upload_file(
            request=SimpleNamespace(headers={}, base_url="https://app.example.com/"),
            file=_Upload(),
            current_user=SimpleNamespace(sub="owner-a", permissions=["file:upload"], roles=[]),
        )

    assert exc_info.value.error_code.code == "upload_duplicate_conflict"
    assert exc_info.value.http_status == 409
    assert objects.deleted == ["documents/owner-a/new.txt"]


@pytest.mark.asyncio
async def test_duplicate_key_index_collision_never_deletes_existing_object_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Upload:
        filename = "note.txt"
        content_type = "text/plain"

        def __init__(self) -> None:
            self._chunks = [b"contents", b""]

        async def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

    class _Records:
        async def find_by_hash(self, _file_hash: str, _uploaded_by: str):
            return None

        async def create(self, **_kwargs):
            from pymongo.errors import DuplicateKeyError

            raise DuplicateKeyError("duplicate key", 11000, {"keyPattern": {"key": 1}})

    class _Objects:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def upload_stream_to_key(self, **_kwargs):
            return SimpleNamespace(key="documents/owner-a/existing.txt")

        async def delete_file(self, key: str) -> None:
            self.deleted.append(key)

    objects = _Objects()
    monkeypatch.setattr(upload, "_file_record_storage", _Records())

    async def _get_storage():
        return objects

    monkeypatch.setattr(upload, "get_or_init_storage", _get_storage)

    with pytest.raises(AppError) as exc_info:
        await upload.upload_file(
            request=SimpleNamespace(headers={}, base_url="https://app.example.com/"),
            file=_Upload(),
            current_user=SimpleNamespace(sub="owner-a", permissions=["file:upload"], roles=[]),
        )

    assert exc_info.value.error_code.code == "upload_duplicate_conflict"
    assert exc_info.value.http_status == 409
    assert objects.deleted == []


@pytest.mark.asyncio
async def test_delete_rejects_unknown_or_foreign_key_without_touching_object_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Records:
        async def find_by_key(self, key: str, uploaded_by: str):
            assert (key, uploaded_by) == ("docs/owner-b/private.txt", "owner-a")
            return None

    class _Objects:
        async def delete_file(self, _key: str) -> None:
            raise AssertionError("foreign object storage must never be deleted")

    async def _storage():
        return _Objects()

    monkeypatch.setattr(upload, "_file_record_storage", _Records())
    monkeypatch.setattr(upload, "get_or_init_storage", _storage)

    with pytest.raises(AppError) as exc_info:
        await upload.delete_file("docs/owner-b/private.txt", SimpleNamespace(sub="owner-a"))

    assert exc_info.value.error_code.code == "file_not_found"
    assert exc_info.value.http_status == 404


@pytest.mark.asyncio
async def test_delete_schedules_owned_zero_reference_cleanup_without_deleting_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Records:
        async def find_by_key(self, key: str, uploaded_by: str):
            assert (key, uploaded_by) == ("docs/owner-a/draft.txt", "owner-a")
            return {"key": key, "reference_count": 0}

        async def schedule_owned_cleanup(self, key: str, uploaded_by: str) -> bool:
            assert (key, uploaded_by) == ("docs/owner-a/draft.txt", "owner-a")
            return True

    class _Objects:
        async def delete_file(self, _key: str) -> None:
            raise AssertionError("cleanup grace period must defer object deletion")

    async def _storage():
        return _Objects()

    monkeypatch.setattr(upload, "_file_record_storage", _Records())
    monkeypatch.setattr(upload, "get_or_init_storage", _storage)

    result = await upload.delete_file("docs/owner-a/draft.txt", SimpleNamespace(sub="owner-a"))

    assert result == {
        "deleted": False,
        "key": "docs/owner-a/draft.txt",
        "status": "scheduled",
    }
