"""
MCP (Model Context Protocol) API router

Provides endpoints for managing MCP server configurations.
"""

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import require_permissions
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
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
admin_router = APIRouter()


# Dependency to get MCPStorage
async def get_mcp_storage() -> MCPStorage:
    return MCPStorage()


def _is_admin(user: TokenPayload) -> bool:
    """Check if user has admin permissions"""
    return "mcp:admin" in (user.permissions or [])


# ==========================================
# User API Endpoints - Static routes first
# ==========================================


@router.get("/", response_model=MCPServersResponse)
async def list_servers(
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Get all visible MCP servers (system + user's own)"""
    is_admin = _is_admin(user)
    servers = await storage.get_visible_servers(user.sub, is_admin)
    return MCPServersResponse(servers=servers)


@router.post("/", response_model=MCPServerResponse, status_code=201)
async def create_server(
    data: MCPServerCreate,
    user: TokenPayload = Depends(require_permissions("mcp:write")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Create a new user MCP server"""
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
        command=server.command,
        args=server.args,
        env=server.env,
        url=server.url,
        headers=server.headers,
        is_system=False,
        can_edit=True,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@router.post("/import", response_model=MCPImportResponse)
async def import_servers(
    data: MCPImportRequest,
    user: TokenPayload = Depends(require_permissions("mcp:write")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Import MCP servers from JSON configuration"""
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
            command=server.command,
            args=server.args,
            env=server.env,
            url=server.url,
            headers=server.headers,
            is_system=False,
            can_edit=True,
            created_at=server.created_at,
            updated_at=server.updated_at,
        )

    # Try system server
    system_server = await storage.get_system_server(name)
    if system_server:
        is_admin = _is_admin(user)
        return MCPServerResponse(
            name=system_server.name,
            transport=system_server.transport,
            enabled=system_server.enabled,
            command=system_server.command,
            args=system_server.args,
            env=system_server.env,
            url=system_server.url,
            headers=system_server.headers,
            is_system=True,
            can_edit=is_admin,
            created_at=system_server.created_at,
            updated_at=system_server.updated_at,
        )

    raise HTTPException(status_code=404, detail=f"Server '{name}' not found")


@router.put("/{name}", response_model=MCPServerResponse)
async def update_server(
    name: str,
    data: MCPServerUpdate,
    user: TokenPayload = Depends(require_permissions("mcp:write")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Update a user MCP server"""
    server = await storage.update_user_server(name, data, user.sub)
    if not server:
        raise HTTPException(
            status_code=404, detail=f"Server '{name}' not found or not owned by user"
        )

    return MCPServerResponse(
        name=server.name,
        transport=server.transport,
        enabled=server.enabled,
        command=server.command,
        args=server.args,
        env=server.env,
        url=server.url,
        headers=server.headers,
        is_system=False,
        can_edit=True,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@router.delete("/{name}")
async def delete_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:delete")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Delete a user MCP server"""
    deleted = await storage.delete_user_server(name, user.sub)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Server '{name}' not found or not owned by user"
        )
    return {"message": f"Server '{name}' deleted successfully"}


@router.patch("/{name}/toggle", response_model=MCPServerToggleResponse)
async def toggle_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:write")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Toggle a server's enabled status (user preferences for system servers)"""
    server = await storage.toggle_server(name, user.sub)

    if not server:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")

    status_text = "enabled" if server.enabled else "disabled"
    return MCPServerToggleResponse(
        server=server,
        message=f"Server '{name}' has been {status_text}",
    )


# ==========================================
# Admin API Endpoints - Static routes first
# ==========================================


@admin_router.get("/", response_model=MCPServersResponse)
async def admin_list_servers(
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Get all MCP servers (admin view - includes all system servers)"""
    servers = await storage.get_visible_servers(user.sub, is_admin=True)
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
        command=server.command,
        args=server.args,
        env=server.env,
        url=server.url,
        headers=server.headers,
        is_system=True,
        can_edit=True,
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
        command=server.command,
        args=server.args,
        env=server.env,
        url=server.url,
        headers=server.headers,
        is_system=True,
        can_edit=True,
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
        command=server.command,
        args=server.args,
        env=server.env,
        url=server.url,
        headers=server.headers,
        is_system=True,
        can_edit=True,
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
            status_code=400, detail="target_user_id is required to identify the user server"
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
            command=server.command,
            args=server.args,
            env=server.env,
            url=server.url,
            headers=server.headers,
            is_system=True,
            can_edit=True,
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
            status_code=400, detail="target_user_id is required to specify the new owner"
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
            command=server.command,
            args=server.args,
            env=server.env,
            url=server.url,
            headers=server.headers,
            is_system=False,
            can_edit=True,
            created_at=server.created_at,
            updated_at=server.updated_at,
        ),
        message=f"System server '{name}' has been demoted to user server",
        from_type="system",
        to_type="user",
    )
