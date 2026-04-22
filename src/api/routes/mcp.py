"""
MCP (Model Context Protocol) API router

Provides endpoints for managing MCP server configurations.
"""

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import require_permissions
from src.infra.logging import get_logger
from src.infra.mcp.storage import MCPStorage
from src.kernel.schemas.mcp import (
    MCPExportResponse,
    MCPImportRequest,
    MCPImportResponse,
    MCPServerCreate,
    MCPServerMoveRequest,
    MCPServerMoveResponse,
    MCPServerResponse,
    MCPServersResponse,
    MCPServerToggleResponse,
    MCPServerUpdate,
    MCPToolDiscoveryResponse,
    MCPToolInfo,
    MCPToolToggleRequest,
    MCPToolToggleResponse,
)
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

router = APIRouter()
admin_router = APIRouter()


# Dependency to get MCPStorage
async def get_mcp_storage() -> MCPStorage:
    return MCPStorage()


def _is_admin(user: TokenPayload) -> bool:
    """Check if user has admin permissions"""
    return "mcp:admin" in (user.permissions or [])


def _has_permission_for_transport(user: TokenPayload, transport: str) -> bool:
    """
    Check if user has permission for a specific transport type.

    Permissions:
    - mcp:admin: can create any transport type
    - mcp:write_sse: can create SSE transport
    - mcp:write_http: can create streamable_http transport
    - mcp:write_sandbox: can create sandbox transport
    """
    if _is_admin(user):
        return True

    permissions = user.permissions or []

    if transport == "sse":
        return "mcp:write_sse" in permissions
    elif transport == "streamable_http":
        return "mcp:write_http" in permissions
    elif transport == "sandbox":
        return "mcp:write_sandbox" in permissions

    return False


# ==========================================
# User API Endpoints - Static routes first
# ==========================================


@router.get("/", response_model=MCPServersResponse)
async def list_servers(
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Get all visible MCP servers (system + user's own)"""
    servers = await storage.get_visible_servers(
        user.sub,
        is_admin=_is_admin(user),
        user_roles=user.roles,
    )
    return MCPServersResponse(servers=servers)


@router.post("/", response_model=MCPServerResponse, status_code=201)
async def create_server(
    data: MCPServerCreate,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Create a new MCP server (requires transport-specific permission)"""
    # Check permission for specific transport type
    if not _has_permission_for_transport(user, data.transport.value):
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied. Requires 'mcp:write_{data.transport.value}' or 'mcp:admin' permission.",
        )

    # Check if name already exists in user's servers
    existing = await storage.get_user_server(data.name, user.sub)
    if existing:
        raise HTTPException(status_code=400, detail=f"Server '{data.name}' already exists")

    # Also check system servers (users can't override with same name unless admin)
    system_existing = await storage.get_system_server(data.name)
    if system_existing:
        raise HTTPException(
            status_code=400,
            detail=f"Server '{data.name}' already exists as a system server",
        )

    server = await storage.create_user_server(data, user.sub)
    return MCPServerResponse(
        name=server.name,
        transport=server.transport,
        enabled=server.enabled,
        url=server.url,
        headers=server.headers,
        command=server.command,
        env_keys=server.env_keys,
        is_system=False,
        can_edit=True,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@router.post("/import", response_model=MCPImportResponse)
async def import_servers(
    data: MCPImportRequest,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Import MCP servers from JSON configuration (requires transport-specific permission)"""
    # Check permissions for each server's transport type
    servers = data.get_servers()
    for server_name, server_config in servers.items():
        transport = server_config.get("transport", "streamable_http")
        if not _has_permission_for_transport(user, transport):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied for server '{server_name}'. Requires 'mcp:write_{transport}' or 'mcp:admin' permission.",
            )

    imported, skipped, errors = await storage.import_servers(data, user.sub, is_admin=False)

    message = f"Imported {imported} server(s)"
    if skipped > 0:
        message += f", skipped {skipped} existing server(s)"

    return MCPImportResponse(
        message=message,
        imported_count=imported,
        skipped_count=skipped,
        errors=errors,
    )


@router.get("/export", response_model=MCPExportResponse)
async def export_servers(
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Export user's MCP servers as JSON configuration"""
    config = await storage.export_user_servers(user.sub)
    return MCPExportResponse(servers=config.get("mcpServers", {}))


# ==========================================
# User API Endpoints - Dynamic routes (with path parameters)
# MUST come after static routes to avoid route shadowing
# ==========================================


@router.get("/{name}", response_model=MCPServerResponse)
async def get_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Get a specific MCP server"""
    # Try user server first
    server = await storage.get_user_server(name, user.sub)
    if server:
        return MCPServerResponse(
            name=server.name,
            transport=server.transport,
            enabled=server.enabled,
            url=server.url,
            headers=server.headers,
            command=server.command,
            env_keys=server.env_keys,
            is_system=False,
            can_edit=True,
            created_at=server.created_at,
            updated_at=server.updated_at,
        )

    # Try system server
    system_server = await storage.get_system_server(name)
    if system_server:
        # Role-based access control: check if user can see this system server
        if system_server.allowed_roles and not _is_admin(user):
            if not set(user.roles).intersection(system_server.allowed_roles):
                raise HTTPException(status_code=404, detail=f"Server '{name}' not found")

        # Only the creator can see sensitive fields (url, headers, command, env_keys)
        is_creator = (system_server.created_by or system_server.updated_by) == user.sub
        return MCPServerResponse(
            name=system_server.name,
            transport=system_server.transport,
            enabled=system_server.enabled,
            url=system_server.url if is_creator else None,
            headers=system_server.headers if is_creator else None,
            command=system_server.command if is_creator else None,
            env_keys=system_server.env_keys if is_creator else None,
            is_system=True,
            can_edit=False,  # System servers are managed through admin routes
            allowed_roles=system_server.allowed_roles,
            role_quotas=system_server.role_quotas,
            created_at=system_server.created_at,
            updated_at=system_server.updated_at,
        )

    raise HTTPException(status_code=404, detail=f"Server '{name}' not found")


@router.put("/{name}", response_model=MCPServerResponse)
async def update_server(
    name: str,
    data: MCPServerUpdate,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Update a user-owned MCP server"""
    # If changing transport, check permission for the new transport type
    if data.transport is not None and not _has_permission_for_transport(user, data.transport.value):
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied. Requires 'mcp:write_{data.transport.value}' or 'mcp:admin' permission.",
        )

    server = await storage.update_user_server(name, data, user.sub)
    if not server:
        raise HTTPException(
            status_code=404, detail=f"Server '{name}' not found or not owned by user"
        )

    return MCPServerResponse(
        name=server.name,
        transport=server.transport,
        enabled=server.enabled,
        url=server.url,
        headers=server.headers,
        command=server.command,
        env_keys=server.env_keys,
        is_system=False,
        can_edit=True,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@router.delete("/{name}")
async def delete_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Delete a user-owned MCP server"""
    deleted = await storage.delete_user_server(name, user.sub)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Server '{name}' not found or not owned by user"
        )

    return {"message": f"Server '{name}' deleted successfully"}


@router.patch("/{name}/toggle", response_model=MCPServerToggleResponse)
async def toggle_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Toggle a server's enabled status (user servers: direct toggle; system servers: toggle user preference)"""
    server = await storage.toggle_server(
        name,
        user.sub,
        user_roles=user.roles,
        is_admin=_is_admin(user),
    )

    if not server:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")

    status_text = "enabled" if server.enabled else "disabled"
    return MCPServerToggleResponse(
        server=server,
        message=f"Server '{name}' has been {status_text}",
    )


# ==========================================
# Tool Discovery & Tool Toggle Endpoints
# ==========================================


@router.get("/{name}/tools", response_model=MCPToolDiscoveryResponse)
async def discover_server_tools(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """
    Dynamically discover tools available from a specific MCP server.

    Connects to the server and lists its available tools with descriptions and parameters.
    This endpoint does NOT use cache - it always probes the server directly.
    """
    tools, error = await storage.discover_server_tools(
        name,
        user.sub,
        user_roles=user.roles,
        is_admin=_is_admin(user),
    )

    return MCPToolDiscoveryResponse(
        server_name=name,
        tools=[MCPToolInfo(**t) for t in tools],
        count=len(tools),
        error=error,
    )


@router.patch("/{name}/tools/{tool_name}", response_model=MCPToolToggleResponse)
async def toggle_tool(
    name: str,
    tool_name: str,
    data: MCPToolToggleRequest,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """
    Toggle a specific tool's enabled status.

    Two levels controlled by the `level` field:
    - level=system (default): Server-level disable. System servers require creator.
      Sets system_disabled — tool is invisible to ALL users everywhere.
    - level=user: Per-user preference. Works for any server the user can see.
      Sets user_disabled — tool hidden from chat input but visible in preferences (re-enableable).
    """
    if not await storage.can_access_server(
        name,
        user.sub,
        user_roles=user.roles,
        is_admin=_is_admin(user),
    ):
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")

    if data.level == "user":
        # User-level preference: works for any server
        await storage.set_tool_preference(tool_name, name, user.sub, data.enabled)
    else:
        # System-level: only creators can toggle
        user_server = await storage.get_user_server(name, user.sub)
        if user_server:
            await storage.set_user_server_tool_disabled(name, tool_name, user.sub, not data.enabled)
        else:
            system_server = await storage.get_system_server(name)
            if not system_server:
                raise HTTPException(status_code=404, detail=f"Server '{name}' not found")

            is_creator = (system_server.created_by or system_server.updated_by) == user.sub
            if not is_creator:
                raise HTTPException(
                    status_code=403, detail="Only the creator can toggle tools on this server"
                )

            await storage.set_system_tool_disabled(name, tool_name, not data.enabled)

    status_text = "enabled" if data.enabled else "disabled"
    return MCPToolToggleResponse(
        server_name=name,
        tool_name=tool_name,
        enabled=data.enabled,
        message=f"Tool '{tool_name}' from server '{name}' has been {status_text}",
    )


# ==========================================
# Admin API Endpoints - Static routes first
# ==========================================


@admin_router.get("/", response_model=MCPServersResponse)
async def admin_list_servers(
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Get all MCP servers (admin view - includes all system servers, bypasses role filter)"""
    servers = await storage.get_visible_servers(user.sub, is_admin=True, user_roles=user.roles)
    return MCPServersResponse(servers=servers)


@admin_router.post("/", response_model=MCPServerResponse, status_code=201)
async def admin_create_server(
    data: MCPServerCreate,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Create a new system MCP server (admin only)"""
    existing = await storage.get_system_server(data.name)
    if existing:
        raise HTTPException(status_code=400, detail=f"System server '{data.name}' already exists")

    server = await storage.create_system_server(data, user.sub)
    return MCPServerResponse(
        name=server.name,
        transport=server.transport,
        enabled=server.enabled,
        url=server.url,
        headers=server.headers,
        command=server.command,
        env_keys=server.env_keys,
        is_system=True,
        can_edit=True,
        allowed_roles=server.allowed_roles,
        role_quotas=server.role_quotas,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@admin_router.get("/export", response_model=MCPExportResponse)
async def admin_export_servers(
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Export all system MCP servers as JSON configuration (admin only)"""
    config = await storage.export_all_servers()
    return MCPExportResponse(servers=config.get("mcpServers", {}))


# ==========================================
# Admin API Endpoints - Dynamic routes (with path parameters)
# MUST come after static routes to avoid route shadowing
# ==========================================


@admin_router.get("/{name}", response_model=MCPServerResponse)
async def admin_get_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Get a system MCP server (admin only)"""
    server = await storage.get_system_server(name)
    if not server:
        raise HTTPException(status_code=404, detail=f"System server '{name}' not found")

    return MCPServerResponse(
        name=server.name,
        transport=server.transport,
        enabled=server.enabled,
        url=server.url,
        headers=server.headers,
        command=server.command,
        env_keys=server.env_keys,
        is_system=True,
        can_edit=True,
        allowed_roles=server.allowed_roles,
        role_quotas=server.role_quotas,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@admin_router.put("/{name}", response_model=MCPServerResponse)
async def admin_update_server(
    name: str,
    data: MCPServerUpdate,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Update a system MCP server (admin only)"""
    server = await storage.update_system_server(name, data, user.sub)
    if not server:
        raise HTTPException(status_code=404, detail=f"System server '{name}' not found")

    return MCPServerResponse(
        name=server.name,
        transport=server.transport,
        enabled=server.enabled,
        url=server.url,
        headers=server.headers,
        command=server.command,
        env_keys=server.env_keys,
        is_system=True,
        can_edit=True,
        allowed_roles=server.allowed_roles,
        role_quotas=server.role_quotas,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@admin_router.delete("/{name}")
async def admin_delete_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Delete a system MCP server (admin only)"""
    deleted = await storage.delete_system_server(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"System server '{name}' not found")

    return {"message": f"System server '{name}' deleted successfully"}


@admin_router.patch("/{name}/toggle", response_model=MCPServerToggleResponse)
async def admin_toggle_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Toggle a system server's enabled status (admin only)"""
    server = await storage.toggle_system_server(name)

    if not server:
        raise HTTPException(status_code=404, detail=f"System server '{name}' not found")

    status_text = "enabled" if server.enabled else "disabled"
    return MCPServerToggleResponse(
        server=server,
        message=f"System server '{name}' has been {status_text}",
    )


@admin_router.patch("/{name}/tools/{tool_name}", response_model=MCPToolToggleResponse)
async def admin_toggle_tool(
    name: str,
    tool_name: str,
    data: MCPToolToggleRequest,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """
    Toggle a tool's system-level disabled status (admin only).

    This affects all users globally. When disabled=True, the tool is blocked
    for everyone and cannot be re-enabled by individual users.
    """
    await storage.set_system_tool_disabled(name, tool_name, not data.enabled)

    status_text = "enabled" if data.enabled else "disabled"
    return MCPToolToggleResponse(
        server_name=name,
        tool_name=tool_name,
        enabled=data.enabled,
        message=f"Tool '{tool_name}' from server '{name}' has been {status_text} globally",
    )


# ==========================================
# Server Type Conversion (Admin only)
# ==========================================


@admin_router.post("/{name}/promote", response_model=MCPServerMoveResponse)
async def promote_server(
    name: str,
    data: MCPServerMoveRequest,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """
    Promote a user server to system server (admin only).

    Requires the owner's user_id in request body to identify which user's server to promote.
    """
    if not data.target_user_id:
        raise HTTPException(
            status_code=400,
            detail="target_user_id is required to identify the user server",
        )

    server = await storage.promote_to_system_server(name, data.target_user_id, user.sub)

    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"User server '{name}' not found or system server with same name exists",
        )

    return MCPServerMoveResponse(
        server=MCPServerResponse(
            name=server.name,
            transport=server.transport,
            enabled=server.enabled,
            url=server.url,
            headers=server.headers,
            command=server.command,
            env_keys=server.env_keys,
            is_system=True,
            can_edit=True,
            allowed_roles=server.allowed_roles,
            role_quotas=server.role_quotas,
            created_at=server.created_at,
            updated_at=server.updated_at,
        ),
        message=f"Server '{name}' has been promoted to system server",
        from_type="user",
        to_type="system",
    )


@admin_router.post("/{name}/demote", response_model=MCPServerMoveResponse)
async def demote_server(
    name: str,
    data: MCPServerMoveRequest,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """
    Demote a system server to user server (admin only).

    Requires target_user_id in request body to specify who will own the server.
    """
    if not data.target_user_id:
        raise HTTPException(
            status_code=400,
            detail="target_user_id is required to specify the new owner",
        )

    server = await storage.demote_to_user_server(name, data.target_user_id, user.sub)

    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"System server '{name}' not found or user already has server with same name",
        )

    return MCPServerMoveResponse(
        server=MCPServerResponse(
            name=server.name,
            transport=server.transport,
            enabled=server.enabled,
            url=server.url,
            headers=server.headers,
            command=server.command,
            env_keys=server.env_keys,
            is_system=False,
            can_edit=True,
            created_at=server.created_at,
            updated_at=server.updated_at,
        ),
        message=f"System server '{name}' has been demoted to user server",
        from_type="system",
        to_type="user",
    )
