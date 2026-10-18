import json
import re
from datetime import datetime
from typing import Any

import pytest
from bson import ObjectId

from src.infra.role import storage as role_storage
from src.infra.role.storage import RoleStorage


async def test_default_role_refresh_preserves_administrator_configured_budgets(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    storage = RoleStorage()
    storage._collection = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(
        storage, "get_by_name", AsyncMock(return_value=SimpleNamespace(name="admin"))
    )
    monkeypatch.setattr(storage, "invalidate_cache", AsyncMock())
    monkeypatch.setattr(
        "src.infra.auth.rbac.RBACManager.get_default_roles",
        lambda self: [
            {"name": "admin", "permissions": [], "is_system": True, "limits": None},
        ],
    )
    await storage.init_default_roles()
    update = storage.collection.update_one.call_args.args[1]
    assert "limits" not in update["$set"]


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.closed = False

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        return True

    async def incr(self, key: str) -> int:
        next_value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(next_value)
        return next_value

    async def aclose(self) -> None:
        self.closed = True


class _FakeCollection:
    async def find_one(self, query: dict) -> dict | None:
        if query != {"name": "admin"}:
            return None
        return {
            "_id": "role-1",
            "name": "admin",
            "description": "Administrator",
            "permissions": [],
            "allowed_agents": [],
            "limits": None,
            "is_system": True,
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
        }


class _LargeAllowedAgentsCollection:
    async def find_one(self, query: dict) -> dict | None:
        if query != {"name": "large"}:
            return None
        return {
            "_id": "role-large",
            "name": "large",
            "description": "Large Role",
            "permissions": [],
            "allowed_agents": [
                f"agent-{index}" for index in range(role_storage.ROLE_ALLOWED_AGENTS_LIMIT + 25)
            ],
            "limits": None,
            "is_system": False,
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
        }


class _FakeRoleCursor:
    def __init__(self) -> None:
        self.operations: list[tuple[str, int | str]] = []

    def sort(self, field: str, direction: int):
        self.operations.append(("sort", field))
        self.operations.append(("direction", direction))
        return self

    def skip(self, skip: int):
        self.operations.append(("skip", skip))
        return self

    def limit(self, limit: int):
        self.operations.append(("limit", limit))
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _ListRoleCursor(_FakeRoleCursor):
    def __init__(self, docs: list[dict]) -> None:
        super().__init__()
        self._docs = docs
        self.limit_value: int | None = None

    def limit(self, limit: int):
        self.limit_value = limit
        return super().limit(limit)

    def __aiter__(self):
        self._iter = iter(self._docs[: self.limit_value or None])
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _ListRolesCollection:
    def __init__(self, docs: list[dict]) -> None:
        self.cursor = _ListRoleCursor(docs)

    def find(self, _query: dict):
        return self.cursor


class _SearchCollection:
    def __init__(self) -> None:
        self.find_query: dict | None = None
        self.count_query: dict | None = None
        self.cursor = _FakeRoleCursor()

    def find(self, query: dict):
        self.find_query = query
        return self.cursor

    async def count_documents(self, query: dict) -> int:
        self.count_query = query
        return 0


class _EmptyAsyncCursor:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _RecordingIdsCollection:
    def __init__(self) -> None:
        self.find_queries: list[dict[str, Any]] = []

    def find(self, query: dict[str, Any]):
        self.find_queries.append(query)
        return _EmptyAsyncCursor()


@pytest.mark.asyncio
async def test_get_by_name_uses_dedicated_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    isolated_pool_flags: list[bool] = []

    monkeypatch.setattr(
        "src.infra.role.storage.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or fake_redis,
    )

    storage = RoleStorage()
    storage._collection = _FakeCollection()

    role = await storage.get_by_name("admin")

    assert role is not None
    assert role.name == "admin"
    assert isolated_pool_flags == [True]


@pytest.mark.asyncio
async def test_close_role_cache_redis_closes_and_clears_dedicated_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(role_storage, "_role_cache_redis", fake_redis)

    await role_storage.close_role_cache_redis()

    assert fake_redis.closed is True
    assert role_storage._role_cache_redis is None


@pytest.mark.asyncio
async def test_get_by_name_caps_allowed_agents_from_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.infra.role.storage.create_redis_client",
        lambda isolated_pool=False: _FakeRedis(),
    )
    storage = RoleStorage()
    storage._collection = _LargeAllowedAgentsCollection()

    role = await storage.get_by_name("large")

    assert role is not None
    assert role.allowed_agents == [
        f"agent-{index}" for index in range(role_storage.ROLE_ALLOWED_AGENTS_LIMIT)
    ]


@pytest.mark.asyncio
async def test_get_by_name_caps_allowed_agents_from_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    fake_redis.values["role:obj_ver:large"] = "1"
    fake_redis.values["role:obj:large:v1"] = json.dumps(
        {
            "id": "role-large",
            "name": "large",
            "description": "Large Role",
            "permissions": [],
            "allowed_agents": [
                f"agent-{index}" for index in range(role_storage.ROLE_ALLOWED_AGENTS_LIMIT + 25)
            ],
            "limits": None,
            "is_system": False,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
    )
    monkeypatch.setattr(
        "src.infra.role.storage.create_redis_client",
        lambda isolated_pool=False: fake_redis,
    )
    storage = RoleStorage()
    storage._collection = _LargeAllowedAgentsCollection()

    role = await storage.get_by_name("large")

    assert role is not None
    assert role.allowed_agents == [
        f"agent-{index}" for index in range(role_storage.ROLE_ALLOWED_AGENTS_LIMIT)
    ]


@pytest.mark.asyncio
async def test_get_by_name_offloads_role_cache_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    fake_redis = _FakeRedis()
    fake_redis.values["role:obj_ver:admin"] = "1"
    fake_redis.values["role:obj:admin:v1"] = json.dumps(
        {
            "id": "role-1",
            "name": "admin",
            "description": "Administrator",
            "permissions": [],
            "allowed_agents": [],
            "limits": None,
            "is_system": True,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
    )

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(role_storage, "_role_cache_redis", None)
    monkeypatch.setattr(
        "src.infra.role.storage.create_redis_client",
        lambda isolated_pool=False: fake_redis,
    )
    monkeypatch.setattr(role_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)
    storage = RoleStorage()
    storage._collection = _FakeCollection()

    role = await storage.get_by_name("admin")

    assert calls == [json.loads]
    assert role is not None
    assert role.name == "admin"


@pytest.mark.asyncio
async def test_get_by_name_offloads_role_cache_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    fake_redis = _FakeRedis()

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(role_storage, "_role_cache_redis", None)
    monkeypatch.setattr(
        "src.infra.role.storage.create_redis_client",
        lambda isolated_pool=False: fake_redis,
    )
    monkeypatch.setattr(role_storage, "run_blocking_io", _fake_run_blocking_io, raising=False)
    storage = RoleStorage()
    storage._collection = _FakeCollection()

    role = await storage.get_by_name("admin")

    assert calls == [json.dumps]
    assert role is not None
    assert fake_redis.values["role:obj:admin:v0"].startswith('{"id": "role-1"')


@pytest.mark.asyncio
async def test_role_search_escapes_regex_metacharacters() -> None:
    storage = RoleStorage()
    collection = _SearchCollection()
    storage._collection = collection

    await storage.list_roles(q="A.B")
    await storage.count_roles(q="A.B")

    expected = re.escape("A.B")
    assert collection.find_query == {
        "$or": [
            {"name": {"$regex": expected, "$options": "i"}},
            {"description": {"$regex": expected, "$options": "i"}},
        ]
    }
    assert collection.count_query == collection.find_query


@pytest.mark.asyncio
async def test_list_roles_clamps_storage_limit() -> None:
    storage = RoleStorage()
    storage._collection = _ListRolesCollection(
        [
            {
                "_id": f"role-{index}",
                "name": f"role-{index}",
                "description": "Role",
                "permissions": [],
                "allowed_agents": [],
                "limits": None,
                "is_system": False,
                "created_at": datetime(2026, 1, 1),
                "updated_at": datetime(2026, 1, 1),
            }
            for index in range(250)
        ]
    )

    roles = await storage.list_roles(limit=10_000)

    assert len(roles) == 200
    assert storage.collection.cursor.limit_value == 200


@pytest.mark.asyncio
async def test_get_by_ids_caps_mongo_in_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(role_storage, "ROLE_BATCH_LOOKUP_LIMIT", 3, raising=False)
    storage = RoleStorage()
    collection = _RecordingIdsCollection()
    storage._collection = collection
    ids = [str(ObjectId()) for _ in range(5)]

    roles = await storage.get_by_ids(ids)

    assert roles == []
    assert len(collection.find_queries[0]["_id"]["$in"]) == 3


class _BatchRedis(_FakeRedis):
    def __init__(self):
        super().__init__()
        self.mget_calls = []
        self.writes = []
        self.pending = []

    async def mget(self, keys):
        self.mget_calls.append(keys)
        return [self.values.get(key) for key in keys]

    def pipeline(self, transaction=False):
        return self

    def set(self, key, value, ex=None):
        self.pending.append((key, value, ex))
        return self

    async def execute(self):
        self.writes.extend(self.pending)
        for key, value, _ex in self.pending:
            self.values[key] = value
        self.pending = []
        return []


class _BatchRoleCollection:
    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def find(self, query):
        self.queries.append(query)
        return _ListRoleCursor(
            [dict(doc) for doc in self.docs if doc["name"] in query["name"]["$in"]]
        )


def _role_doc(name):
    return {
        "_id": f"id-{name}",
        "name": name,
        "permissions": [],
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }


@pytest.mark.asyncio
async def test_get_by_names_batches_misses_with_bounded_input_order(monkeypatch):
    monkeypatch.setattr(role_storage, "ROLE_BATCH_LOOKUP_LIMIT", 3)
    redis = _BatchRedis()
    monkeypatch.setattr(role_storage, "_role_cache_redis", redis)
    storage = RoleStorage()
    collection = _BatchRoleCollection([_role_doc("third"), _role_doc("first")])
    storage._collection = collection

    roles = await storage.get_by_names(["first", "missing", "first", "third", "fourth"])

    assert [role.name for role in roles] == ["first", "third"]
    assert collection.queries == [{"name": {"$in": ["first", "missing", "third"]}}]
    assert len(redis.mget_calls) == 3
    assert {key for key, _value, _ex in redis.writes} == {
        "role:obj:first:v0",
        "role:obj:missing:v0",
        "role:obj:third:v0",
    }
    assert redis.values["role:obj:missing:v0"] == "null"

    collection.queries.clear()
    roles = await storage.get_by_names(["missing", "third", "first"])
    assert [role.name for role in roles] == ["third", "first"]
    assert collection.queries == []


@pytest.mark.asyncio
async def test_get_by_names_skips_stale_cache_write_when_version_changes(monkeypatch):
    class ChangingRedis(_BatchRedis):
        async def mget(self, keys):
            result = await super().mget(keys)
            return ["1"] if len(self.mget_calls) == 3 else result

    redis = ChangingRedis()
    monkeypatch.setattr(role_storage, "_role_cache_redis", redis)
    storage = RoleStorage()
    storage._collection = _BatchRoleCollection([_role_doc("first")])

    assert [role.name for role in await storage.get_by_names(["first"])] == ["first"]
    assert redis.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TimeoutError(), RuntimeError("redis unavailable")])
async def test_get_by_names_cache_failure_uses_one_authoritative_query(monkeypatch, failure):
    class UnavailableRedis(_BatchRedis):
        async def mget(self, keys):
            self.mget_calls.append(keys)
            raise failure

    redis = UnavailableRedis()
    monkeypatch.setattr(role_storage, "_role_cache_redis", redis)
    storage = RoleStorage()
    storage._collection = _BatchRoleCollection([_role_doc("first"), _role_doc("second")])

    assert [role.name for role in await storage.get_by_names(["second", "first"])] == [
        "second",
        "first",
    ]
    assert len(storage.collection.queries) == 1
    assert len(redis.mget_calls) == 1
    assert redis.writes == []


@pytest.mark.asyncio
async def test_role_manager_batches_all_names_preserving_duplicates(monkeypatch):
    from unittest.mock import AsyncMock

    from src.infra.role.manager import RoleManager
    from src.kernel.schemas.role import Role

    monkeypatch.setattr(role_storage, "ROLE_BATCH_LOOKUP_LIMIT", 2)
    manager = RoleManager()
    manager.storage.get_by_names = AsyncMock(
        side_effect=lambda names: [
            Role(id=f"role-{name}", name=name) for name in reversed(names) if name != "missing"
        ]
    )
    roles = await manager.get_roles_by_names(["first", "missing", "last", "first"])

    assert [role.name for role in roles] == ["first", "last", "first"]
    assert [call.args[0] for call in manager.storage.get_by_names.await_args_list] == [
        ["first", "missing"],
        ["last"],
    ]


@pytest.mark.asyncio
async def test_get_by_names_corrupt_cache_does_not_hide_other_roles(monkeypatch):
    redis = _BatchRedis()
    redis.values["role:obj:broken:v0"] = "invalid json"
    redis.values["role:obj:negative:v0"] = "null"
    monkeypatch.setattr(role_storage, "_role_cache_redis", redis)
    storage = RoleStorage()
    storage._collection = _BatchRoleCollection([_role_doc("broken"), _role_doc("fresh")])

    roles = await storage.get_by_names(["negative", "broken", "fresh"])

    assert [role.name for role in roles] == ["broken", "fresh"]
    assert storage.collection.queries == [{"name": {"$in": ["broken", "fresh"]}}]


async def test_create_invalidates_previously_cached_missing_role(monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.kernel.schemas.role import RoleCreate

    records = {}

    async def find_one(query):
        return deepcopy(records.get(query["name"]))

    async def insert_one(document):
        identifier = ObjectId()
        records[document["name"]] = {**deepcopy(document), "_id": identifier}
        return SimpleNamespace(inserted_id=identifier)

    monkeypatch.setattr(role_storage, "_get_redis", AsyncMock(return_value=_FakeRedis()))
    storage = RoleStorage()
    storage._collection = SimpleNamespace(find_one=find_one, insert_one=insert_one)
    assert await storage.get_by_name("new-role") is None
    created = await storage.create(RoleCreate(name="new-role", description="New role"))
    found = await storage.get_by_name("new-role")
    assert found is not None
    assert found.id == created.id
