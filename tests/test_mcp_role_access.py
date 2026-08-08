from collections.abc import AsyncIterator
from typing import Any

import pytest

from src.infra.mcp.storage_operations import StorageOperations
from src.kernel.schemas.mcp import (
    MCPImportRequest,
    MCPServerCreate,
    MCPServerResponse,
    MCPServerUpdate,
    MCPTransport,
)


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self.iterated = 0

    async def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        for doc in self._docs:
            self.iterated += 1
            yield doc


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self.cursors: list[_AsyncCursor] = []

    def find(self, query: dict[str, Any]) -> _AsyncCursor:
        cursor = _AsyncCursor(
            [
                doc
                for doc in self._docs
                if all(doc.get(key) == value for key, value in query.items())
            ]
        )
        self.cursors.append(cursor)
        return cursor

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for doc in self._docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None


class _FakeMCPStorage(StorageOperations):
    def __init__(
        self,
        system_docs: list[dict[str, Any]],
        user_docs: list[dict[str, Any]] | None = None,
    ) -> None:
        self._system_docs = system_docs
        self._user_docs = user_docs or []
        self._system_collection = _FakeCollection(self._system_docs)
        self._user_collection = _FakeCollection(self._user_docs)
        self.created_system_servers: list[MCPServerCreate] = []
        self.updated_system_servers: list[MCPServerUpdate] = []

    def _get_system_collection(self) -> _FakeCollection:
        return self._system_collection

    def _get_user_collection(self) -> _FakeCollection:
        return self._user_collection

    async def _get_user_preferences(self, user_id: str) -> dict[str, bool]:
        return {}

    def _doc_to_response(
        self,
        doc: dict[str, Any],
        is_system: bool,
        can_edit: bool,
        hide_sensitive: bool = False,
    ) -> MCPServerResponse:
        return MCPServerResponse(
            name=doc["name"],
            transport=MCPTransport(doc.get("transport", "streamable_http")),
            enabled=doc.get("enabled", True),
            url=doc.get("url"),
            headers=doc.get("headers"),
            is_system=is_system,
            can_edit=can_edit,
            allowed_roles=doc.get("allowed_roles", []),
            role_quotas=doc.get("role_quotas", {}),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )

    def _doc_to_config_dict(self, doc: dict[str, Any]) -> dict[str, Any]:
        return {"transport": doc.get("transport", "streamable_http")}

    async def get_system_server(self, name: str) -> None:
        return None

    async def get_user_server(self, name: str, user_id: str) -> None:
        return None

    async def system_server_name_exists(self, name: str) -> bool:
        return any(doc.get("name") == name for doc in self._system_docs)

    async def user_server_name_exists(self, name: str, user_id: str) -> bool:
        return any(
            doc.get("name") == name and doc.get("user_id") == user_id for doc in self._user_docs
        )

    async def create_system_server(
        self,
        server: MCPServerCreate,
        admin_user_id: str,
    ) -> None:
        self.created_system_servers.append(server)

    async def update_system_server(
        self,
        name: str,
        updates: MCPServerUpdate,
        admin_user_id: str,
    ) -> None:
        self.updated_system_servers.append(updates)

    async def _invalidate_all_cache(self) -> None:
        return None


@pytest.mark.asyncio
async def test_missing_user_roles_do_not_bypass_system_mcp_role_restrictions() -> None:
    storage = _FakeMCPStorage(
        [
            {
                "name": "open-server",
                "transport": "sse",
                "enabled": True,
                "allowed_roles": [],
            },
            {
                "name": "restricted-server",
                "transport": "sse",
                "enabled": True,
                "allowed_roles": ["developer"],
            },
        ]
    )

    visible_servers = await storage.get_visible_servers("user-1", user_roles=None)
    effective_config = await storage.get_effective_config("user-1", user_roles=None)

    assert [server.name for server in visible_servers] == ["open-server"]
    assert list(effective_config["mcpServers"]) == ["open-server"]


@pytest.mark.asyncio
async def test_matching_user_role_can_access_restricted_system_mcp_servers() -> None:
    storage = _FakeMCPStorage(
        [
            {
                "name": "restricted-server",
                "transport": "sse",
                "enabled": True,
                "allowed_roles": ["developer"],
            },
        ]
    )

    visible_servers = await storage.get_visible_servers("user-1", user_roles=["developer"])
    effective_config = await storage.get_effective_config("user-1", user_roles=["developer"])

    assert [server.name for server in visible_servers] == ["restricted-server"]
    assert list(effective_config["mcpServers"]) == ["restricted-server"]


@pytest.mark.asyncio
async def test_legacy_sandbox_servers_are_hidden_from_runtime_reads() -> None:
    storage = _FakeMCPStorage(
        [
            {
                "name": "legacy",
                "transport": "sandbox",
                "enabled": True,
                "allowed_roles": [],
            }
        ]
    )

    visible_servers = await storage.get_visible_servers("user-1")
    effective_config = await storage.get_effective_config("user-1")

    assert visible_servers == []
    assert effective_config == {"mcpServers": {}}


@pytest.mark.asyncio
async def test_visible_servers_stops_after_requested_limit() -> None:
    storage = _FakeMCPStorage(
        [
            {
                "name": f"server-{index}",
                "transport": "sse",
                "enabled": True,
                "allowed_roles": [],
            }
            for index in range(10)
        ]
    )

    visible_servers = await storage.get_visible_servers("user-1", limit=3)

    assert [server.name for server in visible_servers] == ["server-0", "server-1", "server-2"]
    assert storage._system_collection.cursors[0].iterated == 3


@pytest.mark.asyncio
async def test_can_access_server_denies_restricted_system_server_without_matching_role() -> None:
    storage = _FakeMCPStorage(
        [
            {
                "name": "restricted-server",
                "transport": "sse",
                "enabled": True,
                "allowed_roles": ["developer"],
            },
        ]
    )

    assert not await storage.can_access_server(
        "restricted-server",
        "user-1",
        user_roles=None,
    )


def test_create_schema_preserves_allowed_roles() -> None:
    server = MCPServerCreate.model_validate(
        {
            "name": "restricted-server",
            "transport": "sse",
            "enabled": True,
            "url": "https://example.test/sse",
            "allowed_roles": ["developer"],
        }
    )

    assert server.allowed_roles == ["developer"]


@pytest.mark.asyncio
async def test_admin_import_preserves_allowed_roles() -> None:
    storage = _FakeMCPStorage([])

    imported, skipped, errors = await storage.import_servers(
        MCPImportRequest(
            servers={
                "restricted-server": {
                    "transport": "sse",
                    "url": "https://example.test/sse",
                    "allowed_roles": ["developer"],
                }
            }
        ),
        user_id="admin-1",
        is_admin=True,
    )

    assert (imported, skipped, errors) == (1, 0, [])
    assert storage.created_system_servers[0].allowed_roles == ["developer"]
