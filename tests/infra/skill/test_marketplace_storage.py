from __future__ import annotations

from typing import Any

import pytest

from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.types import MarketplaceSkillResponse


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return doc


class _FakeMarketplaceCollection:
    def __init__(self) -> None:
        self.pipeline: list[dict[str, Any]] | None = None

    def aggregate(self, pipeline: list[dict[str, Any]]) -> _AsyncCursor:
        self.pipeline = pipeline
        return _AsyncCursor(
            [
                {
                    "skill_name": "planner",
                    "description": "Plan work",
                    "tags": ["planning"],
                    "created_by": "user-1",
                    "is_active": True,
                    "_file_count": 3,
                }
            ]
        )


class _PublishedSkillsCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.cursor = _FindCursor(docs)
        self.find_calls: list[tuple[dict[str, Any], dict[str, int] | None]] = []

    def find(self, query: dict[str, Any], projection: dict[str, int] | None = None):
        self.find_calls.append((query, projection))
        return self.cursor


@pytest.mark.asyncio
async def test_list_marketplace_skills_counts_files_without_loading_file_contents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeMarketplaceCollection()
    storage = MarketplaceStorage()
    monkeypatch.setattr(storage, "_get_meta_collection", lambda: collection)

    async def _fake_batch_get_usernames(user_ids: list[str]) -> dict[str, str]:
        assert user_ids == ["user-1"]
        return {"user-1": "tester"}

    monkeypatch.setattr(storage, "_batch_get_usernames", _fake_batch_get_usernames)

    result = await storage.list_marketplace_skills(skip=20, limit=10, viewer_id="user-1")

    assert result[0].file_count == 3
    assert result[0].skill_name == "planner"
    assert result[0].extension_type == "skill"
    assert result[0].extension_id == "skill:planner"
    assert result[0].extension is not None
    assert result[0].extension.id == "skill:planner"
    assert result[0].extension.type == "skill"
    assert result[0].extension.legacy["skill_name"] == "planner"
    assert result[0].extension.legacy["file_count"] == 3
    assert collection.pipeline is not None
    stages = collection.pipeline
    lookup_index = next(i for i, stage in enumerate(stages) if "$lookup" in stage)
    skip_index = next(i for i, stage in enumerate(stages) if stage == {"$skip": 20})
    limit_index = next(i for i, stage in enumerate(stages) if stage == {"$limit": 10})
    assert skip_index < lookup_index
    assert limit_index < lookup_index
    lookup = stages[lookup_index]["$lookup"]
    assert "pipeline" in lookup
    assert lookup["pipeline"][-1] == {"$count": "count"}
    assert "as" in lookup
    assert lookup["as"] != "_files"


def test_marketplace_skill_response_keeps_legacy_fields_and_adds_extension_entry() -> None:
    response = MarketplaceSkillResponse(
        skill_name="planner",
        description="Plan work",
        tags=["planning"],
        version="2.0.0",
        created_by="user-1",
        created_by_username="tester",
        is_active=True,
        is_owner=True,
        file_count=4,
    )

    assert response.skill_name == "planner"
    assert response.description == "Plan work"
    assert response.tags == ["planning"]
    assert response.version == "2.0.0"
    assert response.is_owner is True
    assert response.file_count == 4
    assert response.extension_type == "skill"
    assert response.extension_id == "skill:planner"
    assert response.extension is not None
    assert response.extension.name == "planner"
    assert response.extension.publisher == "tester"
    assert response.extension.capabilities == ["skill"]
    assert response.extension.legacy == {
        "kind": "marketplace_skill",
        "skill_name": "planner",
        "file_count": 4,
    }


@pytest.mark.asyncio
async def test_marketplace_storage_close_clears_local_client_reference() -> None:
    storage = MarketplaceStorage()
    storage._client = object()
    storage._meta_collection = object()
    storage._files_collection = object()
    storage._users_collection = object()

    await storage.close()

    assert storage._client is None
    assert storage._meta_collection is None
    assert storage._files_collection is None
    assert storage._users_collection is None


@pytest.mark.asyncio
async def test_list_marketplace_skills_escapes_search_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeMarketplaceCollection()
    storage = MarketplaceStorage()
    monkeypatch.setattr(storage, "_get_meta_collection", lambda: collection)

    async def _fake_batch_get_usernames(user_ids: list[str]) -> dict[str, str]:
        return {}

    monkeypatch.setattr(storage, "_batch_get_usernames", _fake_batch_get_usernames)

    await storage.list_marketplace_skills(search="a+b(c)", include_inactive=True)

    assert collection.pipeline is not None
    match = collection.pipeline[0]["$match"]
    regex = match["$or"][0]["skill_name"]["$regex"]
    assert regex == r"a\+b\(c\)"


@pytest.mark.asyncio
async def test_get_user_published_skills_filters_to_requested_skill_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = MarketplaceStorage()
    collection = _PublishedSkillsCollection(
        [
            {"skill_name": "planner", "is_active": True},
            {"skill_name": "writer", "is_active": False},
        ]
    )
    monkeypatch.setattr(storage, "_get_meta_collection", lambda: collection)

    result = await storage.get_user_published_skills(
        "user-1",
        skill_names=["planner", "writer", "planner"],
    )

    assert result == {
        "planner": {"is_active": True},
        "writer": {"is_active": False},
    }
    assert collection.find_calls == [
        (
            {"created_by": "user-1", "skill_name": {"$in": ["planner", "writer"]}},
            {"skill_name": 1, "is_active": 1},
        )
    ]
    assert collection.cursor.limit_value == 2


class _FindCursor(_AsyncCursor):
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        super().__init__(docs)
        self.sort_calls: list[tuple[str, int]] = []
        self.batch_size_value: int | None = None
        self.limit_value: int | None = None

    def sort(self, key: str, direction: int):
        self.sort_calls.append((key, direction))
        return self

    def batch_size(self, value: int):
        self.batch_size_value = value
        return self

    def limit(self, value: int):
        self.limit_value = value
        self._docs = self._docs[:value]
        return self


class _FakeFilesCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.cursor = _FindCursor(docs)

    def find(self, query: dict[str, Any], projection: dict[str, int] | None = None):
        assert query == {"skill_name": "planner"}
        assert projection == {"_id": 0, "file_path": 1, "content": 1}
        return self.cursor


class _SyncShouldNotReadCollection:
    def find(self, *_args, **_kwargs):
        raise AssertionError("oversized marketplace sync should be rejected before reads")

    async def bulk_write(self, *_args, **_kwargs):
        raise AssertionError("oversized marketplace sync should be rejected before writes")


class _SyncNoReadCollection:
    def __init__(self) -> None:
        self.delete_many_calls: list[dict[str, Any]] = []
        self.bulk_operations: list[Any] = []

    def find(self, *_args, **_kwargs):
        raise AssertionError("sync should not materialize existing marketplace file paths")

    async def delete_many(self, query: dict[str, Any]):
        self.delete_many_calls.append(query)

    async def bulk_write(self, operations: list[Any], ordered: bool = True):
        assert ordered is True
        self.bulk_operations.extend(operations)


@pytest.mark.asyncio
async def test_iter_marketplace_files_batches_without_materializing_dict() -> None:
    storage = MarketplaceStorage()
    files = _FakeFilesCollection(
        [{"file_path": f"{index}.md", "content": f"content {index}"} for index in range(5)]
    )
    storage._files_collection = files

    batches = []
    async for batch in storage.iter_marketplace_file_batches("planner", batch_size=2):
        batches.append(batch)

    assert batches == [
        {"0.md": "content 0", "1.md": "content 1"},
        {"2.md": "content 2", "3.md": "content 3"},
        {"4.md": "content 4"},
    ]
    assert files.cursor.sort_calls == [("file_path", 1)]
    assert files.cursor.batch_size_value == 2


@pytest.mark.asyncio
async def test_iter_marketplace_files_batches_limits_total_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import marketplace as marketplace_module

    monkeypatch.setattr(
        marketplace_module,
        "MARKETPLACE_FILES_PER_SKILL_LIMIT",
        3,
        raising=False,
    )
    storage = MarketplaceStorage()
    files = _FakeFilesCollection(
        [{"file_path": f"{index}.md", "content": f"content {index}"} for index in range(5)]
    )
    storage._files_collection = files

    batches = []
    async for batch in storage.iter_marketplace_file_batches("planner", batch_size=2):
        batches.append(batch)

    assert batches == [
        {"0.md": "content 0", "1.md": "content 1"},
        {"2.md": "content 2"},
    ]
    assert files.cursor.limit_value == 3


class _FakePathFilesCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.cursor = _FindCursor(docs)

    def find(self, query: dict[str, Any], projection: dict[str, int] | None = None):
        assert query == {"skill_name": "planner"}
        assert projection == {"file_path": 1}
        return self.cursor


class _TagFilesCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.cursor = _FindCursor(docs)
        self.find_calls: list[tuple[dict[str, Any], dict[str, int]]] = []

    def find(self, query: dict[str, Any], projection: dict[str, int]):
        self.find_calls.append((query, projection))
        return self.cursor


@pytest.mark.asyncio
async def test_list_all_tags_limits_active_skill_scan_and_returned_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import marketplace as marketplace_module

    monkeypatch.setattr(marketplace_module, "MARKETPLACE_TAG_SCAN_LIMIT", 2, raising=False)
    monkeypatch.setattr(marketplace_module, "MARKETPLACE_TAG_LIST_LIMIT", 3, raising=False)
    storage = MarketplaceStorage()
    collection = _TagFilesCollection(
        [
            {"tags": ["z", "a"]},
            {"tags": ["b", "c"]},
            {"tags": ["should-not-scan"]},
        ]
    )
    monkeypatch.setattr(storage, "_get_meta_collection", lambda: collection)

    tags = await storage.list_all_tags()

    assert collection.find_calls == [({"is_active": {"$ne": False}}, {"tags": 1})]
    assert collection.cursor.limit_value == 2
    assert tags == ["a", "b", "z"]


@pytest.mark.asyncio
async def test_get_marketplace_files_limits_files_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import marketplace as marketplace_module

    monkeypatch.setattr(
        marketplace_module,
        "MARKETPLACE_FILES_PER_SKILL_LIMIT",
        3,
        raising=False,
    )
    storage = MarketplaceStorage()
    files = _FakeFilesCollection(
        [{"file_path": f"{index}.md", "content": f"content {index}"} for index in range(5)]
    )
    storage._files_collection = files

    loaded = await storage.get_marketplace_files("planner")

    assert loaded == {
        "0.md": "content 0",
        "1.md": "content 1",
        "2.md": "content 2",
    }
    assert files.cursor.limit_value == 3


@pytest.mark.asyncio
async def test_list_marketplace_file_paths_limits_files_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import marketplace as marketplace_module

    monkeypatch.setattr(
        marketplace_module,
        "MARKETPLACE_FILES_PER_SKILL_LIMIT",
        3,
        raising=False,
    )
    storage = MarketplaceStorage()
    files = _FakePathFilesCollection([{"file_path": f"{index}.md"} for index in range(5)])
    storage._files_collection = files

    paths = await storage.list_marketplace_file_paths("planner")

    assert paths == ["0.md", "1.md", "2.md"]
    assert files.cursor.limit_value == 3


@pytest.mark.asyncio
async def test_sync_marketplace_files_rejects_too_many_files_before_existing_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import marketplace as marketplace_module

    monkeypatch.setattr(
        marketplace_module,
        "MARKETPLACE_FILES_PER_SKILL_LIMIT",
        3,
        raising=False,
    )
    storage = MarketplaceStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: _SyncShouldNotReadCollection())

    with pytest.raises(ValueError, match="too many files"):
        await storage.sync_marketplace_files(
            "planner",
            {f"file-{index}.md": "content" for index in range(4)},
        )


@pytest.mark.asyncio
async def test_sync_marketplace_files_deletes_removed_paths_without_scanning_existing_files() -> (
    None
):
    storage = MarketplaceStorage()
    collection = _SyncNoReadCollection()
    storage._files_collection = collection

    await storage.sync_marketplace_files(
        "planner",
        {"SKILL.md": "content", "notes.md": "notes"},
    )

    assert collection.delete_many_calls == [
        {
            "skill_name": "planner",
            "file_path": {"$nin": ["SKILL.md", "notes.md"]},
        }
    ]
    assert len(collection.bulk_operations) == 2
