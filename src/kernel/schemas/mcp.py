"""
MCP (Model Context Protocol) schemas for API request/response
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MCPTransport(str, Enum):
    """MCP transport type"""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class MCPServerBase(BaseModel):
    """Base MCP server configuration"""

    name: str = Field(..., description="Server name (unique identifier)")
    transport: MCPTransport = Field(..., description="Transport type")
    enabled: bool = Field(True, description="Whether server is enabled")

    # stdio configuration
    command: Optional[str] = Field(None, description="Command for stdio transport")
    args: Optional[list[str]] = Field(None, description="Arguments for command")
    env: Optional[dict[str, str]] = Field(None, description="Environment variables")

    # http configuration
    url: Optional[str] = Field(None, description="URL for http transport")
    headers: Optional[dict[str, str]] = Field(None, description="HTTP headers")


class MCPServerCreate(MCPServerBase):
    """Schema for creating a new MCP server"""

    pass


class MCPServerUpdate(BaseModel):
    """Schema for updating an MCP server"""

    transport: Optional[MCPTransport] = None
    enabled: Optional[bool] = None
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[dict[str, str]] = None


class SystemMCPServer(MCPServerBase):
    """System-level MCP server configuration (admin managed)"""

    is_system: bool = Field(True, description="Always True for system servers")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    updated_by: Optional[str] = Field(None, description="Admin user ID who last updated")


class UserMCPServer(MCPServerBase):
    """User-level MCP server configuration"""

    user_id: str = Field(..., description="Owner user ID")
    is_system: bool = Field(False, description="Always False for user servers")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class MCPServerResponse(MCPServerBase):
    """MCP server response with additional metadata"""

    is_system: bool = Field(..., description="Whether this is a system server")
    can_edit: bool = Field(..., description="Whether current user can edit this server")
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
    mcpServers: Optional[dict[str, dict[str, Any]]] = Field(
        None, description="MCP servers config (studio/Claude Desktop format)"
    )
    overwrite: bool = Field(False, description="Overwrite existing servers with same name")

    def get_servers(self) -> dict[str, dict[str, Any]]:
        """Return servers from whichever key was provided, preferring mcpServers"""
        return self.mcpServers or self.servers or {}


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
