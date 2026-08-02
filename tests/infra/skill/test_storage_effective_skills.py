from __future__ import annotations

import json
from typing import Any

import pytest

from src.infra.skill import parser as skill_parser
from src.infra.skill import storage as skill_storage
from src.infra.storage import redis as redis_storage


class _FakeRedis:
    async def get(self, key: str):
        return None

    async def set(self, *args, **kwargs):
        return None


class _RecordingRedis:
    def __init__(self, cached: str | None = None) -> None:
        self.cached = cached
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str):
        return self.cached

    async def set(self, key: str, value: str, ex: int | None = None):
        self.set_calls.append((key, value, ex))


class _EffectiveSkillStorage(skill_storage.SkillStorage):
    def __init__(self, skill_names: list[str]) -> None:
        super().__init__()
        self.skill_names = skill_names
        self.batch_keys: list[tuple[str, str]] = []

    async def get_all_user_skill_names(
        self,
        user_id: str,
        exclude_skill_names: list[str] | None = None,
        limit: int | None = None,
    ) -> list[str]:
        assert user_id == "user-1"
        names = [name for name in self.skill_names if name not in set(exclude_skill_names or [])]
        if limit is not None:
            names = names[:limit]
        return names

    async def batch_get_skill_files(
        self,
        skill_keys: list[tuple[str, str]],
    ) -> dict[tuple[str, str], dict[str, str]]:
        self.batch_keys = skill_keys
        return {
            key: {"SKILL.md": f"---\nname: {key[0]}\ndescription: Demo\n---\n"}
            for key in skill_keys
        }


@pytest.mark.asyncio
async def test_get_effective_skills_caps_batch_file_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_storage, "SKILL_EFFECTIVE_LOAD_LIMIT", 100, raising=False)
    monkeypatch.setattr(redis_storage, "get_redis_client", lambda: _FakeRedis())
    storage = _EffectiveSkillStorage([f"skill-{index}" for index in range(125)])

    result = await storage.get_effective_skills("user-1", disabled_skills=[])

    assert storage.batch_keys == [(f"skill-{index}", "user-1") for index in range(100)]
    assert list(result["skills"]) == [f"skill-{index}" for index in range(100)]


@pytest.mark.asyncio
async def test_get_effective_skills_caps_after_disabled_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_storage, "SKILL_EFFECTIVE_LOAD_LIMIT", 3, raising=False)
    monkeypatch.setattr(redis_storage, "get_redis_client", lambda: _FakeRedis())
    storage = _EffectiveSkillStorage([f"skill-{index}" for index in range(8)])

    result: dict[str, Any] = await storage.get_effective_skills(
        "user-1",
        disabled_skills=["skill-0", "skill-2"],
    )

    assert storage.batch_keys == [
        ("skill-1", "user-1"),
        ("skill-3", "user-1"),
        ("skill-4", "user-1"),
    ]
    assert list(result["skills"]) == ["skill-1", "skill-3", "skill-4"]


@pytest.mark.asyncio
async def test_get_effective_skills_offloads_cached_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    redis = _RecordingRedis(cached='{"skills": {"planner": {"name": "planner"}}}')

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(redis_storage, "get_redis_client", lambda: redis)
    monkeypatch.setattr(skill_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    storage = _EffectiveSkillStorage(["planner"])
    result = await storage.get_effective_skills("user-1", disabled_skills=[])

    assert calls == [json.loads]
    assert result == {"skills": {"planner": {"name": "planner"}}}
    assert storage.batch_keys == []


@pytest.mark.asyncio
async def test_get_effective_skills_offloads_cache_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    redis = _RecordingRedis()

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(redis_storage, "get_redis_client", lambda: redis)
    monkeypatch.setattr(skill_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    storage = _EffectiveSkillStorage(["planner"])
    result = await storage.get_effective_skills("user-1", disabled_skills=[])

    assert calls == [skill_parser.parse_skill_md, json.dumps]
    assert "planner" in result["skills"]
    assert redis.set_calls


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self._index = 0
        self.limit_value: int | None = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return doc

    def sort(self, key, direction=None):
        # Mirror motor's sort: stable multi-key ordering, ascending by default.
        if isinstance(key, list):
            for field, sort_direction in reversed(key):
                self._docs.sort(
                    key=lambda doc: doc.get(field), reverse=sort_direction < 0
                )
        else:
            self._docs.sort(
                key=lambda doc: doc.get(key), reverse=(direction or 1) < 0
            )
        return self

    def limit(self, value: int):
        self.limit_value = value
        self._docs = self._docs[:value]
        return self


class _RecordingFilesCollection:
    def __init__(self) -> None:
        self.queries: list[dict[str, Any]] = []
        self.cursors: list[_AsyncCursor] = []

    def find(self, query: dict[str, Any]) -> _AsyncCursor:
        self.queries.append(query)
        or_clauses = query.get("$or", [])
        cursor = _AsyncCursor(
            [
                {
                    "skill_name": clause["skill_name"],
                    "user_id": clause["user_id"],
                    "file_path": "SKILL.md",
                    "content": "demo",
                }
                for clause in or_clauses
            ]
        )
        self.cursors.append(cursor)
        return cursor


class _RecordingMetaCollection:
    def __init__(self) -> None:
        self.update_calls: list[tuple[dict[str, Any], dict[str, Any], bool]] = []

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
    ) -> None:
        self.update_calls.append((query, update, upsert))


@pytest.mark.asyncio
async def test_set_skill_meta_offloads_meta_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    collection = _RecordingMetaCollection()
    storage = skill_storage.SkillStorage()

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)
    monkeypatch.setattr(skill_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)

    await storage.set_skill_meta(
        "planner",
        "user-1",
        installed_from=skill_storage.InstalledFrom.MARKETPLACE,
        published_marketplace_name="Planner",
    )

    assert calls == [json.dumps]
    assert collection.update_calls[0][2] is True
    content = collection.update_calls[0][1]["$set"]["content"]
    assert json.loads(content)["published_marketplace_name"] == "Planner"


@pytest.mark.asyncio
async def test_batch_get_skill_files_caps_or_clauses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_storage, "SKILL_BATCH_FILE_LOOKUP_LIMIT", 3, raising=False)
    collection = _RecordingFilesCollection()
    storage = skill_storage.SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    result = await storage.batch_get_skill_files(
        [(f"skill-{index}", "user-1") for index in range(5)] + [("skill-1", "user-1")]
    )

    assert len(collection.queries) == 1
    assert collection.queries[0]["$or"] == [
        {"skill_name": "skill-0", "user_id": "user-1"},
        {"skill_name": "skill-1", "user_id": "user-1"},
        {"skill_name": "skill-2", "user_id": "user-1"},
    ]
    assert collection.queries[0]["file_path"] == {"$ne": "__meta__"}
    assert collection.cursors[0].limit_value == 3 * skill_storage.SKILL_FILES_PER_SKILL_LIMIT
    assert list(result) == [
        ("skill-0", "user-1"),
        ("skill-1", "user-1"),
        ("skill-2", "user-1"),
    ]


class _ManyFilesCollection:
    def __init__(self) -> None:
        self.queries: list[dict[str, Any]] = []
        self.cursors: list[_AsyncCursor] = []

    def find(self, query: dict[str, Any]) -> _AsyncCursor:
        self.queries.append(query)
        or_clauses = query.get("$or", [])
        docs: list[dict[str, Any]] = []
        for clause in or_clauses:
            skill_name = clause["skill_name"]
            for index in range(5):
                docs.append(
                    {
                        "skill_name": skill_name,
                        "user_id": clause["user_id"],
                        "file_path": f"file-{index}.md",
                        "content": f"content-{index}",
                    }
                )
        cursor = _AsyncCursor(docs)
        self.cursors.append(cursor)
        return cursor


@pytest.mark.asyncio
async def test_batch_get_skill_files_limits_files_loaded_per_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_storage, "SKILL_FILES_PER_SKILL_LIMIT", 3, raising=False)
    collection = _ManyFilesCollection()
    storage = skill_storage.SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    result = await storage.batch_get_skill_files([("planner", "user-1")])

    assert result == {
        ("planner", "user-1"): {
            "file-0.md": "content-0",
            "file-1.md": "content-1",
            "file-2.md": "content-2",
        }
    }
    assert len(collection.queries) == 1
    assert collection.queries[0]["$or"] == [
        {"skill_name": "planner", "user_id": "user-1"}
    ]
    assert collection.queries[0]["file_path"] == {"$ne": "__meta__"}
    assert collection.cursors[0].limit_value == 1 * 3


@pytest.mark.asyncio
async def test_batch_get_skill_files_fetches_multiple_skills_in_single_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple skills load via one $or query (no N+1); each is fully returned
    when its file count stays within SKILL_FILES_PER_SKILL_LIMIT — the invariant
    sync_skill_files enforces in production, so a single bounded find suffices
    and per-skill starvation cannot occur."""
    monkeypatch.setattr(skill_storage, "SKILL_FILES_PER_SKILL_LIMIT", 5, raising=False)
    collection = _ManyFilesCollection()
    storage = skill_storage.SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    result = await storage.batch_get_skill_files([("alpha", "user-1"), ("beta", "user-1")])

    expected_files = {f"file-{i}.md": f"content-{i}" for i in range(5)}
    assert result == {
        ("alpha", "user-1"): dict(expected_files),
        ("beta", "user-1"): dict(expected_files),
    }
    assert len(collection.queries) == 1
    assert collection.queries[0]["$or"] == [
        {"skill_name": "alpha", "user_id": "user-1"},
        {"skill_name": "beta", "user_id": "user-1"},
    ]
    assert collection.queries[0]["file_path"] == {"$ne": "__meta__"}
    assert collection.cursors[0].limit_value == 2 * 5


class _AggregateSkillNameCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.pipelines: list[list[dict[str, Any]]] = []

    def aggregate(self, pipeline: list[dict[str, Any]]) -> _AsyncCursor:
        self.pipelines.append(pipeline)
        return _AsyncCursor(
            [
                {"_id": "skill-1"},
                {"_id": "skill-3"},
                {"_id": "skill-4"},
            ]
        )

    def find(self, query: dict[str, Any]) -> _AsyncCursor:
        or_clauses = query.get("$or", [])
        return _AsyncCursor(
            [
                {
                    "skill_name": clause["skill_name"],
                    "user_id": clause["user_id"],
                    "file_path": "SKILL.md",
                    "content": f"---\nname: {clause['skill_name']}\ndescription: Demo\n---\n",
                }
                for clause in or_clauses
            ]
        )


@pytest.mark.asyncio
async def test_get_effective_skills_pushes_limit_and_disabled_filter_into_skill_name_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_storage, "SKILL_EFFECTIVE_LOAD_LIMIT", 3, raising=False)
    monkeypatch.setattr(redis_storage, "get_redis_client", lambda: _FakeRedis())
    collection = _AggregateSkillNameCollection([])
    storage = skill_storage.SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    result: dict[str, Any] = await storage.get_effective_skills(
        "user-1",
        disabled_skills=["skill-0", "skill-2"],
    )

    assert list(result["skills"]) == ["skill-1", "skill-3", "skill-4"]
    assert collection.pipelines == [
        [
            {
                "$match": {
                    "user_id": "user-1",
                    "file_path": {"$ne": "__meta__"},
                    "skill_name": {"$nin": ["skill-0", "skill-2"]},
                }
            },
            {"$group": {"_id": "$skill_name"}},
            {"$sort": {"_id": 1}},
            {"$limit": 3},
        ]
    ]


@pytest.mark.asyncio
async def test_get_all_user_skill_names_defaults_to_bounded_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_storage, "SKILL_EFFECTIVE_LOAD_LIMIT", 3, raising=False)
    collection = _AggregateSkillNameCollection([])
    storage = skill_storage.SkillStorage()
    monkeypatch.setattr(storage, "_get_files_collection", lambda: collection)

    result = await storage.get_all_user_skill_names("user-1")

    assert result == ["skill-1", "skill-3", "skill-4"]
    assert collection.pipelines == [
        [
            {
                "$match": {
                    "user_id": "user-1",
                    "file_path": {"$ne": "__meta__"},
                }
            },
            {"$group": {"_id": "$skill_name"}},
            {"$sort": {"_id": 1}},
            {"$limit": 3},
        ]
    ]
