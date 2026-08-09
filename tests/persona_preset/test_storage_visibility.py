from datetime import datetime

import pytest
from bson import ObjectId

from src.infra.persona_preset.storage import PersonaPresetStorage


def test_admin_visibility_query_keeps_user_presets_owner_scoped() -> None:
    query = PersonaPresetStorage._build_visible_query(
        user_id="admin-1",
        include_admin=True,
    )

    assert query == {
        "$or": [
            {"scope": "user", "owner_user_id": "admin-1"},
            {"scope": "global"},
        ]
    }


def test_admin_visibility_query_combines_scope_filter_with_owner_visibility() -> None:
    query = PersonaPresetStorage._build_visible_query(
        user_id="admin-1",
        include_admin=True,
        scope="user",
    )

    assert query == {
        "$or": [
            {"scope": "user", "owner_user_id": "admin-1"},
            {"scope": "global"},
        ],
        "scope": "user",
    }


def test_visible_query_splits_multi_word_search_into_keyword_terms() -> None:
    query = PersonaPresetStorage._build_visible_query(
        user_id="user-1",
        q="素材 内容 创意 设计",
    )

    search_clause = query["$and"][0]["$or"]
    assert search_clause[0]["$or"][0]["name"]["$regex"] != "素材 内容 创意 设计"
    terms = {list(item["$or"][0].values())[0]["$regex"] for item in search_clause}
    assert terms == {"素材", "内容", "创意", "设计"}


@pytest.mark.asyncio
async def test_list_visible_uses_bounded_aggregation_instead_of_materializing_find() -> None:
    user_id = str(ObjectId())
    preset_id = ObjectId()
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
            raise AssertionError("list_visible should not materialize an unbounded find cursor")

        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return _Cursor(
                [
                    {
                        "_id": preset_id,
                        "scope": "global",
                        "owner_user_id": None,
                        "name": "Planner",
                        "description": "Plan carefully",
                        "tags": ["planning"],
                        "system_prompt": "Plan first.",
                        "starter_prompts": [],
                        "skill_names": [],
                        "visibility": "public",
                        "status": "published",
                        "version": 1,
                        "usage_count": 5,
                        "created_at": datetime(2026, 1, 1),
                        "updated_at": datetime(2026, 1, 2),
                    }
                ]
            )

    class _UserCollection:
        async def find_one(self, _query, _projection=None):
            return {"metadata": {"pinned_preset_ids": [], "favorite_preset_ids": []}}

    storage = PersonaPresetStorage()
    storage._collection = _Collection()
    storage._user_collection = _UserCollection()

    docs = await storage.list_visible(user_id=user_id, skip=20, limit=10)

    assert [doc["name"] for doc in docs] == ["Planner"]
    assert {"$skip": 20} in pipelines[0]
    assert {"$limit": 10} in pipelines[0]


@pytest.mark.asyncio
async def test_list_visible_clamps_skip_and_limit_for_direct_storage_calls() -> None:
    user_id = str(ObjectId())
    pipelines: list[list[dict]] = []

    class _Cursor:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return _Cursor()

    class _UserCollection:
        async def find_one(self, _query, _projection=None):
            return {"metadata": {"pinned_preset_ids": [], "favorite_preset_ids": []}}

    storage = PersonaPresetStorage()
    storage._collection = _Collection()
    storage._user_collection = _UserCollection()

    docs = await storage.list_visible(user_id=user_id, skip=-10, limit=10_000)

    assert docs == []
    assert {"$skip": 0} in pipelines[0]
    assert {"$limit": 200} in pipelines[0]


@pytest.mark.asyncio
async def test_list_visible_bounds_large_user_preference_arrays() -> None:
    user_id = str(ObjectId())
    pipelines: list[list[dict]] = []

    class _Cursor:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return _Cursor()

    class _UserCollection:
        async def find_one(self, _query, _projection=None):
            return {
                "metadata": {
                    "pinned_preset_ids": [f"pin-{index}" for index in range(30)],
                    "favorite_preset_ids": [f"fav-{index}" for index in range(500)],
                }
            }

    storage = PersonaPresetStorage()
    storage._collection = _Collection()
    storage._user_collection = _UserCollection()

    docs = await storage.list_visible(user_id=user_id, skip=0, limit=10)

    assert docs == []
    add_fields = pipelines[0][1]["$addFields"]
    assert len(add_fields["is_pinned"]["$in"][1]) == storage.MAX_PINNED
    assert len(add_fields["is_favorite"]["$in"][1]) == storage.MAX_FAVORITES


@pytest.mark.asyncio
async def test_list_visible_reuses_preference_lookup_when_filtering_preferences() -> None:
    user_id = str(ObjectId())
    favorite_id = str(ObjectId())

    class _Cursor:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        def aggregate(self, _pipeline):
            return _Cursor()

    class _UserCollection:
        def __init__(self) -> None:
            self.find_calls = 0

        async def find_one(self, _query, _projection=None):
            self.find_calls += 1
            return {
                "metadata": {
                    "pinned_preset_ids": [],
                    "favorite_preset_ids": [favorite_id],
                }
            }

    user_collection = _UserCollection()
    storage = PersonaPresetStorage()
    storage._collection = _Collection()
    storage._user_collection = user_collection

    docs = await storage.list_visible(user_id=user_id, favorite=True)

    assert docs == []
    assert user_collection.find_calls == 1


@pytest.mark.asyncio
async def test_get_by_ids_deduplicates_valid_ids_and_uses_one_query() -> None:
    first_id = ObjectId()
    second_id = ObjectId()
    calls: list[tuple[dict, int]] = []

    class _Cursor:
        async def to_list(self, *, length: int):
            calls.append((query, length))
            return [
                {"_id": second_id, "name": "Second"},
                {"_id": first_id, "name": "First"},
            ]

    class _Collection:
        def find(self, value):
            nonlocal query
            query = value
            return _Cursor()

    query: dict = {}
    storage = PersonaPresetStorage()
    storage._collection = _Collection()

    result = await storage.get_by_ids([str(first_id), "invalid", str(second_id), str(first_id)])

    assert calls == [({"_id": {"$in": [first_id, second_id]}}, 2)]
    assert list(result) == [str(second_id), str(first_id)]
    assert result[str(first_id)]["name"] == "First"


@pytest.mark.asyncio
async def test_get_by_ids_skips_query_when_no_ids_are_valid() -> None:
    class _Collection:
        def find(self, _query):
            raise AssertionError("invalid identifiers must not reach MongoDB")

    storage = PersonaPresetStorage()
    storage._collection = _Collection()

    assert await storage.get_by_ids(["", "invalid", None]) == {}


@pytest.mark.asyncio
async def test_get_by_ids_bounds_the_lookup_set() -> None:
    captured_length = 0

    class _Cursor:
        async def to_list(self, *, length: int):
            nonlocal captured_length
            captured_length = length
            return []

    class _Collection:
        def find(self, _query):
            return _Cursor()

    storage = PersonaPresetStorage()
    storage._collection = _Collection()

    await storage.get_by_ids([str(ObjectId()) for _ in range(4_001)])

    assert captured_length == 4_000


@pytest.mark.asyncio
async def test_get_by_ids_propagates_storage_failures() -> None:
    class _Collection:
        def find(self, _query):
            raise RuntimeError("database unavailable")

    storage = PersonaPresetStorage()
    storage._collection = _Collection()

    with pytest.raises(RuntimeError, match="database unavailable"):
        await storage.get_by_ids([str(ObjectId())])


@pytest.mark.asyncio
async def test_persona_preset_storage_close_clears_collection_references() -> None:
    storage = PersonaPresetStorage()
    storage._collection = object()
    storage._user_collection = object()

    await storage.close()

    assert storage._collection is None
    assert storage._user_collection is None


@pytest.mark.asyncio
async def test_update_user_preference_rejects_favorite_overflow() -> None:
    user_id = str(ObjectId())
    preset_id = str(ObjectId())

    class _UserCollection:
        def __init__(self):
            self.update_calls = 0

        async def find_one(self, _query, _projection=None):
            return {
                "metadata": {
                    "pinned_preset_ids": [],
                    "favorite_preset_ids": [str(ObjectId()) for _ in range(100)],
                }
            }

        async def update_one(self, *_args, **_kwargs):
            self.update_calls += 1

    user_collection = _UserCollection()
    storage = PersonaPresetStorage()
    storage._user_collection = user_collection

    result = await storage.update_user_preference(
        user_id=user_id,
        preset_id=preset_id,
        update={"is_favorite": True},
    )

    assert result["is_favorite"] is False
    assert user_collection.update_calls == 0


def test_visible_query_treats_search_terms_as_literal_regex_fragments() -> None:
    query = PersonaPresetStorage._build_visible_query(user_id="user-1", q="A.B")

    regexes = [
        field["$regex"] for clause in query["$and"][0]["$or"] for field in clause["$or"][0].values()
    ]

    assert regexes[0] == "a\\.b"
