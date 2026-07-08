"""Tests for team storage."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from bson import ObjectId

from src.infra.team.storage import TeamStorage
from src.kernel.schemas.team import TEAM_MEMBERS_MAX, TEAM_STARTER_PROMPTS_MAX, TEAM_TAGS_MAX


def _make_fake_collection():
    """Build a fake Motor collection backed by an in-memory list."""
    store: list[dict] = []
    counter = {"value": 0}

    def _next_id():
        counter["value"] += 1
        return str(counter["value"])

    async def insert_one(doc: dict):
        doc = dict(doc)
        fake_id = MagicMock()
        fake_id.__str__ = lambda self: _next_id()
        # Use a deterministic id for test assertions
        from bson import ObjectId

        oid = ObjectId()
        doc["_id"] = oid
        store.append(doc)
        result = MagicMock()
        result.inserted_id = oid
        return result

    async def find_one(query: dict):
        filter_id = query.get("_id")
        owner = query.get("owner_user_id")
        for doc in store:
            if filter_id is not None and doc.get("_id") != filter_id:
                continue
            if owner is not None and doc.get("owner_user_id") != owner:
                continue
            return dict(doc)
        return None

    def _matches_regex(value, regex: str) -> bool:
        if isinstance(value, list):
            return any(_matches_regex(item, regex) for item in value)
        return re.search(regex, str(value or ""), re.IGNORECASE) is not None

    def _matches_path(doc: dict, path: str, condition) -> bool:
        current = doc
        parts = path.split(".")
        for index, part in enumerate(parts):
            if isinstance(current, list):
                return any(
                    _matches_path(item, ".".join(parts[index:]), condition) for item in current
                )
            if not isinstance(current, dict):
                return False
            current = current.get(part)
        if isinstance(condition, dict):
            if "$regex" in condition:
                return _matches_regex(current, condition["$regex"])
            if "$elemMatch" in condition:
                return _matches_regex(current, condition["$elemMatch"]["$regex"])
            if "$in" in condition:
                return current in set(condition["$in"])
        if isinstance(current, list):
            return condition in current
        return current == condition

    def _matches_query(doc: dict, query: dict) -> bool:
        for key, value in query.items():
            if key == "$or":
                if not any(_matches_query(doc, clause) for clause in value):
                    return False
                continue
            if not _matches_path(doc, key, value):
                return False
        return True

    async def count_documents(query: dict):
        return sum(1 for d in store if _matches_query(d, query))

    class _Cursor:
        def __init__(self, docs):
            self._docs = list(docs)

        def sort(self, *a, **kw):
            return self

        def skip(self, n):
            self._docs = self._docs[n:]
            return self

        def limit(self, n):
            self._docs = self._docs[:n]
            return self

        async def __aiter__(self):
            for doc in self._docs:
                yield doc

    def find(query: dict):
        matches = [dict(d) for d in store if _matches_query(d, query)]
        return _Cursor(matches)

    def aggregate(pipeline: list[dict]):
        docs = [dict(d) for d in store]
        for stage in pipeline:
            if "$match" in stage:
                docs = [doc for doc in docs if _matches_query(doc, stage["$match"])]
            elif "$addFields" in stage:
                pinned_ids = stage["$addFields"]["is_pinned"]["$in"][1]
                favorite_ids = stage["$addFields"]["is_favorite"]["$in"][1]
                for doc in docs:
                    doc["is_pinned"] = str(doc["_id"]) in pinned_ids
                    doc["is_favorite"] = str(doc["_id"]) in favorite_ids
            elif "$sort" in stage:

                def _sort_key(doc):
                    return (
                        int(bool(doc.get("is_pinned"))),
                        int(bool(doc.get("is_favorite"))),
                        doc.get("updated_at"),
                        doc.get("created_at"),
                    )

                docs.sort(key=_sort_key, reverse=True)
            elif "$skip" in stage:
                docs = docs[stage["$skip"] :]
            elif "$limit" in stage:
                docs = docs[: stage["$limit"]]
        return _Cursor(docs)

    async def delete_one(query: dict):
        filter_id = query.get("_id")
        owner = query.get("owner_user_id")
        for i, doc in enumerate(store):
            if doc.get("_id") == filter_id and doc.get("owner_user_id") == owner:
                store.pop(i)
                result = MagicMock()
                result.deleted_count = 1
                return result
        result = MagicMock()
        result.deleted_count = 0
        return result

    async def find_one_and_update(query: dict, update_doc: dict, return_document=True):
        filter_id = query.get("_id")
        owner = query.get("owner_user_id")
        for i, doc in enumerate(store):
            if doc.get("_id") == filter_id and doc.get("owner_user_id") == owner:
                updated = dict(doc)
                updated.update(update_doc.get("$set", {}))
                store[i] = updated
                return dict(updated)
        return None

    async def insert_many(docs: list[dict]):
        inserted = []
        for doc in docs:
            doc = dict(doc)
            from bson import ObjectId

            oid = ObjectId()
            doc["_id"] = oid
            store.append(doc)
            inserted.append(oid)
        result = MagicMock()
        result.inserted_ids = inserted
        return result

    coll = MagicMock()
    coll.insert_one = insert_one
    coll.find_one = find_one
    coll.find = find
    coll.aggregate = aggregate
    coll.count_documents = count_documents
    coll.delete_one = delete_one
    coll.find_one_and_update = find_one_and_update
    coll.insert_many = insert_many
    return coll, store


def _make_fake_user_collection():
    users: dict[ObjectId, dict] = {}

    async def find_one(query: dict, projection: dict | None = None):
        user_id = query.get("_id")
        return users.get(user_id)

    async def update_one(query: dict, update_doc: dict):
        user_id = query.get("_id")
        user = users.setdefault(user_id, {"_id": user_id, "metadata": {}})
        for key, value in update_doc.get("$set", {}).items():
            if key.startswith("metadata."):
                user["metadata"][key.removeprefix("metadata.")] = value
            else:
                user[key] = value
        result = MagicMock()
        result.modified_count = 1
        return result

    async def update_many(query: dict, update_doc: dict):
        modified = 0
        for user in users.values():
            for key, value in update_doc.get("$pull", {}).items():
                if not key.startswith("metadata."):
                    continue
                metadata_key = key.removeprefix("metadata.")
                current = user.setdefault("metadata", {}).get(metadata_key, [])
                if value in current:
                    user["metadata"][metadata_key] = [item for item in current if item != value]
                    modified += 1
        result = MagicMock()
        result.modified_count = modified
        return result

    coll = MagicMock()
    coll.find_one = find_one
    coll.update_one = update_one
    coll.update_many = update_many
    return coll, users


@pytest.fixture
def storage():
    s = TeamStorage()
    coll, store = _make_fake_collection()
    s._collection = coll
    user_coll, users = _make_fake_user_collection()
    s._user_collection = user_coll
    return s, store, users


@pytest.mark.asyncio
async def test_create_team(storage):
    s, store, users = storage
    team = await s.create_team(
        owner_user_id="user-1",
        name="Test Team",
        description="A test team",
        avatar="🤖",
        members=[
            {"persona_preset_id": "preset-1", "role_instructions": "Be helpful"},
        ],
    )
    assert team.name == "Test Team"
    assert team.avatar == "🤖"
    assert team.owner_user_id == "user-1"
    assert len(team.members) == 1
    assert team.members[0].persona_preset_id == "preset-1"
    assert team.members[0].member_id.startswith("m-")
    assert team.members[0].model_id is None
    assert team.run_in_sandbox is False
    assert team.visibility.value == "private"


@pytest.mark.asyncio
async def test_create_and_get_team_preserves_run_in_sandbox(storage):
    s, store, users = storage
    team = await s.create_team(
        owner_user_id="user-1",
        name="Sandbox Team",
        run_in_sandbox=True,
    )

    fetched = await s.get_team(team.id, owner_user_id="user-1")

    assert fetched is not None
    assert fetched.run_in_sandbox is True
    assert store[0]["run_in_sandbox"] is True


@pytest.mark.asyncio
async def test_old_team_without_run_in_sandbox_defaults_false(storage):
    s, store, users = storage
    team = await s.create_team(owner_user_id="user-1", name="Legacy Team")
    del store[0]["run_in_sandbox"]

    fetched = await s.get_team(team.id, owner_user_id="user-1")

    assert fetched is not None
    assert fetched.run_in_sandbox is False


@pytest.mark.asyncio
async def test_create_and_get_team_preserves_member_model_id(storage):
    s, store, users = storage
    team = await s.create_team(
        owner_user_id="user-1",
        name="Model Team",
        members=[
            {
                "member_id": "m-analyst",
                "persona_preset_id": "preset-1",
                "model_id": "model-member",
            },
        ],
    )

    fetched = await s.get_team(team.id, owner_user_id="user-1")

    assert fetched is not None
    assert fetched.members[0].model_id == "model-member"
    assert store[0]["members"][0]["model_id"] == "model-member"


@pytest.mark.asyncio
async def test_create_and_get_team_ignores_member_agent_id(storage):
    s, store, users = storage
    team = await s.create_team(
        owner_user_id="user-1",
        name="Mode Team",
        members=[
            {
                "member_id": "m-analyst",
                "persona_preset_id": "preset-1",
                "agent_id": "search",
            },
        ],
    )

    fetched = await s.get_team(team.id, owner_user_id="user-1")

    assert fetched is not None
    assert not hasattr(fetched.members[0], "agent_id")
    assert "agent_id" not in store[0]["members"][0]


@pytest.mark.asyncio
async def test_old_team_member_without_model_id_returns_none(storage):
    s, store, users = storage
    team = await s.create_team(
        owner_user_id="user-1",
        name="Legacy Team",
        members=[{"member_id": "m-legacy", "persona_preset_id": "preset-1"}],
    )
    del store[0]["members"][0]["model_id"]

    fetched = await s.get_team(team.id, owner_user_id="user-1")

    assert fetched is not None
    assert fetched.members[0].model_id is None


@pytest.mark.asyncio
async def test_legacy_team_member_agent_id_returns_warning_without_field(storage):
    s, store, users = storage
    team = await s.create_team(
        owner_user_id="user-1",
        name="Legacy Team",
        members=[{"member_id": "m-legacy", "persona_preset_id": "preset-1"}],
    )
    store[0]["members"][0]["agent_id"] = "search"

    fetched = await s.get_team(team.id, owner_user_id="user-1")

    assert fetched is not None
    assert not hasattr(fetched.members[0], "agent_id")
    assert fetched.compatibility_warnings == ["legacy_member_agent_id_ignored"]


@pytest.mark.asyncio
async def test_create_team_preserves_starter_prompts(storage):
    s, store, users = storage

    team = await s.create_team(
        owner_user_id="user-1",
        name="Prompted Team",
        starter_prompts=[
            {"icon": "🧭", "text": "帮我制定协作计划"},
            {"icon": "", "text": {"zh": "总结团队分工", "en": "Summarize roles"}},
        ],
    )

    assert team.starter_prompts[0].icon == "🧭"
    assert team.starter_prompts[0].text == "帮我制定协作计划"
    assert team.starter_prompts[1].icon is None
    assert team.starter_prompts[1].text == {
        "zh": "总结团队分工",
        "en": "Summarize roles",
    }


@pytest.mark.asyncio
async def test_create_team_preserves_tags(storage):
    s, store, users = storage

    team = await s.create_team(
        owner_user_id="user-1",
        name="Tagged Team",
        tags=["research", "writing"],
    )

    assert team.tags == ["research", "writing"]


@pytest.mark.asyncio
async def test_create_team_caps_members_tags_and_starter_prompts_at_storage_layer(storage):
    s, store, users = storage

    team = await s.create_team(
        owner_user_id="user-1",
        name="Bounded Team",
        tags=[f"tag-{index}" for index in range(TEAM_TAGS_MAX + 5)],
        members=[
            {"persona_preset_id": f"preset-{index}", "position": index}
            for index in range(TEAM_MEMBERS_MAX + 5)
        ],
        starter_prompts=[
            {"icon": "", "text": f"prompt-{index}"} for index in range(TEAM_STARTER_PROMPTS_MAX + 5)
        ],
    )

    assert len(team.tags) == TEAM_TAGS_MAX
    assert len(team.members) == TEAM_MEMBERS_MAX
    assert len(team.starter_prompts) == TEAM_STARTER_PROMPTS_MAX
    assert team.tags[-1] == f"tag-{TEAM_TAGS_MAX - 1}"
    assert team.members[-1].persona_preset_id == f"preset-{TEAM_MEMBERS_MAX - 1}"
    assert team.starter_prompts[-1].text == f"prompt-{TEAM_STARTER_PROMPTS_MAX - 1}"


@pytest.mark.asyncio
async def test_create_team_uses_created_first_member_as_default(storage):
    s, store, users = storage

    team = await s.create_team(
        owner_user_id="user-1",
        name="Team With Default",
        members=[
            {"persona_preset_id": "preset-1", "position": 0},
            {"persona_preset_id": "preset-2", "position": 1},
        ],
        default_member_id="temporary-frontend-member-id",
    )

    assert team.default_member_id == team.members[0].member_id


@pytest.mark.asyncio
async def test_get_team_not_found(storage):
    s, store, users = storage
    result = await s.get_team("nonexistent-id", owner_user_id="user-1")
    assert result is None


@pytest.mark.asyncio
async def test_list_teams_paginated(storage):
    s, store, users = storage
    await s.create_team(owner_user_id="user-1", name="Team A")
    await s.create_team(owner_user_id="user-1", name="Team B")
    await s.create_team(owner_user_id="user-2", name="Team C")

    teams, total = await s.list_teams(owner_user_id="user-1", skip=0, limit=10)
    assert total == 2
    assert len(teams) == 2
    names = {t.name for t in teams}
    assert names == {"Team A", "Team B"}


@pytest.mark.asyncio
async def test_list_teams_uses_bounded_aggregation_instead_of_materializing_find():
    owner_user_id = str(ObjectId())
    team_id = ObjectId()
    pipelines: list[list[dict]] = []

    class _Cursor:
        def __init__(self, docs):
            self._docs = list(docs)

        def __aiter__(self):
            self._iter = iter(self._docs)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    class _Collection:
        def find(self, _query):
            raise AssertionError("list_teams should not materialize an unbounded find cursor")

        async def count_documents(self, query):
            assert query == {"owner_user_id": owner_user_id}
            return 1

        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return _Cursor(
                [
                    {
                        "_id": team_id,
                        "owner_user_id": owner_user_id,
                        "name": "Bounded",
                        "description": "",
                        "tags": [],
                        "members": [],
                        "created_at": datetime(2026, 1, 1),
                        "updated_at": datetime(2026, 1, 1),
                    }
                ]
            )

    s = TeamStorage()
    s._collection = _Collection()
    user_coll, _users = _make_fake_user_collection()
    s._user_collection = user_coll

    teams, total = await s.list_teams(owner_user_id=owner_user_id, skip=20, limit=10)

    assert total == 1
    assert [team.name for team in teams] == ["Bounded"]
    assert {"$skip": 20} in pipelines[0]
    assert {"$limit": 10} in pipelines[0]


@pytest.mark.asyncio
async def test_list_teams_fetches_count_and_preferences_concurrently():
    owner_user_id = str(ObjectId())
    pipelines: list[list[dict]] = []

    class _Cursor:
        def __aiter__(self):
            self._iter = iter([])
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        async def count_documents(self, query):
            for _ in range(10):
                if user_collection.find_one_started:
                    break
                await asyncio.sleep(0)
            assert user_collection.find_one_started is True
            assert query == {"owner_user_id": owner_user_id}
            return 1

        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return _Cursor()

    class _UserCollection:
        def __init__(self) -> None:
            self.find_one_started = False

        async def find_one(self, _query, _projection=None):
            self.find_one_started = True
            return {"metadata": {"pinned_team_ids": [], "favorite_team_ids": []}}

    user_collection = _UserCollection()
    s = TeamStorage()
    s._collection = _Collection()
    s._user_collection = user_collection

    teams, total = await s.list_teams(owner_user_id=owner_user_id, skip=0, limit=10)

    assert teams == []
    assert total == 1
    assert pipelines


@pytest.mark.asyncio
async def test_list_teams_accepts_future_returned_by_motor_count_documents():
    owner_user_id = str(ObjectId())
    pipelines: list[list[dict]] = []

    class _Cursor:
        def __aiter__(self):
            self._iter = iter([])
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        def count_documents(self, query):
            assert query == {"owner_user_id": owner_user_id}
            future = asyncio.get_running_loop().create_future()
            future.set_result(1)
            return future

        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return _Cursor()

    s = TeamStorage()
    s._collection = _Collection()
    user_coll, _users = _make_fake_user_collection()
    s._user_collection = user_coll

    teams, total = await s.list_teams(owner_user_id=owner_user_id, skip=0, limit=50)

    assert teams == []
    assert total == 1
    assert pipelines


@pytest.mark.asyncio
async def test_list_teams_clamps_storage_limit():
    owner_user_id = str(ObjectId())
    pipelines: list[list[dict]] = []

    class _Cursor:
        def __aiter__(self):
            self._iter = iter([])
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        async def count_documents(self, query):
            assert query == {"owner_user_id": owner_user_id}
            return 500

        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return _Cursor()

    s = TeamStorage()
    s._collection = _Collection()
    user_coll, _users = _make_fake_user_collection()
    s._user_collection = user_coll

    teams, total = await s.list_teams(owner_user_id=owner_user_id, skip=0, limit=10_000)

    assert teams == []
    assert total == 500
    assert {"$limit": 200} in pipelines[0]


@pytest.mark.asyncio
async def test_list_teams_bounds_large_user_preference_arrays():
    owner_user_id = str(ObjectId())
    pipelines: list[list[dict]] = []

    class _Cursor:
        def __aiter__(self):
            self._iter = iter([])
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        async def count_documents(self, query):
            assert query == {"owner_user_id": owner_user_id}
            return 1

        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return _Cursor()

    class _UserCollection:
        async def find_one(self, _query, _projection=None):
            return {
                "metadata": {
                    "pinned_team_ids": [f"pin-{index}" for index in range(30)],
                    "favorite_team_ids": [f"fav-{index}" for index in range(500)],
                }
            }

    s = TeamStorage()
    s._collection = _Collection()
    s._user_collection = _UserCollection()

    teams, total = await s.list_teams(owner_user_id=owner_user_id, skip=0, limit=10)

    assert teams == []
    assert total == 1
    add_fields = pipelines[0][1]["$addFields"]
    assert len(add_fields["is_pinned"]["$in"][1]) == s.MAX_PINNED
    assert len(add_fields["is_favorite"]["$in"][1]) == s.MAX_FAVORITES


@pytest.mark.asyncio
async def test_list_teams_filters_by_query_and_tag(storage):
    s, store, users = storage
    await s.create_team(
        owner_user_id="user-1",
        name="Research Team",
        description="Deep analysis",
        tags=["research"],
    )
    await s.create_team(
        owner_user_id="user-1",
        name="Writing Team",
        description="Drafting",
        tags=["writing"],
    )

    teams, total = await s.list_teams(
        owner_user_id="user-1",
        q="analysis",
        tag="research",
        skip=0,
        limit=10,
    )

    assert total == 1
    assert [team.name for team in teams] == ["Research Team"]


@pytest.mark.asyncio
async def test_list_teams_search_treats_query_as_literal_text(storage):
    s, store, users = storage
    await s.create_team(
        owner_user_id="user-1",
        name="A.B Team",
        description="literal punctuation",
    )
    await s.create_team(
        owner_user_id="user-1",
        name="AXB Team",
        description="regex-looking neighbor",
    )

    teams, total = await s.list_teams(
        owner_user_id="user-1",
        q="A.B",
        skip=0,
        limit=10,
    )

    assert total == 1
    assert [team.name for team in teams] == ["A.B Team"]


@pytest.mark.asyncio
async def test_delete_team(storage):
    s, store, users = storage
    team = await s.create_team(owner_user_id="user-1", name="To Delete")
    deleted = await s.delete_team(team.id, owner_user_id="user-1")
    assert deleted is True
    result = await s.get_team(team.id, owner_user_id="user-1")
    assert result is None


@pytest.mark.asyncio
async def test_delete_team_wrong_owner(storage):
    s, store, users = storage
    team = await s.create_team(owner_user_id="user-1", name="Owned")
    deleted = await s.delete_team(team.id, owner_user_id="user-2")
    assert deleted is False


@pytest.mark.asyncio
async def test_clone_team(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        members=[
            {"persona_preset_id": "preset-1"},
        ],
    )
    cloned = await s.clone_team(original.id, owner_user_id="user-1")
    assert cloned is not None
    assert cloned.name == "Original (copy)"
    assert cloned.id != original.id
    assert len(cloned.members) == 1
    assert cloned.members[0].member_id != original.members[0].member_id


@pytest.mark.asyncio
async def test_clone_team_preserves_member_model_id(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        members=[
            {
                "persona_preset_id": "preset-1",
                "model_id": "model-member",
            },
        ],
    )

    cloned = await s.clone_team(original.id, owner_user_id="user-1")

    assert cloned is not None
    assert cloned.members[0].model_id == "model-member"


@pytest.mark.asyncio
async def test_clone_team_drops_legacy_member_agent_id(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        members=[
            {
                "persona_preset_id": "preset-1",
            },
        ],
    )
    store[0]["members"][0]["agent_id"] = "search"

    cloned = await s.clone_team(original.id, owner_user_id="user-1")

    assert cloned is not None
    assert not hasattr(cloned.members[0], "agent_id")
    assert "agent_id" not in store[-1]["members"][0]


@pytest.mark.asyncio
async def test_update_team_preserves_client_member_ids_and_default(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        members=[
            {"member_id": "m-alpha", "persona_preset_id": "preset-1"},
            {"member_id": "m-beta", "persona_preset_id": "preset-2"},
        ],
        default_member_id="m-alpha",
    )

    updated = await s.update_team(
        original.id,
        owner_user_id="user-1",
        update={
            "avatar": "icon:sparkles",
            "members": [
                {"member_id": "m-alpha", "persona_preset_id": "preset-1"},
                {"member_id": "m-beta", "persona_preset_id": "preset-2"},
            ],
            "default_member_id": "m-beta",
        },
    )

    assert updated is not None
    assert updated.avatar == "icon:sparkles"
    assert [m.member_id for m in updated.members] == ["m-alpha", "m-beta"]
    assert updated.default_member_id == "m-beta"


@pytest.mark.asyncio
async def test_update_team_preserves_member_model_id(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        members=[{"member_id": "m-alpha", "persona_preset_id": "preset-1"}],
    )

    updated = await s.update_team(
        original.id,
        owner_user_id="user-1",
        update={
            "members": [
                {
                    "member_id": "m-alpha",
                    "persona_preset_id": "preset-1",
                    "model_id": "model-member",
                },
            ],
        },
    )

    assert updated is not None
    assert updated.members[0].model_id == "model-member"


@pytest.mark.asyncio
async def test_update_team_ignores_member_agent_id(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        members=[{"member_id": "m-alpha", "persona_preset_id": "preset-1"}],
    )

    updated = await s.update_team(
        original.id,
        owner_user_id="user-1",
        update={
            "members": [
                {
                    "member_id": "m-alpha",
                    "persona_preset_id": "preset-1",
                    "agent_id": "search",
                },
            ],
        },
    )

    assert updated is not None
    assert not hasattr(updated.members[0], "agent_id")
    assert "agent_id" not in store[0]["members"][0]


@pytest.mark.asyncio
async def test_update_team_preserves_starter_prompts(storage):
    s, store, users = storage
    original = await s.create_team(owner_user_id="user-1", name="Original")

    updated = await s.update_team(
        original.id,
        owner_user_id="user-1",
        update={
            "starter_prompts": [
                {"icon": "💬", "text": "让团队给我三个方案"},
            ],
        },
    )

    assert updated is not None
    assert [prompt.model_dump(mode="json") for prompt in updated.starter_prompts] == [
        {"icon": "💬", "text": "让团队给我三个方案"},
    ]


@pytest.mark.asyncio
async def test_update_team_caps_members_tags_and_starter_prompts_at_storage_layer(storage):
    s, store, users = storage
    original = await s.create_team(owner_user_id="user-1", name="Original")

    updated = await s.update_team(
        original.id,
        owner_user_id="user-1",
        update={
            "tags": [f"tag-{index}" for index in range(TEAM_TAGS_MAX + 5)],
            "members": [
                {"persona_preset_id": f"preset-{index}", "position": index}
                for index in range(TEAM_MEMBERS_MAX + 5)
            ],
            "starter_prompts": [
                {"icon": "", "text": f"prompt-{index}"}
                for index in range(TEAM_STARTER_PROMPTS_MAX + 5)
            ],
        },
    )

    assert updated is not None
    assert len(updated.tags) == TEAM_TAGS_MAX
    assert len(updated.members) == TEAM_MEMBERS_MAX
    assert len(updated.starter_prompts) == TEAM_STARTER_PROMPTS_MAX


@pytest.mark.asyncio
async def test_clone_team_preserves_avatar(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        avatar="/api/upload/file/team.png",
        members=[
            {"persona_preset_id": "preset-1"},
        ],
    )

    cloned = await s.clone_team(original.id, owner_user_id="user-1")

    assert cloned is not None
    assert cloned.avatar == "/api/upload/file/team.png"


@pytest.mark.asyncio
async def test_clone_team_preserves_starter_prompts(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        starter_prompts=[
            {"icon": "✨", "text": "启动团队复盘"},
        ],
    )

    cloned = await s.clone_team(original.id, owner_user_id="user-1")

    assert cloned is not None
    assert [prompt.model_dump(mode="json") for prompt in cloned.starter_prompts] == [
        {"icon": "✨", "text": "启动团队复盘"},
    ]


@pytest.mark.asyncio
async def test_clone_team_preserves_tags(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        tags=["research", "review"],
    )

    cloned = await s.clone_team(original.id, owner_user_id="user-1")

    assert cloned is not None
    assert cloned.tags == ["research", "review"]


@pytest.mark.asyncio
async def test_clone_team_preserves_run_in_sandbox(storage):
    s, store, users = storage
    original = await s.create_team(
        owner_user_id="user-1",
        name="Original",
        run_in_sandbox=True,
    )

    cloned = await s.clone_team(original.id, owner_user_id="user-1")

    assert cloned is not None
    assert cloned.run_in_sandbox is True


@pytest.mark.asyncio
async def test_team_preferences_sort_list_and_update_response(storage):
    s, store, users = storage
    owner_user_id = str(ObjectId())
    normal = await s.create_team(owner_user_id=owner_user_id, name="Normal")
    favorite = await s.create_team(owner_user_id=owner_user_id, name="Favorite")
    pinned = await s.create_team(owner_user_id=owner_user_id, name="Pinned")

    favorite_pref = await s.update_user_preference(
        user_id=owner_user_id,
        team_id=favorite.id,
        update={"is_favorite": True},
    )
    pinned_pref = await s.update_user_preference(
        user_id=owner_user_id,
        team_id=pinned.id,
        update={"is_pinned": True},
    )
    teams, total = await s.list_teams(owner_user_id=owner_user_id, skip=0, limit=10)

    assert favorite_pref["is_favorite"] is True
    assert pinned_pref["is_pinned"] is True
    assert total == 3
    assert [team.id for team in teams] == [pinned.id, favorite.id, normal.id]
    assert teams[0].is_pinned is True
    assert teams[1].is_favorite is True


@pytest.mark.asyncio
async def test_list_teams_filters_favorites(storage):
    s, store, users = storage
    owner_user_id = str(ObjectId())
    normal = await s.create_team(owner_user_id=owner_user_id, name="Normal")
    favorite = await s.create_team(owner_user_id=owner_user_id, name="Favorite")
    await s.update_user_preference(
        user_id=owner_user_id,
        team_id=favorite.id,
        update={"is_favorite": True},
    )

    teams, total = await s.list_teams(
        owner_user_id=owner_user_id,
        favorite=True,
        skip=0,
        limit=10,
    )

    assert total == 1
    assert [team.id for team in teams] == [favorite.id]


@pytest.mark.asyncio
async def test_update_team_preference_rejects_favorite_overflow(storage):
    s, store, users = storage
    owner_user_id = str(ObjectId())
    team_id = str(ObjectId())
    users[ObjectId(owner_user_id)] = {
        "_id": ObjectId(owner_user_id),
        "metadata": {
            "pinned_team_ids": [],
            "favorite_team_ids": [str(ObjectId()) for _ in range(s.MAX_FAVORITES)],
        },
    }

    result = await s.update_user_preference(
        user_id=owner_user_id,
        team_id=team_id,
        update={"is_favorite": True},
    )

    metadata = users[ObjectId(owner_user_id)]["metadata"]
    assert result["is_favorite"] is False
    assert team_id not in metadata["favorite_team_ids"]
    assert len(metadata["favorite_team_ids"]) == s.MAX_FAVORITES


@pytest.mark.asyncio
async def test_list_teams_false_preference_filters_do_not_return_empty(storage):
    s, store, users = storage
    owner_user_id = str(ObjectId())
    normal = await s.create_team(owner_user_id=owner_user_id, name="Normal")
    favorite = await s.create_team(owner_user_id=owner_user_id, name="Favorite")
    await s.update_user_preference(
        user_id=owner_user_id,
        team_id=favorite.id,
        update={"is_favorite": True},
    )

    teams, total = await s.list_teams(
        owner_user_id=owner_user_id,
        favorite=False,
        pinned=False,
        skip=0,
        limit=10,
    )

    assert total == 2
    assert {team.id for team in teams} == {normal.id, favorite.id}


@pytest.mark.asyncio
async def test_delete_team_removes_deleted_id_from_user_preferences(storage):
    s, store, users = storage
    owner_user_id = str(ObjectId())
    team = await s.create_team(owner_user_id=owner_user_id, name="Pinned")
    await s.update_user_preference(
        user_id=owner_user_id,
        team_id=team.id,
        update={"is_favorite": True, "is_pinned": True},
    )

    deleted = await s.delete_team(team.id, owner_user_id=owner_user_id)

    assert deleted is True
    metadata = users[ObjectId(owner_user_id)]["metadata"]
    assert team.id not in metadata["favorite_team_ids"]
    assert team.id not in metadata["pinned_team_ids"]
