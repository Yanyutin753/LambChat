from __future__ import annotations

import json
from typing import Any

import pytest

from src.infra.skill import storage as skill_storage
from src.infra.skill.storage import SkillStorage
from src.infra.user import storage as user_storage


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


class _LimitableAsyncCursor(_AsyncCursor):
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        super().__init__(docs)
        self.limit_value: int | None = None

    def limit(self, value: int):
        self.limit_value = value
        self._docs = self._docs[:value]
        return self


class _FakeSkillFilesCollection:
    def __init__(self) -> None:
        self.aggregate_pipelines: list[list[dict[str, Any]]] = []

    def aggregate(self, pipeline: list[dict[str, Any]]) -> _AsyncCursor:
        self.aggregate_pipelines.append(pipeline)
        return _AsyncCursor(
            [
                {
                    "_id": "planner",
                    "file_count": 2,
                    "file_paths": ["SKILL.md", "notes.md"],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                }
            ]
        )

    def find(self, query: dict[str, Any], projection: dict[str, int]) -> _AsyncCursor:
        assert query == {
            "skill_name": {"$in": ["planner"]},
            "user_id": "user-1",
            "file_path": "__meta__",
        }
        assert projection == {"skill_name": 1, "content": 1}
        return _AsyncCursor(
            [
                {
                    "skill_name": "planner",
                    "content": json.dumps(
                        {
                            "installed_from": "manual",
                            "published_marketplace_name": "public-planner",
                        }
                    ),
                }
            ]
        )


@pytest.mark.asyncio
async def test_skill_storage_close_clears_local_client_reference() -> None:
    storage = SkillStorage()
    storage._client = object()
    storage._files_collection = object()

    await storage.close()

    assert storage._client is None
    assert storage._files_collection is None


class _FindOneMetaCollection:
    async def find_one(self, query: dict[str, Any]) -> dict[str, Any]:
        assert query == {
            "skill_name": "planner",
            "user_id": "user-1",
            "file_path": "__meta__",
        }
        return {
            "content": json.dumps(
                {
                    "installed_from": "manual",
                    "published_marketplace_name": "public-planner",
                }
            )
        }


class _FakeSkillMdCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.cursor: _LimitableAsyncCursor | None = None
        self.find_calls: list[tuple[dict[str, Any], dict[str, int]]] = []

    def aggregate(self, pipeline: list[dict[str, Any]]) -> _AsyncCursor:
        raise AssertionError(f"unexpected aggregate: {pipeline}")

    def find(self, query: dict[str, Any], projection: dict[str, int]) -> _LimitableAsyncCursor:
        self.find_calls.append((query, projection))
        self.cursor = _LimitableAsyncCursor(self.docs)
        return self.cursor


class _MatchingSkillCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.cursor: _LimitableAsyncCursor | None = None

    def find(self, query: dict[str, Any], projection: dict[str, int]) -> _LimitableAsyncCursor:
        assert query == {"user_id": "user-1", "file_path": "SKILL.md"}
        assert projection == {"skill_name": 1, "content": 1}
        self.cursor = _LimitableAsyncCursor(self.docs)
        return self.cursor


class _GeneralFindCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.cursors: list[_LimitableAsyncCursor] = []

    def find(
        self,
        query: dict[str, Any],
        projection: dict[str, int] | None = None,
    ) -> _LimitableAsyncCursor:
        del query, projection
        cursor = _LimitableAsyncCursor(self.docs)
        self.cursors.append(cursor)
        return cursor


class _FindOneSkillMdCollection:
    def __init__(self) -> None:
        self.find_one_calls: list[dict[str, Any]] = []

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        self.find_one_calls.append(query)
        if query.get("file_path") == {"$regex": r"^skill\.md$", "$options": "i"}:
            return {"content": "legacy lowercase content"}
        return None


class _SyncShouldNotReadCollection:
    def find(self, *_args, **_kwargs):
        raise AssertionError("oversized sync should be rejected before reading existing files")

    async def bulk_write(self, *_args, **_kwargs):
        raise AssertionError("oversized sync should be rejected before bulk write")


class _SyncRemovedBinaryCollection:
    def __init__(self) -> None:
        self.find_calls: list[tuple[dict[str, Any], dict[str, int]]] = []
        self.cursor = _LimitableAsyncCursor(
            [
                {
                    "content": json.dumps(
                        {
                            "_binary_ref": True,
                            "storage_key": "skills/user-1/planner/old.png",
                            "mime_type": "image/png",
                            "size": 12,
                        }
                    )
                }
            ]
        )
        self.delete_many_calls: list[dict[str, Any]] = []
        self.bulk_operations: list[Any] = []

    def find(self, query: dict[str, Any], projection: dict[str, int]) -> _LimitableAsyncCursor:
        self.find_calls.append((query, projection))
        return self.cursor

    async def delete_many(self, query: dict[str, Any]):
        self.delete_many_calls.append(query)

    async def bulk_write(self, operations: list[Any], ordered: bool = True):
        assert ordered is True
        self.bulk_operations.extend(operations)


class _PreferenceUserDoc:
    def __init__(self, metadata: dict[str, Any]) -> None:
        self.metadata = metadata


class _PreferenceUserStorage:
    def __init__(self, metadata: dict[str, Any]) -> None:
        self.metadata = metadata
        self.updates: list[tuple[str, dict[str, Any]]] = []

    async def get_by_id(self, user_id: str):
        assert user_id == "user-1"
        return _PreferenceUserDoc(self.metadata)

    async def update_metadata(self, user_id: str, metadata: dict[str, Any]):
        assert user_id == "user-1"
        self.updates.append((user_id, metadata))
        return None


@pytest.mark.asyncio
async def test_list_user_skills_without_filters_returns_paginated_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeSkillFilesCollection()
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    skills = await storage.list_user_skills(
        "user-1",
        skip=20,
        limit=10,
        disabled_skills=["planner"],
    )

    assert skills == [
        {
            "skill_name": "planner",
            "enabled": False,
            "file_count": 2,
            "file_paths": ["SKILL.md", "notes.md"],
            "installed_from": "manual",
            "published_marketplace_name": "public-planner",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
            "is_pinned": False,
            "is_favorite": False,
        }
    ]
    assert collection.aggregate_pipelines[0][-2:] == [{"$skip": 20}, {"$limit": 10}]


@pytest.mark.asyncio
async def test_list_user_skills_offloads_meta_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    collection = _FakeSkillFilesCollection()
    storage = SkillStorage()

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)
    monkeypatch.setattr(skill_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    skills = await storage.list_user_skills("user-1", skip=0, limit=10)

    assert calls == [json.loads]
    assert skills[0]["published_marketplace_name"] == "public-planner"


@pytest.mark.asyncio
async def test_get_skill_meta_offloads_meta_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    storage = SkillStorage()

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(storage, "_get_files_collection", lambda: _FindOneMetaCollection())
    monkeypatch.setattr(skill_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    meta = await storage.get_skill_meta("planner", "user-1")

    assert calls == [json.loads]
    assert meta is not None
    assert meta.published_marketplace_name == "public-planner"


@pytest.mark.asyncio
async def test_list_user_skills_with_preferences_paginates_in_aggregation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeSkillFilesCollection()
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    await storage.list_user_skills(
        "user-1",
        skip=20,
        limit=10,
        pinned_skill_names=["planner"],
        favorite_skill_names=["writer"],
    )

    pipeline = collection.aggregate_pipelines[0]
    add_fields = next(stage["$addFields"] for stage in pipeline if "$addFields" in stage)
    assert add_fields["_is_pinned"] == {"$in": ["$_id", ["planner"]]}
    assert add_fields["_is_favorite"] == {"$in": ["$_id", ["writer"]]}
    assert {"$skip": 20} in pipeline
    assert {"$limit": 10} in pipeline


@pytest.mark.asyncio
async def test_list_user_skills_bounds_preference_lists_in_aggregation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeSkillFilesCollection()
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    await storage.list_user_skills(
        "user-1",
        skip=0,
        limit=10,
        pinned_skill_names=[f"pinned-{index}" for index in range(125)] + ["pinned-1"],
        favorite_skill_names=[f"favorite-{index}" for index in range(125)] + ["favorite-1"],
    )

    pipeline = collection.aggregate_pipelines[0]
    add_fields = next(stage["$addFields"] for stage in pipeline if "$addFields" in stage)
    assert add_fields["_is_pinned"] == {
        "$in": ["$_id", [f"pinned-{index}" for index in range(100)]]
    }
    assert add_fields["_is_favorite"] == {
        "$in": ["$_id", [f"favorite-{index}" for index in range(100)]]
    }


@pytest.mark.asyncio
async def test_update_user_preference_bounds_historical_preference_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_user_storage = _PreferenceUserStorage(
        {
            "pinned_skill_names": [f"pinned-{index}" for index in range(50)] + ["pinned-1"],
            "favorite_skill_names": [f"favorite-{index}" for index in range(130)] + ["favorite-1"],
        }
    )
    monkeypatch.setattr(user_storage, "UserStorage", lambda: fake_user_storage)

    storage = SkillStorage()
    result = await storage.update_user_preference(
        user_id="user-1",
        skill_name="favorite-1",
        update={"is_pinned": False},
    )

    assert result["is_favorite"] is True
    assert result["is_pinned"] is False
    assert len(fake_user_storage.updates) == 1
    updated = fake_user_storage.updates[0][1]
    assert updated["pinned_skill_names"] == [f"pinned-{index}" for index in range(10)]
    assert updated["favorite_skill_names"] == [f"favorite-{index}" for index in range(100)]


@pytest.mark.asyncio
async def test_update_user_preference_rejects_favorite_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_user_storage = _PreferenceUserStorage(
        {
            "pinned_skill_names": [],
            "favorite_skill_names": [f"favorite-{index}" for index in range(100)],
        }
    )
    monkeypatch.setattr(user_storage, "UserStorage", lambda: fake_user_storage)

    storage = SkillStorage()
    result = await storage.update_user_preference(
        user_id="user-1",
        skill_name="new-favorite",
        update={"is_favorite": True},
    )

    assert result == {"is_favorite": False, "is_pinned": False}
    assert fake_user_storage.updates == []


@pytest.mark.asyncio
async def test_list_user_skill_tags_limits_skill_md_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import storage as skill_storage

    monkeypatch.setattr(skill_storage, "SKILL_MD_SCAN_LIMIT", 3, raising=False)
    collection = _FakeSkillMdCollection(
        [
            {
                "skill_name": f"skill-{index}",
                "content": f"---\nname: skill-{index}\ntags:\n- tag-{index}\n---\n",
            }
            for index in range(5)
        ]
    )
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    tags = await storage.list_user_skill_tags("user-1")

    assert collection.find_calls == [
        (
            {"user_id": "user-1", "file_path": "SKILL.md"},
            {"skill_name": 1, "content": 1},
        )
    ]
    assert collection.cursor is not None
    assert collection.cursor.limit_value == 3
    assert tags == ["tag-0", "tag-1", "tag-2"]


@pytest.mark.asyncio
async def test_list_matching_skill_names_limits_skill_md_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import storage as skill_storage

    monkeypatch.setattr(skill_storage, "SKILL_MD_SCAN_LIMIT", 2, raising=False)
    collection = _FakeSkillMdCollection(
        [
            {
                "skill_name": f"planner-{index}",
                "content": f"---\nname: planner-{index}\ndescription: Plan {index}\n---\n",
            }
            for index in range(5)
        ]
    )
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    names = await storage.list_matching_skill_names("user-1", q="plan")

    assert collection.cursor is not None
    assert collection.cursor.limit_value == 2
    assert names == ["planner-0", "planner-1"]


@pytest.mark.asyncio
async def test_list_matching_skill_names_offloads_skill_md_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import parser as skill_parser
    from src.infra.skill import storage as skill_storage

    calls: list[Any] = []
    collection = _MatchingSkillCollection(
        [
            {
                "skill_name": f"planner-{index}",
                "content": (
                    f"---\nname: planner-{index}\ndescription: Plan {index}\n"
                    f"tags:\n- tag-{index}\n---\n"
                ),
            }
            for index in range(2)
        ]
    )

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(skill_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    names = await storage.list_matching_skill_names("user-1", q="plan")

    assert calls == [skill_parser.parse_skill_md, skill_parser.parse_skill_md]
    assert names == ["planner-0", "planner-1"]


@pytest.mark.asyncio
async def test_batch_get_skill_md_contents_bounds_name_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import storage as skill_storage

    monkeypatch.setattr(skill_storage, "SKILL_METADATA_LIST_LIMIT", 3, raising=False)
    collection = _FakeSkillMdCollection(
        [
            {
                "skill_name": f"skill-{index}",
                "content": f"content-{index}",
            }
            for index in range(3)
        ]
    )
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    docs = await storage.batch_get_skill_md_contents(
        [f"skill-{index}" for index in range(5)] + ["skill-1"],
        "user-1",
    )

    assert collection.find_calls == [
        (
            {
                "skill_name": {"$in": ["skill-0", "skill-1", "skill-2"]},
                "user_id": "user-1",
                "file_path": "SKILL.md",
            },
            {"skill_name": 1, "content": 1},
        )
    ]
    assert docs == {
        "skill-0": "content-0",
        "skill-1": "content-1",
        "skill-2": "content-2",
    }


@pytest.mark.asyncio
async def test_get_skill_files_limits_files_loaded_per_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import storage as skill_storage

    monkeypatch.setattr(skill_storage, "SKILL_FILES_PER_SKILL_LIMIT", 3, raising=False)
    collection = _GeneralFindCollection(
        [
            {"file_path": "__meta__", "content": "{}"},
            *[
                {"file_path": f"file-{index}.txt", "content": f"content-{index}"}
                for index in range(5)
            ],
        ]
    )
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    files = await storage.get_skill_files("planner", "user-1")

    assert collection.cursors[0].limit_value == 4
    assert files == {
        "file-0.txt": "content-0",
        "file-1.txt": "content-1",
        "file-2.txt": "content-2",
    }


@pytest.mark.asyncio
async def test_list_skill_file_paths_limits_files_loaded_per_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import storage as skill_storage

    monkeypatch.setattr(skill_storage, "SKILL_FILES_PER_SKILL_LIMIT", 3, raising=False)
    collection = _GeneralFindCollection([{"file_path": f"file-{index}.txt"} for index in range(5)])
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    paths = await storage.list_skill_file_paths("planner", "user-1")

    assert collection.cursors[0].limit_value == 3
    assert paths == ["file-0.txt", "file-1.txt", "file-2.txt"]


@pytest.mark.asyncio
async def test_get_skill_files_canonicalizes_lowercase_skill_md(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _GeneralFindCollection(
        [
            {"file_path": "skill.md", "content": "lowercase content"},
            {"file_path": "notes.md", "content": "notes"},
        ]
    )
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    files = await storage.get_skill_files("planner", "user-1")

    assert files == {
        "SKILL.md": "lowercase content",
        "notes.md": "notes",
    }


@pytest.mark.asyncio
async def test_get_skill_file_falls_back_to_legacy_lowercase_skill_md(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FindOneSkillMdCollection()
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    content = await storage.get_skill_file("planner", "SKILL.md", "user-1")

    assert content == "legacy lowercase content"
    assert collection.find_one_calls == [
        {"skill_name": "planner", "user_id": "user-1", "file_path": "SKILL.md"},
        {
            "skill_name": "planner",
            "user_id": "user-1",
            "file_path": {"$regex": r"^skill\.md$", "$options": "i"},
        },
    ]


@pytest.mark.asyncio
async def test_sync_skill_files_rejects_too_many_files_before_existing_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import storage as skill_storage

    monkeypatch.setattr(skill_storage, "SKILL_FILES_PER_SKILL_LIMIT", 3, raising=False)
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: _SyncShouldNotReadCollection())

    with pytest.raises(ValueError, match="too many files"):
        await storage.sync_skill_files(
            "planner",
            {f"file-{index}.txt": "content" for index in range(4)},
            "user-1",
        )


@pytest.mark.asyncio
async def test_sync_skill_files_only_scans_removed_binary_refs_before_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.skill import storage as skill_storage

    monkeypatch.setattr(skill_storage, "SKILL_FILES_PER_SKILL_LIMIT", 3, raising=False)
    deleted_s3: list[str] = []
    collection = _SyncRemovedBinaryCollection()
    storage = SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    async def fake_delete_s3_object(storage_key: str) -> None:
        deleted_s3.append(storage_key)

    monkeypatch.setattr(storage, "_delete_s3_object", fake_delete_s3_object)

    await storage.sync_skill_files(
        "planner",
        {"SKILL.md": "content", "notes.md": "notes"},
        "user-1",
    )

    assert collection.find_calls == [
        (
            {
                "skill_name": "planner",
                "user_id": "user-1",
                "file_path": {"$ne": "__meta__", "$nin": ["SKILL.md", "notes.md"]},
                "content": {"$regex": '"_binary_ref": true'},
            },
            {"content": 1},
        )
    ]
    assert collection.cursor.limit_value == 3
    assert collection.delete_many_calls == [
        {
            "skill_name": "planner",
            "user_id": "user-1",
            "file_path": {"$ne": "__meta__", "$nin": ["SKILL.md", "notes.md"]},
        }
    ]
    assert len(collection.bulk_operations) == 2
    assert deleted_s3 == ["skills/user-1/planner/old.png"]
