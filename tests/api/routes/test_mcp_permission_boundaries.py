"""MCP maintenance does not imply credential export or access-policy administration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import mcp
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.mcp import (
    MCPServerCreate,
    MCPServerMoveRequest,
    MCPServerUpdate,
    MCPToolToggleRequest,
    MCPTransport,
    SystemMCPServer,
    UserMCPServer,
)
from src.kernel.schemas.user import TokenPayload


def _user(*permissions):
    return TokenPayload(
        sub="owner", username="owner", roles=["reader"], permissions=list(permissions)
    )


def _personal():
    return UserMCPServer(
        name="server",
        user_id="owner",
        transport=MCPTransport.SSE,
        url="https://user:secret@example.com/token/path?key=secret",
        headers={"Custom-Credential": "secret"},
    )


async def test_personal_put_checks_saved_transport_before_write():
    storage = SimpleNamespace(
        get_user_server=AsyncMock(return_value=_personal()),
        update_user_server=AsyncMock(return_value=_personal()),
    )
    with pytest.raises(AppError) as denied:
        await mcp.update_server(
            "server", MCPServerUpdate(url="https://new.example.com"), _user("mcp:read"), storage
        )
    assert denied.value.error_code == ErrorCode.MCP_WRITE_PERMISSION_DENIED
    storage.update_user_server.assert_not_awaited()


async def test_personal_toggle_requires_transport_write():
    storage = SimpleNamespace(
        get_user_server=AsyncMock(return_value=_personal()),
        toggle_server=AsyncMock(return_value=_personal()),
    )
    with pytest.raises(AppError):
        await mcp.toggle_server("server", _user("mcp:read"), storage)
    storage.toggle_server.assert_not_awaited()


async def test_historical_system_creator_cannot_change_global_tool_policy():
    server = SystemMCPServer(name="server", transport=MCPTransport.SSE, created_by="owner")
    storage = SimpleNamespace(
        can_access_server=AsyncMock(return_value=True),
        get_user_server=AsyncMock(return_value=None),
        get_system_server=AsyncMock(return_value=server),
        set_system_tool_disabled=AsyncMock(),
    )
    with pytest.raises(AppError):
        await mcp.toggle_tool(
            "server", "tool", MCPToolToggleRequest(enabled=False), _user("mcp:read"), storage
        )
    storage.set_system_tool_disabled.assert_not_awaited()


async def test_maintainer_cannot_change_system_access_policy():
    storage = SimpleNamespace(
        update_system_server=AsyncMock(
            return_value=SystemMCPServer(name="server", transport=MCPTransport.SSE)
        )
    )
    with pytest.raises(AppError) as denied:
        await mcp.admin_update_server(
            "server", MCPServerUpdate(allowed_roles=[]), _user("mcp:admin"), storage
        )
    assert denied.value.error_code == ErrorCode.PERMISSION_MISSING
    storage.update_system_server.assert_not_awaited()


async def test_admin_cannot_promote_another_users_private_credentials():
    storage = SimpleNamespace(promote_to_system_server=AsyncMock())
    with pytest.raises(AppError):
        await mcp.promote_server(
            "server",
            MCPServerMoveRequest(target_user_id="other"),
            _user("mcp:admin", "mcp:policy_manage"),
            storage,
        )
    storage.promote_to_system_server.assert_not_awaited()


async def test_config_read_masks_all_credentials():
    storage = SimpleNamespace(get_user_server=AsyncMock(return_value=_personal()))
    response = await mcp.get_server("server", _user("mcp:read"), storage)
    serialized = response.model_dump_json()
    assert "secret" not in serialized
    assert response.headers == {"Custom-Credential": "***"}


async def test_masked_update_keeps_existing_secret_values():
    saved = _personal()
    storage = SimpleNamespace(
        get_user_server=AsyncMock(return_value=saved),
        update_user_server=AsyncMock(return_value=saved),
    )
    response = await mcp.get_server("server", _user("mcp:read"), storage)
    await mcp.update_server(
        "server",
        MCPServerUpdate(url=response.url, headers=response.headers),
        _user("mcp:read", "mcp:write_sse"),
        storage,
    )
    update = storage.update_user_server.await_args.args[1]
    assert update.headers == saved.headers
    assert update.url == saved.url


async def test_maintainer_cannot_enable_public_system_server_without_policy_grant():
    storage = SimpleNamespace(
        system_server_name_exists=AsyncMock(return_value=False), create_system_server=AsyncMock()
    )
    with pytest.raises(AppError):
        await mcp.admin_create_server(
            MCPServerCreate(name="server", transport=MCPTransport.SSE), _user("mcp:admin"), storage
        )
    storage.create_system_server.assert_not_awaited()


def test_mcp_configuration_maintenance_does_not_imply_personal_write():
    assert not mcp._has_permission_for_transport(_user("mcp:admin"), "sse")


async def test_authority_audit_does_not_log_credentials(monkeypatch):
    server = _personal()
    storage = SimpleNamespace(
        export_user_servers=AsyncMock(return_value={"mcpServers": {"server": server.model_dump()}})
    )
    records = []
    monkeypatch.setattr(mcp.logger, "info", lambda *args, **kwargs: records.append(str(args)))
    await mcp.export_servers(_user("mcp:read", "mcp:export"), storage)
    assert "export_personal_credentials" in str(records)
    assert "owner" in str(records)
    assert "secret" not in str(records)
