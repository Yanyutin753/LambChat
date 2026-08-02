from __future__ import annotations

import pytest

from src.infra.agent import config_storage, model_access


class _FakeCollection:
    def __init__(self, responses: list[dict | None]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[dict, dict | None]] = []

    async def find_one(self, query: dict | None = None, projection: dict | None = None):
        self.calls.append((query or {}, projection))
        return self.responses.pop(0) if self.responses else None


class _FakeRoleModelsCollection:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict | None]] = []

    async def find_one(self, query: dict | None = None, projection: dict | None = None):
        self.calls.append((query or {}, projection))
        return {
            "allowed_models": [
                f"model-{index}" for index in range(model_access.ROLE_MODEL_ACCESS_LIMIT + 25)
            ]
        }


class _FakeRoleAgentsCollection:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict | None]] = []

    async def find_one(self, query: dict | None = None, projection: dict | None = None):
        self.calls.append((query or {}, projection))
        return {
            "allowed_agents": [
                f"agent-{index}" for index in range(config_storage.ROLE_AGENT_ACCESS_LIMIT + 25)
            ]
        }


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.limit_calls: list[int] = []

    def limit(self, value: int):
        self.limit_calls.append(value)
        self.docs = self.docs[:value]
        return self

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for doc in self.docs:
            yield doc


class _FakeFindCollection:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.calls: list[tuple[tuple, dict]] = []
        self.cursor: _FakeCursor | None = None

    def find(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.cursor = _FakeCursor(self.docs)
        return self.cursor


class _RecordingUpdateCollection:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict, bool]] = []

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        self.calls.append((query, update, upsert))


class _RecordingCatalogCollection:
    """Fake catalog collection recording update_one / bulk_write / delete_many."""

    def __init__(self) -> None:
        self.update_one_calls: list[tuple[dict, dict, bool]] = []
        self.bulk_write_calls: list[list] = []
        self.bulk_write_ordered: list[bool] = []
        self.delete_many_calls: list[dict] = []

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        self.update_one_calls.append((query, update, upsert))

    async def bulk_write(self, operations, ordered: bool = False):
        self.bulk_write_calls.append(list(operations))
        self.bulk_write_ordered.append(ordered)

    async def delete_many(self, query: dict):
        self.delete_many_calls.append(query)


@pytest.mark.asyncio
async def test_is_agent_enabled_checks_catalog_agent_without_loading_all() -> None:
    storage = config_storage.AgentConfigStorage()
    catalog = _FakeCollection([{"_id": "catalog-agent"}])
    global_config = _FakeCollection([])
    storage._collections = {
        config_storage._COLL_AGENT_CATALOG_CONFIG: catalog,
        config_storage._COLL_AGENT_CONFIG: global_config,
    }

    assert await storage.is_agent_enabled("agent-1") is True

    assert catalog.calls == [
        (
            {
                "$or": [{"agent_id": "agent-1"}, {"id": "agent-1"}],
                "enabled": {"$ne": False},
            },
            {"_id": 1},
        )
    ]
    assert global_config.calls == []


@pytest.mark.asyncio
async def test_is_agent_enabled_uses_elem_match_for_legacy_global_config() -> None:
    storage = config_storage.AgentConfigStorage()
    catalog = _FakeCollection([None, None])
    global_config = _FakeCollection([{"_id": "global"}])
    storage._collections = {
        config_storage._COLL_AGENT_CATALOG_CONFIG: catalog,
        config_storage._COLL_AGENT_CONFIG: global_config,
    }

    assert await storage.is_agent_enabled("agent-1") is True

    assert catalog.calls[-1] == ({}, {"_id": 1})
    assert global_config.calls == [
        (
            {
                "type": "global",
                "agents": {
                    "$elemMatch": {
                        "id": "agent-1",
                        "enabled": True,
                    }
                },
            },
            {"_id": 1},
        )
    ]


@pytest.mark.asyncio
async def test_get_role_models_slices_allowed_models_in_mongo_projection() -> None:
    storage = config_storage.AgentConfigStorage()
    collection = _FakeRoleModelsCollection()
    storage._collections = {
        config_storage._COLL_ROLE_MODELS: collection,
    }

    role_models = await storage.get_role_models("role-1")

    assert role_models == [
        f"model-{index}" for index in range(model_access.ROLE_MODEL_ACCESS_LIMIT)
    ]
    assert collection.calls == [
        (
            {"role_id": "role-1"},
            {
                "allowed_models": {
                    "$slice": model_access.ROLE_MODEL_ACCESS_LIMIT,
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_role_agents_slices_allowed_agents_in_mongo_projection() -> None:
    storage = config_storage.AgentConfigStorage()
    collection = _FakeRoleAgentsCollection()
    storage._collections = {
        config_storage._COLL_ROLE_AGENTS: collection,
    }

    role_agents = await storage.get_role_agents("role-1")

    assert role_agents == [
        f"agent-{index}" for index in range(config_storage.ROLE_AGENT_ACCESS_LIMIT)
    ]
    assert collection.calls == [
        (
            {"role_id": "role-1"},
            {
                "allowed_agents": {
                    "$slice": config_storage.ROLE_AGENT_ACCESS_LIMIT,
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_set_role_agents_caps_written_allowed_agents() -> None:
    storage = config_storage.AgentConfigStorage()
    collection = _RecordingUpdateCollection()
    storage._collections = {
        config_storage._COLL_ROLE_AGENTS: collection,
    }
    agent_ids = [f"agent-{index}" for index in range(config_storage.ROLE_AGENT_ACCESS_LIMIT + 25)]

    written = await storage.set_role_agents("role-1", "Role", agent_ids)

    assert written == [f"agent-{index}" for index in range(config_storage.ROLE_AGENT_ACCESS_LIMIT)]
    payload = collection.calls[0][1]["$set"]
    assert payload["allowed_agents"] == written


@pytest.mark.asyncio
async def test_get_all_role_agents_caps_legacy_allowed_agents() -> None:
    storage = config_storage.AgentConfigStorage()
    collection = _FakeFindCollection(
        [
            {
                "role_id": "role-1",
                "role_name": "Role",
                "allowed_agents": [
                    f"agent-{index}" for index in range(config_storage.ROLE_AGENT_ACCESS_LIMIT + 25)
                ]
                + ["agent-1"],
            }
        ]
    )
    storage._collections = {
        config_storage._COLL_ROLE_AGENTS: collection,
    }

    mappings = await storage.get_all_role_agents()

    assert mappings == [
        {
            "role_id": "role-1",
            "role_name": "Role",
            "allowed_agents": [
                f"agent-{index}" for index in range(config_storage.ROLE_AGENT_ACCESS_LIMIT)
            ],
        }
    ]


@pytest.mark.asyncio
async def test_get_catalog_config_limits_documents_loaded() -> None:
    storage = config_storage.AgentConfigStorage()
    collection = _FakeFindCollection(
        [
            {
                "agent_id": f"agent-{index}",
                "name": f"Agent {index}",
                "enabled": True,
                "sort_order": index,
            }
            for index in range(5)
        ]
    )
    storage._collections = {
        config_storage._COLL_AGENT_CATALOG_CONFIG: collection,
    }

    configs = await storage.get_catalog_config()

    assert [config.id for config in configs] == [f"agent-{index}" for index in range(5)]
    assert collection.cursor.limit_calls == [config_storage.AGENT_CATALOG_LIST_LIMIT]


@pytest.mark.asyncio
async def test_get_all_role_agents_limits_documents_loaded() -> None:
    storage = config_storage.AgentConfigStorage()
    collection = _FakeFindCollection(
        [
            {
                "role_id": f"role-{index}",
                "role_name": f"Role {index}",
                "allowed_agents": ["agent-1"],
            }
            for index in range(5)
        ]
    )
    storage._collections = {
        config_storage._COLL_ROLE_AGENTS: collection,
    }

    mappings = await storage.get_all_role_agents()

    assert [mapping["role_id"] for mapping in mappings] == [f"role-{index}" for index in range(5)]
    assert collection.cursor.limit_calls == [config_storage.ROLE_AGENT_MAPPING_LIST_LIMIT]


@pytest.mark.asyncio
async def test_set_role_models_caps_written_allowed_models() -> None:
    storage = config_storage.AgentConfigStorage()
    collection = _RecordingUpdateCollection()
    storage._collections = {
        config_storage._COLL_ROLE_MODELS: collection,
    }
    model_ids = [f"model-{index}" for index in range(model_access.ROLE_MODEL_ACCESS_LIMIT + 25)]

    written = await storage.set_role_models("role-1", "Role", model_ids)

    assert written == [f"model-{index}" for index in range(model_access.ROLE_MODEL_ACCESS_LIMIT)]
    payload = collection.calls[0][1]["$set"]
    assert payload["allowed_models"] == written


@pytest.mark.asyncio
async def test_get_all_role_models_caps_legacy_allowed_models() -> None:
    storage = config_storage.AgentConfigStorage()
    collection = _FakeFindCollection(
        [
            {
                "role_id": "role-1",
                "role_name": "Role",
                "allowed_models": [
                    f"model-{index}" for index in range(model_access.ROLE_MODEL_ACCESS_LIMIT + 25)
                ]
                + ["model-1"],
            }
        ]
    )
    storage._collections = {
        config_storage._COLL_ROLE_MODELS: collection,
    }

    mappings = await storage.get_all_role_models()

    assert mappings == [
        {
            "role_id": "role-1",
            "role_name": "Role",
            "allowed_models": [
                f"model-{index}" for index in range(model_access.ROLE_MODEL_ACCESS_LIMIT)
            ],
        }
    ]


@pytest.mark.asyncio
async def test_get_all_role_models_limits_documents_loaded() -> None:
    storage = config_storage.AgentConfigStorage()
    collection = _FakeFindCollection(
        [
            {
                "role_id": f"role-{index}",
                "role_name": f"Role {index}",
                "allowed_models": ["model-1"],
            }
            for index in range(5)
        ]
    )
    storage._collections = {
        config_storage._COLL_ROLE_MODELS: collection,
    }

    mappings = await storage.get_all_role_models()

    assert [mapping["role_id"] for mapping in mappings] == [f"role-{index}" for index in range(5)]
    assert collection.cursor.limit_calls == [config_storage.ROLE_MODEL_MAPPING_LIST_LIMIT]


@pytest.mark.asyncio
async def test_set_catalog_config_uses_single_bulk_write() -> None:
    from src.kernel.schemas.agent import AgentCatalogConfig

    storage = config_storage.AgentConfigStorage()
    collection = _RecordingCatalogCollection()
    storage._collections = {
        config_storage._COLL_AGENT_CATALOG_CONFIG: collection,
    }
    agents = [
        AgentCatalogConfig(
            id=f"agent-{index}",
            name=f"Agent {index}",
            description=f"desc-{index}",
        )
        for index in range(3)
    ]

    returned = await storage.set_catalog_config(agents)

    assert returned == agents
    # Must not issue per-agent update_one calls any longer.
    assert collection.update_one_calls == []
    # Exactly one bulk_write carrying 3 UpdateOne operations.
    assert len(collection.bulk_write_calls) == 1
    operations = collection.bulk_write_calls[0]
    assert len(operations) == 3
    for operation, agent in zip(operations, agents):
        assert operation._filter == {"agent_id": agent.id}
        assert operation._upsert is True
    # delete_many keeps only registered agent ids.
    assert collection.delete_many_calls == [
        {"agent_id": {"$nin": [agent.id for agent in agents]}}
    ]
