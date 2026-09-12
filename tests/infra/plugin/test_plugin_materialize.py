from __future__ import annotations

from typing import Any, Optional

import pytest

from src.infra.plugin.materialize import (
    delete_plugin_mcp,
    disable_plugin_mcp,
    materialize_plugin_mcp,
)
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.mcp import MCPServerUpdate, MCPTransport, SystemMCPServer


class FakeMCPStorage:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.created: list[tuple[str, Optional[str]]] = []
        self.updated: list[tuple[str, bool]] = []
        self.deleted: list[str] = []

    async def get_system_server(self, name: str) -> Optional[SystemMCPServer]:
        doc = self.docs.get(name)
        if not doc:
            return None
        return SystemMCPServer(
            name=doc["name"],
            transport=MCPTransport(doc.get("transport", "streamable_http")),
            enabled=doc.get("enabled", True),
            url=doc.get("url"),
            headers=None,
            source_plugin=doc.get("source_plugin"),
        )

    async def create_system_server(self, server, admin_user_id: str, *, source_plugin=None):
        self.docs[server.name] = {
            "name": server.name,
            "transport": server.transport.value,
            "enabled": server.enabled,
            "url": server.url,
            "source_plugin": source_plugin,
        }
        self.created.append((server.name, source_plugin))
        return self.docs[server.name]

    async def update_system_server(self, name: str, updates: MCPServerUpdate, admin_user_id: str):
        doc = self.docs.get(name)
        if not doc:
            return None
        if updates.enabled is not None:
            doc["enabled"] = updates.enabled
        self.updated.append((name, updates.enabled))
        return doc

    async def delete_system_server(self, name: str):
        if name in self.docs:
            self.deleted.append(name)
            del self.docs[name]
            return True
        return False

    async def iter_system_servers_by_plugin(self, plugin_name: str):
        for doc in list(self.docs.values()):
            if doc.get("source_plugin") == plugin_name:
                yield SystemMCPServer(
                    name=doc["name"],
                    transport=MCPTransport(doc.get("transport", "streamable_http")),
                    enabled=doc.get("enabled", True),
                    url=doc.get("url"),
                    headers=None,
                    source_plugin=doc.get("source_plugin"),
                )


class FakePluginStorage:
    def __init__(self) -> None:
        self.decrypted: list[list[dict[str, Any]]] = []

    def decrypt_mcp_headers(self, servers: list[dict[str, Any]]):
        self.decrypted.append(servers)
        return [dict(server) for server in servers]


@pytest.mark.asyncio
async def test_materialize_creates_system_servers_with_source_marker() -> None:
    mcp = FakeMCPStorage()
    plugin_doc = {
        "name": "research-kit",
        "mcp_servers": [
            {"name": "arxiv", "transport": "streamable_http", "url": "https://arxiv", "ref": False}
        ],
    }
    created = await materialize_plugin_mcp(
        plugin_doc,
        admin_user_id="admin-1",
        mcp_storage=mcp,  # type: ignore[arg-type]
        plugin_storage=FakePluginStorage(),  # type: ignore[arg-type]
    )
    assert created == ["arxiv"]
    assert mcp.created == [("arxiv", "research-kit")]
    assert mcp.docs["arxiv"]["source_plugin"] == "research-kit"


@pytest.mark.asyncio
async def test_materialize_reactivates_own_servers_without_conflict() -> None:
    mcp = FakeMCPStorage()
    mcp.docs["arxiv"] = {
        "name": "arxiv",
        "transport": "streamable_http",
        "enabled": False,
        "url": "https://arxiv",
        "source_plugin": "research-kit",
    }
    plugin_doc = {
        "name": "research-kit",
        "mcp_servers": [
            {"name": "arxiv", "transport": "streamable_http", "url": "https://arxiv", "ref": False}
        ],
    }
    created = await materialize_plugin_mcp(
        plugin_doc,
        admin_user_id="admin-1",
        mcp_storage=mcp,  # type: ignore[arg-type]
        plugin_storage=FakePluginStorage(),  # type: ignore[arg-type]
    )
    assert created == ["arxiv"]
    assert mcp.docs["arxiv"]["enabled"] is True


@pytest.mark.asyncio
async def test_materialize_conflicts_on_foreign_server_name() -> None:
    mcp = FakeMCPStorage()
    mcp.docs["arxiv"] = {
        "name": "arxiv",
        "transport": "streamable_http",
        "enabled": True,
        "source_plugin": "other-plugin",
    }
    plugin_doc = {
        "name": "research-kit",
        "mcp_servers": [{"name": "arxiv", "transport": "sse", "url": "https://x", "ref": False}],
    }
    with pytest.raises(AppError) as excinfo:
        await materialize_plugin_mcp(
            plugin_doc,
            admin_user_id="admin-1",
            mcp_storage=mcp,  # type: ignore[arg-type]
            plugin_storage=FakePluginStorage(),  # type: ignore[arg-type]
        )
    assert excinfo.value.error_code == ErrorCode.PLUGIN_MCP_NAME_CONFLICT


@pytest.mark.asyncio
async def test_materialize_validates_ref_servers() -> None:
    mcp = FakeMCPStorage()
    plugin_doc = {
        "name": "research-kit",
        "mcp_servers": [{"name": "ghost", "ref": True}],
    }
    with pytest.raises(AppError) as excinfo:
        await materialize_plugin_mcp(
            plugin_doc,
            admin_user_id="admin-1",
            mcp_storage=mcp,  # type: ignore[arg-type]
            plugin_storage=FakePluginStorage(),  # type: ignore[arg-type]
        )
    assert excinfo.value.error_code == ErrorCode.PLUGIN_MCP_REF_NOT_FOUND


@pytest.mark.asyncio
async def test_disable_and_delete_plugin_mcp() -> None:
    mcp = FakeMCPStorage()
    mcp.docs["arxiv"] = {
        "name": "arxiv",
        "transport": "streamable_http",
        "enabled": True,
        "source_plugin": "research-kit",
    }
    mcp.docs["unrelated"] = {
        "name": "unrelated",
        "transport": "streamable_http",
        "enabled": True,
        "source_plugin": None,
    }

    assert await disable_plugin_mcp("research-kit", mcp_storage=mcp) == 1  # type: ignore[arg-type]
    assert mcp.docs["arxiv"]["enabled"] is False
    assert mcp.docs["unrelated"]["enabled"] is True

    assert await delete_plugin_mcp("research-kit", mcp_storage=mcp) == 1  # type: ignore[arg-type]
    assert "arxiv" not in mcp.docs
    assert "unrelated" in mcp.docs
