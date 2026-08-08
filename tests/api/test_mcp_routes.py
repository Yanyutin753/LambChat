from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.api import deps as api_deps
from src.api.routes import mcp as mcp_route
from src.kernel.schemas.mcp import (
    MCPServerCreate,
    MCPServerResponse,
    MCPToolInfo,
    MCPTransport,
)
from src.kernel.schemas.user import TokenPayload


def _fake_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["mcp:read"],
    )


def _fake_admin() -> TokenPayload:
    return TokenPayload(
        sub="admin-1",
        username="admin",
        roles=["admin"],
        permissions=["mcp:read", "mcp:admin"],
    )


def _fake_mcp_import_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["mcp:read", "mcp:write_sse", "mcp:write_http"],
    )


def test_mcp_schema_rejects_sandbox_transport() -> None:
    with pytest.raises(ValidationError):
        MCPServerCreate.model_validate(
            {
                "name": "legacy",
                "transport": "sandbox",
                "enabled": True,
            }
        )


def test_mcp_schemas_do_not_expose_sandbox_command_fields() -> None:
    assert "command" not in MCPServerCreate.model_fields
    assert "env_keys" not in MCPServerCreate.model_fields
    assert "command" not in MCPServerResponse.model_fields
    assert "env_keys" not in MCPServerResponse.model_fields


@pytest.mark.asyncio
async def test_list_mcp_servers_returns_paginated_response() -> None:
    class _FakeStorage:
        async def get_visible_servers(self, user_id: str, is_admin: bool, user_roles, limit=None):
            assert user_id == "user-1"
            assert is_admin is False
            assert user_roles == ["user"]
            assert limit == 5
            return [
                MCPServerResponse(
                    name=f"server-{i}",
                    transport=MCPTransport.SSE,
                    enabled=True,
                    url=f"https://example.com/{i}",
                    headers=None,
                    is_system=False,
                    can_edit=True,
                    allowed_roles=[],
                    role_quotas={},
                    created_at=None,
                    updated_at=None,
                )
                for i in range(5)
            ]

    app = FastAPI()
    app.include_router(mcp_route.router, prefix="/api/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/mcp/?skip=2&limit=2&q=server")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 5
    assert payload["skip"] == 2
    assert payload["limit"] == 2
    assert [server["name"] for server in payload["servers"]] == ["server-2", "server-3"]


@pytest.mark.asyncio
async def test_admin_mcp_list_includes_internal_server() -> None:
    class _FakeStorage:
        async def get_visible_servers(self, user_id: str, is_admin: bool, user_roles, limit=None):
            assert is_admin is True
            assert limit == 21
            return []

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/admin/mcp/")

    assert response.status_code == 200
    payload = response.json()
    assert any(server["name"] == "lambchat_internal" for server in payload["servers"])


@pytest.mark.asyncio
async def test_admin_internal_tool_discovery_uses_internal_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_internal_tool_infos(*args, **kwargs):
        return [
            MCPToolInfo(
                name="image_generate",
                description="Generate images",
                parameters=[],
                policy_configured=True,
            )
        ]

    monkeypatch.setattr(
        "src.infra.tool.internal_registry.get_internal_tool_infos",
        fake_get_internal_tool_infos,
    )

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: object()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/admin/mcp/lambchat_internal/tools")

    assert response.status_code == 200
    payload = response.json()
    assert payload["server_name"] == "lambchat_internal"
    assert payload["count"] == 1
    assert payload["tools"][0]["name"] == "image_generate"


@pytest.mark.asyncio
async def test_import_mcp_servers_rejects_oversized_payload_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_route, "MCP_IMPORT_MAX_SERVERS", 2, raising=False)

    class _FakeStorage:
        async def import_servers(self, *args, **kwargs):
            raise AssertionError("oversized import should be rejected before storage")

    app = FastAPI()
    app.include_router(mcp_route.router, prefix="/api/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_mcp_import_user
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    payload = {
        "servers": {
            f"server-{i}": {
                "transport": "sse",
                "url": f"https://example.com/{i}",
            }
            for i in range(3)
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/mcp/import", json=payload)

    assert response.status_code == 413
    assert "too many MCP servers" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_mcp_servers_reports_sandbox_error_and_imports_http_entry() -> None:
    class _FakeStorage:
        async def import_servers(self, data, user_id: str, is_admin: bool):
            assert user_id == "user-1"
            assert is_admin is False
            assert set(data.get_servers()) == {"legacy", "http-server"}
            return 1, 0, ["Invalid transport 'sandbox' for server 'legacy'"]

    app = FastAPI()
    app.include_router(mcp_route.router, prefix="/api/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_mcp_import_user
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    payload = {
        "servers": {
            "legacy": {"transport": "sandbox", "command": "legacy-command"},
            "http-server": {
                "transport": "streamable_http",
                "url": "https://example.com/mcp",
            },
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/mcp/import", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "message": "Imported 1 server(s)",
        "imported_count": 1,
        "skipped_count": 0,
        "errors": ["Invalid transport 'sandbox' for server 'legacy'"],
    }


@pytest.mark.asyncio
async def test_import_mcp_servers_reports_malformed_transport_and_imports_http_entry() -> None:
    class _FakeStorage:
        async def import_servers(self, data, user_id: str, is_admin: bool):
            assert user_id == "user-1"
            assert is_admin is False
            assert set(data.get_servers()) == {"malformed", "http-server"}
            return 1, 0, ["Invalid transport '['bad']' for server 'malformed'"]

    app = FastAPI()
    app.include_router(mcp_route.router, prefix="/api/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_mcp_import_user
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    payload = {
        "servers": {
            "malformed": {"transport": ["bad"]},
            "http-server": {
                "transport": "streamable_http",
                "url": "https://example.com/mcp",
            },
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/mcp/import", json=payload)

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1
    assert response.json()["errors"] == ["Invalid transport '['bad']' for server 'malformed'"]


@pytest.mark.asyncio
async def test_admin_toggle_tool_returns_bad_request_for_disabled_tool_overflow() -> None:
    class _FakeStorage:
        async def get_system_server(self, _name: str):
            return object()

        async def set_system_tool_disabled(self, *_args, **_kwargs):
            raise ValueError("Too many disabled tools: maximum 100 allowed.")

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/api/admin/mcp/server-1/tools/tool-101",
            json={"enabled": False},
        )

    assert response.status_code == 400
    assert "maximum 100" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_toggle_tool_returns_not_found_for_hidden_legacy_server() -> None:
    class _FakeStorage:
        async def get_system_server(self, name: str):
            assert name == "legacy"
            return None

        async def set_system_tool_disabled(self, *_args, **_kwargs):
            raise AssertionError("hidden legacy server must not be mutated")

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/api/admin/mcp/legacy/tools/tool-1",
            json={"enabled": False},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_update_tool_policy_accepts_inline_exposure() -> None:
    class _FakeStorage:
        def __init__(self) -> None:
            self.calls = []

        async def get_system_server(self, name: str):
            assert name == "server-1"
            return object()

        async def set_tool_policy(self, **kwargs):
            self.calls.append(kwargs)
            from src.kernel.schemas.mcp import MCPToolPolicy

            return MCPToolPolicy(
                server_name=kwargs["server_name"],
                tool_name=kwargs["tool_name"],
                disabled=kwargs["disabled"],
                inline_exposure=kwargs["inline_exposure"],
            )

    storage = _FakeStorage()
    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/admin/mcp/server-1/tools/extract/policy",
            json={"disabled": False, "inline_exposure": True},
        )

    assert response.status_code == 200
    assert response.json()["inline_exposure"] is True
    assert storage.calls == [
        {
            "server_name": "server-1",
            "tool_name": "extract",
            "disabled": False,
            "inline_exposure": True,
            "allowed_roles": None,
            "role_quotas": None,
            "updated_by": "admin-1",
        }
    ]
