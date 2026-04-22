"""
MCP (Model Context Protocol) schemas for API request/response
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MCPTransport(str, Enum):
    """MCP transport type"""

    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"
    SANDBOX = "sandbox"


class MCPServerBase(BaseModel):
    """Base MCP server configuration"""

    name: str = Field(..., description="Server name (unique identifier)")
    transport: MCPTransport = Field(..., description="Transport type")
    enabled: bool = Field(True, description="Whether server is enabled")

    # http configuration
    url: Optional[str] = Field(None, description="URL for http transport")
    headers: Optional[dict[str, str]] = Field(None, description="HTTP headers")

    # sandbox configuration
    command: Optional[str] = Field(None, description="stdio command for sandbox transport")
    env_keys: Optional[list[str]] = Field(
        None, description="Environment variable keys to inject into sandbox MCP"
    )


class MCPRoleQuota(BaseModel):
    """Per-role MCP usage quota for a system server."""

    daily_limit: Optional[int] = Field(
        None,
        ge=0,
        description="Daily tool-call limit per user for this role. None = unlimited.",
    )
    weekly_limit: Optional[int] = Field(
        None,
        ge=0,
        description="Weekly tool-call limit per user for this role. None = unlimited.",
    )


class MCPServerCreate(MCPServerBase):
    """Schema for creating a new MCP server"""

    allowed_roles: list[str] = Field(
        default_factory=list,
        description="Roles allowed to see and use this server. Empty list = all roles.",
    )
    role_quotas: dict[str, MCPRoleQuota] = Field(
        default_factory=dict,
        description="Per-role usage quotas for this system server.",
    )


class MCPServerUpdate(BaseModel):
    """Schema for updating an MCP server"""

    transport: Optional[MCPTransport] = None
    enabled: Optional[bool] = None
    url: Optional[str] = None
    headers: Optional[dict[str, str]] = None
    command: Optional[str] = None
    env_keys: Optional[list[str]] = None
    allowed_roles: Optional[list[str]] = None
    role_quotas: Optional[dict[str, MCPRoleQuota]] = None


class SystemMCPServer(MCPServerBase):
    """System-level MCP server configuration (admin managed)"""

    is_system: bool = Field(True, description="Always True for system servers")
    disabled_tools: list[str] = Field(
        default_factory=list, description="List of tool names disabled at system level"
    )
    allowed_roles: list[str] = Field(
        default_factory=list,
        description="Roles allowed to see and use this server. Empty list = all roles.",
    )
    role_quotas: dict[str, MCPRoleQuota] = Field(
        default_factory=dict,
        description="Per-role usage quotas for this system server.",
    )
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    updated_by: Optional[str] = Field(None, description="Admin user ID who last updated")
    created_by: Optional[str] = Field(None, description="Admin user ID who created the server")


class UserMCPServer(MCPServerBase):
    """User-level MCP server configuration"""

    user_id: str = Field(..., description="Owner user ID")
    is_system: bool = Field(False, description="Always False for user servers")
    disabled_tools: list[str] = Field(
        default_factory=list, description="List of tool names disabled on this server"
    )
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class MCPServerResponse(MCPServerBase):
    """MCP server response with additional metadata"""

    is_system: bool = Field(..., description="Whether this is a system server")
    can_edit: bool = Field(..., description="Whether current user can edit this server")
    allowed_roles: list[str] = Field(
        default_factory=list,
        description="Roles allowed to see and use this server. Empty list = all roles.",
    )
    role_quotas: dict[str, MCPRoleQuota] = Field(
        default_factory=dict,
        description="Per-role usage quotas for this system server.",
    )
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class MCPServersResponse(BaseModel):
    """Response containing list of MCP servers"""

    servers: list[MCPServerResponse] = Field(default_factory=list)


class MCPServerToggleResponse(BaseModel):
    """Response after toggling server enabled status"""

    server: MCPServerResponse
    message: str


class MCPImportRequest(BaseModel):
    """Request to import MCP servers from JSON (supports both native and studio format)"""

    servers: Optional[dict[str, dict[str, Any]]] = Field(
        None, description="MCP servers config (native format)"
    )
    mcp_servers: Optional[dict[str, dict[str, Any]]] = Field(
        None, description="MCP servers config (studio/Claude Desktop format)"
    )
    overwrite: bool = Field(False, description="Overwrite existing servers with same name")

    def get_servers(self) -> dict[str, dict[str, Any]]:
        """Return servers from whichever key was provided, preferring mcp_servers"""
        return self.mcp_servers or self.servers or {}


class MCPImportResponse(BaseModel):
    """Response after importing MCP servers"""

    message: str
    imported_count: int
    skipped_count: int
    errors: list[str] = Field(default_factory=list)


class MCPExportResponse(BaseModel):
    """Response for exporting MCP configuration"""

    servers: dict[str, dict[str, Any]] = Field(default_factory=dict)


class MCPServerMoveRequest(BaseModel):
    """Request to move a server between user and system"""

    target_user_id: Optional[str] = Field(
        None, description="Target user ID when demoting system server to user server"
    )


class MCPServerMoveResponse(BaseModel):
    """Response after moving a server"""

    server: MCPServerResponse
    message: str
    from_type: str = Field(..., description="Original server type (user/system)")
    to_type: str = Field(..., description="New server type (user/system)")


# ============================================
# MCP Tool Discovery & Toggle Schemas
# ============================================


class MCPToolInfo(BaseModel):
    """Information about a tool discovered from an MCP server"""

    name: str = Field(..., description="Tool name")
    description: str = Field(default="", description="Tool description")
    parameters: list[dict[str, Any]] = Field(default_factory=list, description="Tool parameters")
    system_disabled: bool = Field(
        default=False, description="Whether this tool is disabled at system level"
    )
    user_disabled: bool = Field(
        default=False, description="Whether this tool is disabled by the current user"
    )


class MCPToolDiscoveryResponse(BaseModel):
    """Response for tool discovery from an MCP server"""

    server_name: str = Field(..., description="MCP server name")
    tools: list[MCPToolInfo] = Field(default_factory=list, description="Discovered tools")
    count: int = Field(0, description="Number of discovered tools")
    error: Optional[str] = Field(None, description="Error message if discovery failed")


class MCPToolToggleRequest(BaseModel):
    """Request to toggle a specific tool's enabled status"""

    enabled: bool = Field(..., description="Whether the tool is enabled")
    level: str = Field(
        "system",
        description="Toggle level: 'system' for server-level (affects all users), 'user' for per-user preference",
    )


class MCPToolToggleResponse(BaseModel):
    """Response after toggling a tool's enabled status"""

    server_name: str = Field(..., description="MCP server name")
    tool_name: str = Field(..., description="Tool name")
    enabled: bool = Field(..., description="New enabled status")
    message: str
