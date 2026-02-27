"""Agent-related schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.kernel.schemas.message import ToolCall


class AgentRequest(BaseModel):
    """Request to run the agent."""

    message: str = Field(..., description="User message or task description")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    workspace_dir: str = Field("./workspace", description="Working directory for file operations")
    max_steps: int = Field(50, description="Maximum number of agent steps")
    disabled_tools: Optional[list[str]] = Field(
        None, description="Tools to disable (default: none)"
    )
    agent_options: Optional[dict[str, Any]] = Field(
        None, description="Agent options (e.g., enable_thinking)"
    )
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class AgentStep(BaseModel):
    """Single step in agent execution."""

    step: int
    thought: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    response: Optional[str] = None


class AgentResponse(BaseModel):
    """Agent execution response."""

    success: bool
    message: str
    steps: int
    logs: list[AgentStep] = Field(default_factory=list)
    session_id: str
    trace_url: Optional[str] = None  # LangSmith trace URL


class StreamEvent(BaseModel):
    """Streaming event."""

    event_type: str  # thinking, content, tool_call, tool_result, step, complete, error
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ToolParamInfo(BaseModel):
    """Information about a tool parameter."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Parameter name")
    type: str = Field(default="string", description="Parameter type")
    description: str = Field(default="", description="Parameter description")
    required: bool = Field(default=False, description="Whether the parameter is required")
    default: Optional[Any] = Field(None, description="Default value if any")


class ToolInfo(BaseModel):
    """Information about a single tool."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Tool name")
    description: str = Field(default="", description="Tool description")
    category: str = Field(..., description="Tool category: builtin, skill, human, mcp")
    server: Optional[str] = Field(None, description="MCP server name for MCP tools")
    parameters: list[ToolParamInfo] = Field(default_factory=list, description="Tool parameters")


class ToolsListResponse(BaseModel):
    """Tools list response."""

    tools: list[ToolInfo]
    count: int


class VersionResponse(BaseModel):
    """Version information response."""

    app_version: str = Field(..., description="Application version")
    git_tag: Optional[str] = Field(None, description="Git tag (e.g., v1.0.0)")
    commit_hash: Optional[str] = Field(None, description="Git commit short hash")
    build_time: Optional[str] = Field(None, description="Build timestamp")
