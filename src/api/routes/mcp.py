"""
MCP (Model Context Protocol) API router

Provides endpoints for managing MCP server configurations.
"""

from fastapi import APIRouter, Depends, Query

from src.api.deps import require_permissions
from src.infra.auth.delegation import require_capability as _require_capability
from src.infra.logging import get_logger
from src.infra.mcp.audit import audit_mcp as _audit_mcp
from src.infra.mcp.audit import policy_changes as _policy_changes
from src.infra.mcp.redaction import MASKED_SECRET, preserve_mcp_secrets, redact_mcp_url
from src.infra.mcp.storage import MCPStorage
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.mcp import (
    MCPExportResponse,
    MCPImportRequest,
    MCPImportResponse,
    MCPServerCreate,
    MCPServerMoveRequest,
    MCPServerMoveResponse,
    MCPServerResponse,
    MCPServerRetestResponse,
    MCPServersResponse,
    MCPServerToggleResponse,
    MCPServerUpdate,
    MCPToolDiscoveryResponse,
    MCPToolInfo,
    MCPToolPolicy,
    MCPToolPolicyUpdate,
    MCPToolToggleRequest,
    MCPToolToggleResponse,
    MCPTransport,
)
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

router = APIRouter()
admin_router = APIRouter()

MCP_IMPORT_MAX_SERVERS = 100


# Dependency to get MCPStorage
async def get_mcp_storage() -> MCPStorage:
    return MCPStorage()


def _paginate_servers(
    servers: list[MCPServerResponse],
    *,
    skip: int,
    limit: int,
    q: str | None,
) -> MCPServersResponse:
    servers = sorted(
        (_redact_server(server) for server in servers), key=lambda server: server.name.lower()
    )
    if q:
        lowered = q.lower()
        servers = [server for server in servers if lowered in server.name.lower()]
    total = len(servers)
    return MCPServersResponse(
        servers=servers[skip : skip + limit],
        total=total,
        skip=skip,
        limit=limit,
    )


def _can_inspect_system(user: TokenPayload) -> bool:
    """Explicit configuration inspection, independent of execution role access."""
    return "mcp:system_read" in user.permissions


def _redact_server(server: MCPServerResponse) -> MCPServerResponse:
    return server.model_copy(
        update={
            "url": redact_mcp_url(server.url),
            "headers": {key: MASKED_SECRET for key in server.headers}
            if server.headers
            else server.headers,
        }
    )


def _is_internal_server(name: str) -> bool:
    from src.infra.tool.internal_registry import INTERNAL_MCP_SERVER_NAME

    return name == INTERNAL_MCP_SERVER_NAME


def _has_permission_for_transport(user: TokenPayload, transport: str) -> bool:
    """
    Check if user has permission for a specific transport type.

    Permissions:
    - mcp:write_sse: can create SSE transport
    - mcp:write_http: can create streamable_http transport
    """
    permissions = user.permissions or []

    if transport == "sse":
        return "mcp:write_sse" in permissions
    elif transport == "streamable_http":
        return "mcp:write_http" in permissions
    return False


# ==========================================
# User API Endpoints - Static routes first
# ==========================================


@router.get("", response_model=MCPServersResponse, include_in_schema=False)
@router.get("/", response_model=MCPServersResponse)
async def list_servers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    q: str | None = None,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Get all visible MCP servers (system + user's own)"""
    storage_limit = skip + limit + 1
    servers = await storage.get_visible_servers(
        user.sub,
        is_admin=_can_inspect_system(user),
        user_roles=user.roles,
        limit=storage_limit,
    )
    if _can_inspect_system(user):
        from src.infra.tool.internal_registry import build_internal_server_response

        servers.append(build_internal_server_response())
    return _paginate_servers(servers, skip=skip, limit=limit, q=q)


@router.post("", response_model=MCPServerResponse, status_code=201, include_in_schema=False)
@router.post("/", response_model=MCPServerResponse, status_code=201)
async def create_server(
    data: MCPServerCreate,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Create a new MCP server (requires transport-specific permission)"""
    if data.allowed_roles or data.role_quotas:
        raise AppError(ErrorCode.FORBIDDEN)
    # Check permission for specific transport type
    if not _has_permission_for_transport(user, data.transport.value):
        raise AppError(
            ErrorCode.MCP_WRITE_PERMISSION_DENIED,
            args={"permission": f"mcp:write_{data.transport.value}"},
        )

    # Check if name already exists in user's servers
    if await storage.user_server_name_exists(data.name, user.sub):
        raise AppError(ErrorCode.MCP_SERVER_EXISTS, args={"name": data.name})

    # Also check system servers (users can't override with same name unless admin)
    if await storage.system_server_name_exists(data.name):
        raise AppError(ErrorCode.MCP_SERVER_EXISTS_AS_SYSTEM, args={"name": data.name})

    server = await storage.create_user_server(data, user.sub)
    return _redact_server(
        MCPServerResponse(
            name=server.name,
            transport=server.transport,
            enabled=server.enabled,
            url=server.url,
            headers=server.headers,
            is_system=False,
            can_edit=True,
            created_at=server.created_at,
            updated_at=server.updated_at,
        )
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
    if len(servers) > MCP_IMPORT_MAX_SERVERS:
        raise AppError(ErrorCode.MCP_IMPORT_LIMIT, args={"max": MCP_IMPORT_MAX_SERVERS})

    for server_name, server_config in servers.items():
        transport = server_config.get("transport", "streamable_http")
        if not isinstance(transport, str) or transport not in {item.value for item in MCPTransport}:
            continue
        if not _has_permission_for_transport(user, transport):
            raise AppError(
                ErrorCode.MCP_SERVER_PERMISSION_DENIED,
                args={"name": server_name, "permission": f"mcp:write_{transport}"},
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
    user: TokenPayload = Depends(require_permissions("mcp:read", "mcp:export")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Export user's MCP servers as JSON configuration"""
    _audit_mcp(user, "export_personal_credentials", user.sub)
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
    if _is_internal_server(name):
        if not _can_inspect_system(user):
            raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})
        from src.infra.tool.internal_registry import build_internal_server_response

        return build_internal_server_response()

    # Try user server first
    server = await storage.get_user_server(name, user.sub)
    if server:
        return _redact_server(
            MCPServerResponse(
                name=server.name,
                transport=server.transport,
                enabled=server.enabled,
                url=server.url,
                headers=server.headers,
                is_system=False,
                can_edit=True,
                created_at=server.created_at,
                updated_at=server.updated_at,
            )
        )

    # Try system server
    system_server = await storage.get_system_server(name)
    if system_server:
        # Role-based access control: check if user can see this system server
        if system_server.allowed_roles and not _can_inspect_system(user):
            if not set(user.roles).intersection(system_server.allowed_roles):
                raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})

        # Connection details remain masked; historical authorship grants no authority.
        is_creator = (system_server.created_by or system_server.updated_by) == user.sub
        return _redact_server(
            MCPServerResponse(
                name=system_server.name,
                transport=system_server.transport,
                enabled=system_server.enabled,
                url=system_server.url if is_creator else None,
                headers=system_server.headers if is_creator else None,
                is_system=True,
                can_edit=False,  # System servers are managed through admin routes
                allowed_roles=system_server.allowed_roles,
                role_quotas=system_server.role_quotas,
                created_at=system_server.created_at,
                updated_at=system_server.updated_at,
            )
        )

    raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})


@router.put("/{name}", response_model=MCPServerResponse)
async def update_server(
    name: str,
    data: MCPServerUpdate,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Update a user-owned MCP server"""
    existing = await storage.get_user_server(name, user.sub)
    if not existing:
        raise AppError(ErrorCode.MCP_SERVER_NOT_OWNED, args={"name": name})
    transport = data.transport or existing.transport
    if not _has_permission_for_transport(user, transport):
        raise AppError(
            ErrorCode.MCP_WRITE_PERMISSION_DENIED,
            args={
                "permission": "mcp:write_sse" if transport == MCPTransport.SSE else "mcp:write_http"
            },
        )
    if data.model_fields_set.intersection({"allowed_roles", "role_quotas"}):
        raise AppError(ErrorCode.FORBIDDEN)
    data = preserve_mcp_secrets(data, existing)

    server = await storage.update_user_server(name, data, user.sub)
    if not server:
        raise AppError(ErrorCode.MCP_SERVER_NOT_OWNED, args={"name": name})

    return _redact_server(
        MCPServerResponse(
            name=server.name,
            transport=server.transport,
            enabled=server.enabled,
            url=server.url,
            headers=server.headers,
            is_system=False,
            can_edit=True,
            created_at=server.created_at,
            updated_at=server.updated_at,
        )
    )


@router.delete("/{name}")
async def delete_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:delete")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Delete a user-owned MCP server"""
    deleted = await storage.delete_user_server(name, user.sub)
    if not deleted:
        raise AppError(ErrorCode.MCP_SERVER_NOT_OWNED, args={"name": name})

    return {"message": f"Server '{name}' deleted successfully"}


@router.patch("/{name}/toggle", response_model=MCPServerToggleResponse)
async def toggle_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Toggle a server's enabled status (user servers: direct toggle; system servers: toggle user preference)"""
    existing = await storage.get_user_server(name, user.sub)
    if existing and not _has_permission_for_transport(user, existing.transport.value):
        raise AppError(
            ErrorCode.MCP_WRITE_PERMISSION_DENIED,
            args={
                "permission": "mcp:write_sse"
                if existing.transport == MCPTransport.SSE
                else "mcp:write_http"
            },
        )
    server = await storage.toggle_server(
        name,
        user.sub,
        user_roles=user.roles,
        is_admin=_can_inspect_system(user),
    )

    if not server:
        raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})

    status_text = "enabled" if server.enabled else "disabled"
    return MCPServerToggleResponse(
        server=_redact_server(server),
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
    if _is_internal_server(name):
        if not _can_inspect_system(user):
            raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})
        from src.infra.tool.internal_registry import get_internal_tool_infos

        internal_tools = await get_internal_tool_infos(
            user_id=user.sub,
            user_roles=user.roles,
            is_admin=True,
        )
        return MCPToolDiscoveryResponse(
            server_name=name,
            tools=internal_tools,
            count=len(internal_tools),
            error=None,
        )
    else:
        tools, error = await storage.discover_server_tools(
            name,
            user.sub,
            user_roles=user.roles,
            is_admin=_can_inspect_system(user),
        )

    return MCPToolDiscoveryResponse(
        server_name=name,
        tools=[MCPToolInfo(**t) for t in tools],
        count=len(tools),
        error=error,
    )


@router.post("/{name}/retest", response_model=MCPServerRetestResponse)
async def retest_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """
    Retest one MCP server connection and persist the load status (issue #991).

    Soft-failure style: a failed probe still returns 200 with status="failed"
    and the error detail, mirroring the tool-discovery endpoint. A successful
    retest also resets the consecutive-failure counter.
    """
    if _is_internal_server(name):
        raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})

    ok, latency_ms, tool_count, error, scope = await storage.probe_server_connection(
        name,
        user.sub,
        user_roles=user.roles,
        is_admin=_can_inspect_system(user),
    )
    if scope is None:
        raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})

    try:
        if scope == "user":
            await storage.update_user_server_load_status(name, user.sub, ok=ok, error=error)
        else:
            await storage.update_system_server_load_status(name, ok=ok, error=error)
    except Exception as e:
        # 状态落库失败不应让探测结果不可见
        logger.warning(f"[MCP] Failed to persist load status for server '{name}': {e}")

    return MCPServerRetestResponse(
        server_name=name,
        status="ok" if ok else "failed",
        latency_ms=latency_ms,
        tool_count=tool_count,
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
    if _is_internal_server(name):
        _require_capability(user, "mcp:policy_manage")
        await storage.set_tool_policy(
            server_name=name,
            tool_name=tool_name,
            disabled=not data.enabled,
            updated_by=user.sub,
        )
    elif data.level == "user":
        if not await storage.can_access_server(
            name,
            user.sub,
            user_roles=user.roles,
            is_admin=_can_inspect_system(user),
        ):
            raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})

        # User-level preference: works for any server
        await storage.set_tool_preference(tool_name, name, user.sub, data.enabled)
    else:
        if not await storage.can_access_server(
            name,
            user.sub,
            user_roles=user.roles,
            is_admin=_can_inspect_system(user),
        ):
            raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})

        # Configuration ownership and current global policy authority are separate.
        user_server = await storage.get_user_server(name, user.sub)
        if user_server:
            if not _has_permission_for_transport(user, user_server.transport.value):
                raise AppError(ErrorCode.MCP_WRITE_PERMISSION_DENIED)
            try:
                await storage.set_user_server_tool_disabled(
                    name, tool_name, user.sub, not data.enabled
                )
            except ValueError as e:
                raise AppError(ErrorCode.MCP_SERVER_ERROR, message=str(e))
        else:
            system_server = await storage.get_system_server(name)
            if not system_server:
                raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})

            _require_capability(user, "mcp:policy_manage")

            try:
                await storage.set_system_tool_disabled(name, tool_name, not data.enabled)
            except ValueError as e:
                raise AppError(ErrorCode.MCP_SERVER_ERROR, message=str(e))

    if _is_internal_server(name) or data.level != "user":
        _audit_mcp(
            user,
            "toggle_tool_policy",
            name + ":" + tool_name,
            fields=["enabled"],
            changes={"enabled": data.enabled},
        )
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
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    q: str | None = None,
    user: TokenPayload = Depends(require_permissions("mcp:system_read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Get all MCP servers (admin view - includes all system servers, bypasses role filter)"""
    storage_limit = skip + limit + 1
    servers = await storage.get_visible_servers(
        user.sub,
        is_admin=True,
        user_roles=user.roles,
        limit=storage_limit,
    )
    from src.infra.tool.internal_registry import build_internal_server_response

    servers.append(build_internal_server_response())
    return _paginate_servers(servers, skip=skip, limit=limit, q=q)


@admin_router.post("/", response_model=MCPServerResponse, status_code=201)
async def admin_create_server(
    data: MCPServerCreate,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Create a new system MCP server (admin only)"""
    if data.enabled or data.allowed_roles or data.role_quotas:
        _require_capability(user, "mcp:policy_manage")
    if await storage.system_server_name_exists(data.name):
        raise AppError(ErrorCode.MCP_SYSTEM_SERVER_EXISTS, args={"name": data.name})

    server = await storage.create_system_server(data, user.sub)
    _audit_mcp(
        user,
        "create_system_server",
        data.name,
        fields=data.model_fields_set,
        changes=_policy_changes(data),
    )
    return _redact_server(
        MCPServerResponse(
            name=server.name,
            transport=server.transport,
            enabled=server.enabled,
            url=server.url,
            headers=server.headers,
            is_system=True,
            can_edit=True,
            allowed_roles=server.allowed_roles,
            role_quotas=server.role_quotas,
            created_at=server.created_at,
            updated_at=server.updated_at,
        )
    )


@admin_router.get("/export", response_model=MCPExportResponse)
async def admin_export_servers(
    user: TokenPayload = Depends(require_permissions("mcp:system_read", "mcp:export")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Export all system MCP servers as JSON configuration (admin only)"""
    _audit_mcp(user, "export_system_credentials", "system")
    config = await storage.export_all_servers()
    return MCPExportResponse(servers=config.get("mcpServers", {}))


@admin_router.get("/{name}/tools", response_model=MCPToolDiscoveryResponse)
async def admin_discover_server_tools(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:system_read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Discover tools for a system or internal MCP server (admin only)."""
    if _is_internal_server(name):
        from src.infra.tool.internal_registry import get_internal_tool_infos

        internal_tools = await get_internal_tool_infos(
            user_id=user.sub,
            user_roles=user.roles,
            is_admin=True,
        )
        return MCPToolDiscoveryResponse(
            server_name=name,
            tools=internal_tools,
            count=len(internal_tools),
            error=None,
        )

    tools, error = await storage.discover_server_tools(
        name,
        user.sub,
        user_roles=user.roles,
        is_admin=True,
    )
    return MCPToolDiscoveryResponse(
        server_name=name,
        tools=[MCPToolInfo(**t) for t in tools],
        count=len(tools),
        error=error,
    )


@admin_router.post("/{name}/retest", response_model=MCPServerRetestResponse)
async def admin_retest_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:system_read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Retest a system MCP server connection and persist the load status (admin only)."""
    if _is_internal_server(name):
        raise AppError(ErrorCode.MCP_SERVER_NOT_FOUND, args={"name": name})

    ok, latency_ms, tool_count, error, scope = await storage.probe_server_connection(
        name,
        user.sub,
        user_roles=user.roles,
        is_admin=True,
        system_only=True,
    )
    if scope is None:
        raise AppError(ErrorCode.MCP_SYSTEM_SERVER_NOT_FOUND, args={"name": name})

    try:
        if scope == "user":
            await storage.update_user_server_load_status(name, user.sub, ok=ok, error=error)
        else:
            await storage.update_system_server_load_status(name, ok=ok, error=error)
    except Exception as e:
        logger.warning(f"[MCP] Failed to persist load status for server '{name}': {e}")

    return MCPServerRetestResponse(
        server_name=name,
        status="ok" if ok else "failed",
        latency_ms=latency_ms,
        tool_count=tool_count,
        error=error,
    )


# ==========================================
# Admin API Endpoints - Dynamic routes (with path parameters)
# MUST come after static routes to avoid route shadowing
# ==========================================


@admin_router.get("/{name}", response_model=MCPServerResponse)
async def admin_get_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:system_read")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Get a system MCP server (admin only)"""
    if _is_internal_server(name):
        from src.infra.tool.internal_registry import build_internal_server_response

        return build_internal_server_response()

    server = await storage.get_system_server(name)
    if not server:
        raise AppError(ErrorCode.MCP_SYSTEM_SERVER_NOT_FOUND, args={"name": name})

    return _redact_server(
        MCPServerResponse(
            name=server.name,
            transport=server.transport,
            enabled=server.enabled,
            url=server.url,
            headers=server.headers,
            is_system=True,
            can_edit=True,
            allowed_roles=server.allowed_roles,
            role_quotas=server.role_quotas,
            created_at=server.created_at,
            updated_at=server.updated_at,
        )
    )


@admin_router.put("/{name}", response_model=MCPServerResponse)
async def admin_update_server(
    name: str,
    data: MCPServerUpdate,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Update a system MCP server (admin only)"""
    if data.model_fields_set.intersection({"enabled", "allowed_roles", "role_quotas"}):
        _require_capability(user, "mcp:policy_manage")
    existing = await storage.get_system_server(name)
    if not existing:
        raise AppError(ErrorCode.MCP_SYSTEM_SERVER_NOT_FOUND, args={"name": name})
    data = preserve_mcp_secrets(data, existing)
    server = await storage.update_system_server(name, data, user.sub)
    _audit_mcp(
        user,
        "update_system_server",
        name,
        fields=data.model_fields_set,
        changes=_policy_changes(data),
    )
    if not server:
        raise AppError(ErrorCode.MCP_SYSTEM_SERVER_NOT_FOUND, args={"name": name})

    return _redact_server(
        MCPServerResponse(
            name=server.name,
            transport=server.transport,
            enabled=server.enabled,
            url=server.url,
            headers=server.headers,
            is_system=True,
            can_edit=True,
            allowed_roles=server.allowed_roles,
            role_quotas=server.role_quotas,
            created_at=server.created_at,
            updated_at=server.updated_at,
        )
    )


@admin_router.delete("/{name}")
async def admin_delete_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:system_delete")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Delete a system MCP server (admin only)"""
    deleted = await storage.delete_system_server(name)
    _audit_mcp(user, "delete_system_server", name, fields=())
    if not deleted:
        raise AppError(ErrorCode.MCP_SYSTEM_SERVER_NOT_FOUND, args={"name": name})

    return {"message": f"System server '{name}' deleted successfully"}


@admin_router.patch("/{name}/toggle", response_model=MCPServerToggleResponse)
async def admin_toggle_server(
    name: str,
    user: TokenPayload = Depends(require_permissions("mcp:admin")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Toggle a system server's enabled status (admin only)"""
    _require_capability(user, "mcp:policy_manage")
    server = await storage.toggle_system_server(name)
    _audit_mcp(user, "toggle_system_server", name, fields=["enabled"])

    if not server:
        raise AppError(ErrorCode.MCP_SYSTEM_SERVER_NOT_FOUND, args={"name": name})

    status_text = "enabled" if server.enabled else "disabled"
    return MCPServerToggleResponse(
        server=_redact_server(server),
        message=f"System server '{name}' has been {status_text}",
    )


@admin_router.patch("/{name}/tools/{tool_name}", response_model=MCPToolToggleResponse)
async def admin_toggle_tool(
    name: str,
    tool_name: str,
    data: MCPToolToggleRequest,
    user: TokenPayload = Depends(require_permissions("mcp:policy_manage")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """
    Toggle a tool's system-level disabled status (admin only).

    This affects all users globally. When disabled=True, the tool is blocked
    for everyone and cannot be re-enabled by individual users.
    """
    if _is_internal_server(name):
        await storage.set_tool_policy(
            server_name=name,
            tool_name=tool_name,
            disabled=not data.enabled,
            updated_by=user.sub,
        )
    else:
        server = await storage.get_system_server(name)
        if not server:
            raise AppError(ErrorCode.MCP_SYSTEM_SERVER_NOT_FOUND, args={"name": name})
        try:
            await storage.set_system_tool_disabled(name, tool_name, not data.enabled)
        except ValueError as e:
            raise AppError(ErrorCode.MCP_SERVER_ERROR, message=str(e))

    _audit_mcp(
        user,
        "toggle_tool_policy",
        name + ":" + tool_name,
        fields=["enabled"],
        changes={"enabled": data.enabled},
    )
    status_text = "enabled" if data.enabled else "disabled"
    return MCPToolToggleResponse(
        server_name=name,
        tool_name=tool_name,
        enabled=data.enabled,
        message=f"Tool '{tool_name}' from server '{name}' has been {status_text} globally",
    )


@admin_router.put("/{name}/tools/{tool_name}/policy", response_model=MCPToolPolicy)
async def admin_update_tool_policy(
    name: str,
    tool_name: str,
    data: MCPToolPolicyUpdate,
    user: TokenPayload = Depends(require_permissions("mcp:policy_manage")),
    storage: MCPStorage = Depends(get_mcp_storage),
):
    """Update role access and quotas for one MCP tool (admin only)."""
    if not _is_internal_server(name):
        server = await storage.get_system_server(name)
        if not server:
            raise AppError(ErrorCode.MCP_SYSTEM_SERVER_NOT_FOUND, args={"name": name})

    policy = await storage.set_tool_policy(
        server_name=name,
        tool_name=tool_name,
        disabled=data.disabled,
        inline_exposure=data.inline_exposure,
        allowed_roles=data.allowed_roles,
        role_quotas=data.role_quotas,
        updated_by=user.sub,
    )
    _audit_mcp(
        user,
        "update_tool_policy",
        name + ":" + tool_name,
        fields=data.model_fields_set,
        changes=_policy_changes(data),
    )
    return policy


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

    Only the current user's own server can be promoted.
    """
    _require_capability(user, "mcp:policy_manage")
    if not data.target_user_id:
        raise AppError(ErrorCode.TARGET_USER_REQUIRED)
    if data.target_user_id != user.sub:
        raise AppError(ErrorCode.FORBIDDEN)

    server = await storage.promote_to_system_server(name, data.target_user_id, user.sub)
    _audit_mcp(user, "promote_own_server", name, fields=())

    if not server:
        raise AppError(ErrorCode.MCP_USER_SERVER_NOT_FOUND, args={"name": name})

    return MCPServerMoveResponse(
        server=_redact_server(
            MCPServerResponse(
                name=server.name,
                transport=server.transport,
                enabled=server.enabled,
                url=server.url,
                headers=server.headers,
                is_system=True,
                can_edit=True,
                allowed_roles=server.allowed_roles,
                role_quotas=server.role_quotas,
                created_at=server.created_at,
                updated_at=server.updated_at,
            )
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
    _require_capability(user, "mcp:policy_manage")
    _require_capability(user, "mcp:export")
    if not data.target_user_id:
        raise AppError(ErrorCode.TARGET_OWNER_REQUIRED)

    server = await storage.demote_to_user_server(name, data.target_user_id, user.sub)
    _audit_mcp(user, "demote_system_server", name, fields=["target_user_id:" + data.target_user_id])

    if not server:
        raise AppError(ErrorCode.MCP_SYSTEM_SERVER_CONFLICT, args={"name": name})

    return MCPServerMoveResponse(
        server=_redact_server(
            MCPServerResponse(
                name=server.name,
                transport=server.transport,
                enabled=server.enabled,
                url=server.url,
                headers=server.headers,
                is_system=False,
                can_edit=True,
                created_at=server.created_at,
                updated_at=server.updated_at,
            )
        ),
        message=f"System server '{name}' has been demoted to user server",
        from_type="system",
        to_type="user",
    )
