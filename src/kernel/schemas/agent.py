"""Agent-related schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.infra.goal import GoalSpec
from src.infra.utils.datetime import utc_now
from src.kernel.schemas.message import ToolCall
from src.kernel.schemas.persona_preset import PersonaPresetSnapshot


class AttachmentSchema(BaseModel):
    """Attachment schema for file uploads."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Unique attachment ID")
    key: str = Field(..., description="Storage key")
    name: str = Field(..., description="Original filename")
    type: str = Field(..., description="File category: image, video, audio, document")
    mime_type: str = Field(..., description="MIME type", alias="mimeType")
    size: int = Field(..., description="File size in bytes")
    url: str = Field(..., description="Accessible URL")


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
    disabled_skills: Optional[list[str]] = Field(
        None, description="Skills to disable for this conversation"
    )
    enabled_skills: Optional[list[str]] = Field(
        None, description="Skills to explicitly enable for this conversation"
    )
    persona_preset_id: Optional[str] = Field(None, description="Persona preset ID")
    persona_snapshot: Optional[PersonaPresetSnapshot] = Field(
        None, description="Resolved persona preset snapshot"
    )
    persona_system_prompt: Optional[str] = Field(
        None, description="Resolved persona system prompt for runtime injection"
    )
    disabled_mcp_tools: Optional[list[str]] = Field(
        None, description="MCP tools to disable for this conversation"
    )
    user_timezone: Optional[str] = Field(
        None, description="User IANA timezone for timestamping chat messages"
    )
    attachments: Optional[list[AttachmentSchema]] = Field(None, description="File attachments")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")
    project_id: Optional[str] = Field(None, description="Project ID to assign to new session")
    team_id: Optional[str] = Field(None, description="Team ID for team agent mode")
    goal: Optional[GoalSpec] = Field(None, description="Active goal for rubric-guided execution")
    retry_user_message: bool = Field(
        False,
        description="Regenerate using an existing user message without writing a duplicate user event",
    )


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
    timestamp: datetime = Field(default_factory=utc_now)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
    timestamp: datetime = Field(default_factory=utc_now)
    memory: Optional["MemoryHealthSummary"] = None


class MemoryHealthSummary(BaseModel):
    """Compact memory diagnostics for health checks."""

    available: bool = False
    reason: Optional[str] = None
    rss_bytes: Optional[int] = None
    vms_bytes: Optional[int] = None
    thread_count: Optional[int] = None
    open_file_count: Optional[int] = None
    history_size: Optional[int] = None
    growth_bytes: int = 0
    suspected_leak: bool = False
    sample_interval_seconds: Optional[float] = None
    baseline_reset_at: Optional[datetime] = None
    last_sample_at: Optional[datetime] = None
    last_error: Optional[str] = None
    checkpointer: Optional[dict[str, Any]] = None


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
    system_disabled: bool = Field(
        default=False,
        description="Whether this tool is disabled at the system level (admin controlled)",
    )
    user_disabled: bool = Field(
        default=False,
        description="Whether this tool is disabled by the user",
    )


class ToolsListResponse(BaseModel):
    """Tools list response."""

    tools: list[ToolInfo]
    count: int


class ReleaseAsset(BaseModel):
    """GitHub release asset for mobile download."""

    name: str = Field(..., description="Asset filename")
    url: str = Field(..., description="Asset download URL")
    size: Optional[int] = Field(None, description="File size in bytes")
    content_type: str = Field("application/octet-stream", description="MIME type")


class VersionResponse(BaseModel):
    """Version information response."""

    app_version: str = Field(..., description="Application version")
    git_tag: Optional[str] = Field(None, description="Git tag (e.g., v1.0.0)")
    commit_hash: Optional[str] = Field(None, description="Git commit short hash")
    build_time: Optional[str] = Field(None, description="Build timestamp")
    latest_version: Optional[str] = Field(None, description="Latest version from GitHub")
    release_url: Optional[str] = Field(None, description="GitHub release URL")
    github_url: Optional[str] = Field(None, description="GitHub repository URL")
    has_update: Optional[bool] = Field(None, description="Whether a newer version is available")
    published_at: Optional[str] = Field(None, description="Latest release publish date")
    release_notes: Optional[str] = Field(None, description="Release body/notes")
    release_assets: Optional[list[ReleaseAsset]] = Field(
        None, description="Release assets for mobile"
    )


# ============================================
# Agent Config Schemas
# ============================================


class AgentConfig(BaseModel):
    """Agent configuration (global)."""

    id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")
    enabled: bool = Field(True, description="Whether the agent is enabled globally")
    icon: Optional[str] = Field(None, description="Display icon name or emoji")
    sort_order: Optional[int] = Field(None, description="Display sort order")
    labels: dict[str, "AgentCatalogLocale"] = Field(
        default_factory=dict,
        description="Localized display labels keyed by locale",
    )


class AgentCatalogLocale(BaseModel):
    """Localized display metadata for an agent."""

    name: str = Field(default="", description="Localized agent display name")
    description: str = Field(default="", description="Localized agent description")


class AgentCatalogConfig(BaseModel):
    """Admin-managed agent catalog entry."""

    id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Fallback agent name or i18n key")
    description: str = Field(..., description="Fallback agent description or i18n key")
    enabled: bool = Field(True, description="Whether the agent is enabled globally")
    icon: str = Field("Bot", description="Display icon name or emoji")
    sort_order: int = Field(100, description="Display sort order")
    labels: dict[str, AgentCatalogLocale] = Field(
        default_factory=dict,
        description="Localized display labels keyed by locale",
    )


class AgentCatalogConfigUpdate(BaseModel):
    """Update admin-managed agent catalog."""

    agents: list[AgentCatalogConfig] = Field(..., description="List of catalog entries")


class AgentCatalogConfigResponse(BaseModel):
    """Response for admin-managed agent catalog."""

    agents: list[AgentCatalogConfig] = Field(..., description="All catalog entries")
    available_agents: list[str] = Field(..., description="List of enabled agent IDs")


class AgentConfigUpdate(BaseModel):
    """Update global agent configuration."""

    agents: list[AgentConfig] = Field(..., description="List of agent configurations")


class GlobalAgentConfigResponse(BaseModel):
    """Response for global agent config."""

    agents: list[AgentConfig] = Field(
        ..., description="All registered agents with their enabled status"
    )
    available_agents: list[str] = Field(..., description="List of enabled agent IDs")


# ============================================
# Role Agent Schemas
# ============================================


class RoleAgentAssignment(BaseModel):
    """Role's accessible agents."""

    role_id: str = Field(..., description="Role ID")
    role_name: str = Field(..., description="Role name")
    allowed_agents: list[str] = Field(default_factory=list, description="List of allowed agent IDs")


class RoleAgentAssignmentUpdate(BaseModel):
    """Update role's accessible agents."""

    allowed_agents: list[str] = Field(..., description="List of allowed agent IDs")


class RoleAgentAssignmentResponse(BaseModel):
    """Response after updating role's accessible agents."""

    role_id: str = Field(..., description="Role ID")
    role_name: str = Field(..., description="Role name")
    allowed_agents: list[str] = Field(default_factory=list, description="List of allowed agent IDs")


# ============================================
# Role Model Schemas
# ============================================


class RoleModelAssignment(BaseModel):
    """Role's accessible models."""

    role_id: str = Field(..., description="Role ID")
    role_name: str = Field(..., description="Role name")
    allowed_models: list[str] = Field(
        default_factory=list, description="List of allowed model values"
    )
    configured: bool = Field(True, description="Whether this role has an explicit model assignment")


class RoleModelAssignmentUpdate(BaseModel):
    """Update role's accessible models."""

    allowed_models: list[str] = Field(..., description="List of allowed model values")


# ============================================
# User Agent Preference Schemas
# ============================================


class UserAgentPreference(BaseModel):
    """User's default agent preference."""

    default_agent_id: Optional[str] = Field(None, description="Default agent ID for the user")


class UserAgentPreferenceUpdate(BaseModel):
    """Update user's default agent preference."""

    default_agent_id: str = Field(..., description="Default agent ID")


class UserAgentPreferenceResponse(BaseModel):
    """Response for user agent preference operations."""

    default_agent_id: Optional[str] = Field(None, description="Default agent ID for the user")
