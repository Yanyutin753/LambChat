from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.mcp.storage import MCPStorage
from src.kernel.schemas.mcp import MCPServerCreate, MCPTransport


class _EmptyCursor:
    def __init__(self) -> None:
        self.limit_calls: list[int] = []

    def limit(self, value: int):
        self.limit_calls.append(value)
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _ListCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.index = 0
        self.limit_calls: list[int] = []

    def limit(self, value: int):
        self.limit_calls.append(value)
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.docs):
            raise StopAsyncIteration
        doc = self.docs[self.index]
        self.index += 1
        return doc


class _FilteringCursor(_ListCursor):
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        super().__init__(docs)
        self.max_items: int | None = None

    def limit(self, value: int):
        super().limit(value)
        self.max_items = value
        return self

    async def __anext__(self):
        if self.max_items is not None and self.index >= self.max_items:
            raise StopAsyncIteration
        return await super().__anext__()


class _RecordingCollection:
    def __init__(self) -> None:
        self.find_queries: list[dict[str, Any]] = []
        self.cursor = _EmptyCursor()

    def find(self, query: dict[str, Any]):
        self.find_queries.append(query)
        return self.cursor


class _ListCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.find_queries: list[dict[str, Any]] = []
        self.cursor = _ListCursor(docs)
        self.deleted_queries: list[dict[str, Any]] = []
        self.updated_queries: list[dict[str, Any]] = []
        self.inserted_docs: list[dict[str, Any]] = []

    def find(self, query: dict[str, Any]):
        self.find_queries.append(query)
        return self.cursor

    async def find_one(self, query: dict[str, Any]):
        return next(
            (
                doc
                for doc in self.cursor.docs
                if all(doc.get(key) == value for key, value in query.items())
            ),
            None,
        )

    async def delete_one(self, query: dict[str, Any]):
        self.deleted_queries.append(query)
        return SimpleNamespace(deleted_count=1)

    async def update_one(self, query: dict[str, Any], _update: dict[str, Any]):
        self.updated_queries.append(query)
        return SimpleNamespace(modified_count=1)

    async def insert_one(self, doc: dict[str, Any]):
        self.inserted_docs.append(doc)
        return SimpleNamespace(inserted_id="doc-1")


class _FilteringCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.find_queries: list[dict[str, Any]] = []

    @staticmethod
    def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, expected in query.items():
            if isinstance(expected, dict) and "$ne" in expected:
                if doc.get(key) == expected["$ne"]:
                    return False
            elif doc.get(key) != expected:
                return False
        return True

    def find(self, query: dict[str, Any]):
        self.find_queries.append(query)
        return _FilteringCursor([doc for doc in self.docs if self._matches(doc, query)])


class _DisabledToolsCollection:
    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def find_one(self, query: dict[str, Any]):
        return dict(self.doc)

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]):
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=1)


class _InsertRecordingCollection:
    def __init__(self) -> None:
        self.inserted_docs: list[dict[str, Any]] = []

    async def insert_one(self, doc: dict[str, Any]):
        self.inserted_docs.append(doc)
        return SimpleNamespace(inserted_id="doc-1")


def _mcp_doc(name: str = "server-1", user_id: str = "user-1") -> dict[str, Any]:
    return {
        "name": name,
        "transport": "streamable_http",
        "enabled": True,
        "url": "https://example.com/mcp",
        "headers": {"__encrypted__": "secret"},
        "user_id": user_id,
        "is_system": False,
        "disabled_tools": [],
        "created_at": "2026-04-25T00:00:00Z",
        "updated_at": "2026-04-25T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_list_user_servers_applies_storage_limit() -> None:
    from src.infra.mcp.storage import MCP_SERVER_LIST_LIMIT

    collection = _RecordingCollection()
    storage = MCPStorage()
    storage._user_collection = collection  # type: ignore[assignment]

    servers = await storage.list_user_servers("user-1")

    assert servers == []
    assert collection.find_queries == [{"user_id": "user-1", "transport": {"$ne": "sandbox"}}]
    assert collection.cursor.limit_calls == [MCP_SERVER_LIST_LIMIT]


@pytest.mark.asyncio
async def test_list_user_servers_offloads_secret_decryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.mcp import storage as mcp_storage

    calls: list[Any] = []
    collection = _ListCollection([_mcp_doc()])
    storage = MCPStorage()
    storage._user_collection = collection  # type: ignore[assignment]

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    def fake_decrypt_server_secrets(doc: dict[str, Any]) -> dict[str, Any]:
        decrypted = dict(doc)
        decrypted["headers"] = {"Authorization": "plain-secret"}
        return decrypted

    monkeypatch.setattr(mcp_storage, "run_blocking_io", fake_run_blocking_io, raising=False)
    monkeypatch.setattr(mcp_storage, "decrypt_server_secrets", fake_decrypt_server_secrets)

    servers = await storage.list_user_servers("user-1")

    assert calls == [mcp_storage.decrypt_server_secrets]
    assert servers[0].headers == {"Authorization": "plain-secret"}


@pytest.mark.asyncio
async def test_create_user_server_offloads_secret_encryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.mcp import storage as mcp_storage

    calls: list[object] = []
    collection = _InsertRecordingCollection()
    storage = MCPStorage()
    storage._user_collection = collection  # type: ignore[assignment]

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    async def _noop_invalidate_user_cache(_user_id: str) -> None:
        return None

    def fake_encrypt_server_secrets(doc: dict[str, Any]) -> dict[str, Any]:
        encrypted = dict(doc)
        encrypted["headers"] = {"Authorization": "encrypted-secret"}
        encrypted["_encrypted_by_test"] = True
        return encrypted

    monkeypatch.setattr(mcp_storage, "run_blocking_io", fake_run_blocking_io, raising=False)
    monkeypatch.setattr(mcp_storage, "encrypt_server_secrets", fake_encrypt_server_secrets)
    monkeypatch.setattr(storage, "_invalidate_user_cache", _noop_invalidate_user_cache)

    server = MCPServerCreate(
        name="server-1",
        transport=MCPTransport.STREAMABLE_HTTP,
        url="https://example.com/mcp",
        headers={"Authorization": "secret"},
    )

    created = await storage.create_user_server(server, "user-1")

    assert created.name == "server-1"
    assert collection.inserted_docs[0]["headers"] == {"Authorization": "encrypted-secret"}
    assert collection.inserted_docs[0]["_encrypted_by_test"] is True
    assert fake_encrypt_server_secrets in calls


@pytest.mark.asyncio
async def test_list_system_servers_omits_legacy_sandbox_documents() -> None:
    legacy = _mcp_doc(user_id="system")
    legacy["transport"] = "sandbox"
    legacy["headers"] = None
    collection = _ListCollection([legacy])
    storage = MCPStorage()
    storage._system_collection = collection  # type: ignore[assignment]

    servers = await storage.list_system_servers()

    assert servers == []
    assert collection.find_queries == [{"transport": {"$ne": "sandbox"}}]


@pytest.mark.asyncio
async def test_list_system_servers_filters_legacy_before_storage_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.mcp import storage as mcp_storage

    monkeypatch.setattr(mcp_storage, "MCP_SERVER_LIST_LIMIT", 1)
    legacy = _mcp_doc(name="legacy", user_id="system")
    legacy.update({"transport": "sandbox", "headers": None})
    valid = _mcp_doc(name="valid", user_id="system")
    valid["headers"] = None
    collection = _FilteringCollection([legacy, valid])
    storage = MCPStorage()
    storage._system_collection = collection  # type: ignore[assignment]

    servers = await storage.list_system_servers()

    assert [server.name for server in servers] == ["valid"]
    assert collection.find_queries == [{"transport": {"$ne": "sandbox"}}]


@pytest.mark.asyncio
async def test_legacy_system_server_is_hidden_but_reserves_its_name() -> None:
    legacy = _mcp_doc(user_id="system")
    legacy.update({"transport": "sandbox", "headers": None})
    collection = _ListCollection([legacy])
    storage = MCPStorage()
    storage._system_collection = collection  # type: ignore[assignment]

    assert await storage.get_system_server("server-1") is None
    assert await storage.system_server_name_exists("server-1") is True


@pytest.mark.asyncio
async def test_legacy_system_server_cannot_be_deleted_or_toggled() -> None:
    legacy = _mcp_doc(user_id="system")
    legacy.update({"transport": "sandbox", "headers": None})
    collection = _ListCollection([legacy])
    storage = MCPStorage()
    storage._system_collection = collection  # type: ignore[assignment]

    assert await storage.delete_system_server("server-1") is False
    assert await storage.toggle_system_server("server-1") is None
    assert collection.deleted_queries == []
    assert collection.updated_queries == []


@pytest.mark.asyncio
async def test_import_skips_hidden_legacy_name_even_with_overwrite() -> None:
    legacy = _mcp_doc()
    legacy.update({"transport": "sandbox", "headers": None})
    collection = _ListCollection([legacy])
    storage = MCPStorage()
    storage._user_collection = collection  # type: ignore[assignment]

    from src.kernel.schemas.mcp import MCPImportRequest

    result = await storage.import_servers(
        MCPImportRequest(
            servers={
                "server-1": {
                    "transport": "streamable_http",
                    "url": "https://replacement.example/mcp",
                }
            },
            overwrite=True,
        ),
        "user-1",
    )

    assert result == (0, 1, [])
    assert collection.inserted_docs == []
    assert collection.updated_queries == []


@pytest.mark.asyncio
async def test_export_all_servers_applies_storage_limit() -> None:
    from src.infra.mcp.storage import MCP_SERVER_LIST_LIMIT

    collection = _RecordingCollection()
    storage = MCPStorage()
    storage._system_collection = collection  # type: ignore[assignment]

    servers = await storage.export_all_servers()

    assert servers == {"mcpServers": {}}
    assert collection.find_queries == [{"transport": {"$ne": "sandbox"}}]
    assert collection.cursor.limit_calls == [MCP_SERVER_LIST_LIMIT]


@pytest.mark.asyncio
async def test_export_all_servers_offloads_config_decryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.mcp import storage as mcp_storage

    calls: list[Any] = []
    collection = _ListCollection([_mcp_doc(user_id="system")])
    storage = MCPStorage()
    storage._system_collection = collection  # type: ignore[assignment]

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    def fake_decrypt_server_secrets(doc: dict[str, Any]) -> dict[str, Any]:
        decrypted = dict(doc)
        decrypted["headers"] = {"Authorization": "plain-secret"}
        return decrypted

    monkeypatch.setattr(mcp_storage, "run_blocking_io", fake_run_blocking_io, raising=False)
    monkeypatch.setattr(mcp_storage, "decrypt_server_secrets", fake_decrypt_server_secrets)

    exported = await storage.export_all_servers()

    assert calls == [mcp_storage.decrypt_server_secrets]
    assert exported["mcpServers"]["server-1"]["headers"] == {"Authorization": "plain-secret"}


@pytest.mark.asyncio
async def test_get_tool_preferences_applies_storage_limit() -> None:
    from src.infra.mcp.storage import MCP_PREFERENCE_LIST_LIMIT

    collection = _RecordingCollection()
    storage = MCPStorage()
    storage._tool_preferences_collection = collection  # type: ignore[assignment]

    preferences = await storage.get_tool_preferences("user-1")

    assert preferences == {}
    assert collection.find_queries == [{"user_id": "user-1"}]
    assert collection.cursor.limit_calls == [MCP_PREFERENCE_LIST_LIMIT]


@pytest.mark.asyncio
async def test_list_tool_policies_applies_storage_limit() -> None:
    from src.infra.mcp.storage import MCP_TOOL_POLICY_LIST_LIMIT

    collection = _RecordingCollection()
    storage = MCPStorage()
    storage._tool_policies_collection = collection  # type: ignore[assignment]

    policies = await storage.list_tool_policies("server-1")

    assert policies == {}
    assert collection.find_queries == [{"server_name": "server-1"}]
    assert collection.cursor.limit_calls == [MCP_TOOL_POLICY_LIST_LIMIT]


@pytest.mark.asyncio
async def test_set_system_tool_disabled_bounds_historical_disabled_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _DisabledToolsCollection(
        {
            "name": "server-1",
            "disabled_tools": [f"tool-{index}" for index in range(130)] + ["tool-1"],
        }
    )
    storage = MCPStorage()
    storage._system_collection = collection  # type: ignore[assignment]

    async def _noop_invalidate_all_cache() -> None:
        return None

    monkeypatch.setattr(storage, "_invalidate_all_cache", _noop_invalidate_all_cache)

    await storage.set_system_tool_disabled("server-1", "tool-1", True)

    assert len(collection.updates) == 1
    disabled_tools = collection.updates[0][1]["$set"]["disabled_tools"]
    assert disabled_tools == [f"tool-{index}" for index in range(100)]


@pytest.mark.asyncio
async def test_set_user_server_tool_disabled_rejects_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _DisabledToolsCollection(
        {
            "name": "server-1",
            "user_id": "user-1",
            "disabled_tools": [f"tool-{index}" for index in range(100)],
        }
    )
    storage = MCPStorage()
    storage._user_collection = collection  # type: ignore[assignment]

    async def _noop_invalidate_user_cache(_user_id: str) -> None:
        return None

    monkeypatch.setattr(storage, "_invalidate_user_cache", _noop_invalidate_user_cache)

    with pytest.raises(ValueError, match="maximum 100"):
        await storage.set_user_server_tool_disabled("server-1", "new-tool", "user-1", True)

    assert collection.updates == []


@pytest.mark.asyncio
async def test_disabled_tool_readers_hide_legacy_servers() -> None:
    system_legacy = _mcp_doc(name="legacy-system", user_id="system")
    system_legacy.update(
        {"transport": "sandbox", "headers": None, "disabled_tools": ["hidden-tool"]}
    )
    user_legacy = _mcp_doc(name="legacy-user")
    user_legacy.update({"transport": "sandbox", "headers": None, "disabled_tools": ["hidden-tool"]})
    storage = MCPStorage()
    storage._system_collection = _ListCollection([system_legacy])  # type: ignore[assignment]
    storage._user_collection = _ListCollection([user_legacy])  # type: ignore[assignment]

    assert await storage.get_system_disabled_tools() == {}
    assert await storage.get_user_server_disabled_tools("user-1") == {}


@pytest.mark.asyncio
async def test_disabled_tool_setters_reject_legacy_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _mcp_doc()
    legacy.update({"transport": "sandbox", "headers": None})
    system_collection = _DisabledToolsCollection(legacy)
    user_collection = _DisabledToolsCollection(legacy)
    storage = MCPStorage()
    storage._system_collection = system_collection  # type: ignore[assignment]
    storage._user_collection = user_collection  # type: ignore[assignment]

    async def _fail_cache_invalidation(*_args) -> None:
        raise AssertionError("legacy server mutation must not invalidate caches")

    monkeypatch.setattr(storage, "_invalidate_all_cache", _fail_cache_invalidation)
    monkeypatch.setattr(storage, "_invalidate_user_cache", _fail_cache_invalidation)

    with pytest.raises(ValueError, match="not found"):
        await storage.set_system_tool_disabled("server-1", "tool-1", True)
    with pytest.raises(ValueError, match="not found"):
        await storage.set_user_server_tool_disabled("server-1", "tool-1", "user-1", True)

    assert system_collection.updates == []
    assert user_collection.updates == []


class _FakeMCPClientManager:
    def __init__(self, tools: list[Any]) -> None:
        self._tools = tools
        self.initialized_config: dict[str, Any] | None = None
        self.closed = False

    async def _initialize_with_config(self, config: dict[str, Any]) -> None:
        self.initialized_config = config

    async def close(self) -> None:
        self.closed = True


def _server() -> SimpleNamespace:
    return SimpleNamespace(
        name="server-1",
        transport=SimpleNamespace(value="sse"),
        url="https://example.com/mcp",
        headers=None,
        is_system=True,
        allowed_roles=[],
    )


@pytest.mark.asyncio
async def test_discover_server_tools_limits_tool_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.mcp import storage as mcp_storage

    monkeypatch.setattr(mcp_storage, "MCP_DISCOVER_TOOL_LIMIT", 3, raising=False)
    manager = _FakeMCPClientManager(
        [
            SimpleNamespace(name=f"server-1:tool-{index}", description="", args_schema=None)
            for index in range(5)
        ]
    )
    monkeypatch.setattr(
        "src.infra.tool.mcp_client.MCPClientManager",
        lambda use_database=False: manager,
    )
    storage = MCPStorage()

    async def _get_user_server(*_args):
        return None

    monkeypatch.setattr(storage, "get_user_server", _get_user_server)

    async def _get_system_server(_name: str):
        return _server()

    async def _empty_dict(*_args, **_kwargs):
        return {}

    async def _empty_set(*_args, **_kwargs):
        return set()

    monkeypatch.setattr(storage, "get_system_server", _get_system_server)
    monkeypatch.setattr(storage, "get_system_disabled_tools", _empty_dict)
    monkeypatch.setattr(storage, "get_disabled_tool_names", _empty_set)
    monkeypatch.setattr(storage, "list_tool_policies", _empty_dict)

    tools, error = await storage.discover_server_tools("server-1", "user-1")

    assert error is None
    assert [tool["name"] for tool in tools] == ["tool-0", "tool-1", "tool-2"]
    assert manager.closed is True


@pytest.mark.asyncio
async def test_discover_server_tools_limits_parameters_per_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.mcp import storage as mcp_storage

    monkeypatch.setattr(mcp_storage, "MCP_DISCOVER_TOOL_PARAMETER_LIMIT", 2, raising=False)

    class _Schema:
        @staticmethod
        def schema() -> dict[str, Any]:
            return {
                "properties": {
                    f"param_{index}": {"type": "string", "description": "demo"}
                    for index in range(5)
                },
                "required": ["param_0"],
            }

    manager = _FakeMCPClientManager(
        [SimpleNamespace(name="server-1:tool", description="", args_schema=_Schema())]
    )
    monkeypatch.setattr(
        "src.infra.tool.mcp_client.MCPClientManager",
        lambda use_database=False: manager,
    )
    storage = MCPStorage()

    async def _get_user_server(*_args):
        return None

    monkeypatch.setattr(storage, "get_user_server", _get_user_server)

    async def _get_system_server(_name: str):
        return _server()

    async def _empty_dict(*_args, **_kwargs):
        return {}

    async def _empty_set(*_args, **_kwargs):
        return set()

    monkeypatch.setattr(storage, "get_system_server", _get_system_server)
    monkeypatch.setattr(storage, "get_system_disabled_tools", _empty_dict)
    monkeypatch.setattr(storage, "get_disabled_tool_names", _empty_set)
    monkeypatch.setattr(storage, "list_tool_policies", _empty_dict)

    tools, error = await storage.discover_server_tools("server-1", "user-1")

    assert error is None
    assert [param["name"] for param in tools[0]["parameters"]] == ["param_0", "param_1"]
