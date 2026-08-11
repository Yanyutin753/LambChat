from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.routes import upload


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
async def test_live_owner_dedupe_refreshes_its_cleanup_grace_period(
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
            return True

    class _Objects:
        async def file_exists(self, key: str) -> bool:
            assert key == "docs/owner-a/draft.txt"
            return True

    records = _Records()
    monkeypatch.setattr(upload, "_file_record_storage", records)

    assert await upload._get_live_record_by_hash("same-content", "owner-a", _Objects()) == {
        "key": "docs/owner-a/draft.txt"
    }
    assert records.refreshed == [("docs/owner-a/draft.txt", "owner-a")]


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

    with pytest.raises(HTTPException) as exc_info:
        await upload.delete_file("docs/owner-b/private.txt", SimpleNamespace(sub="owner-a"))

    assert exc_info.value.status_code == 404


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
