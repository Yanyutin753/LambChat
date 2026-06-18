"""Naming contracts for extensionized agent capabilities.

AgentTeam keeps the legacy external Team API surface for compatibility, while
new extension manifests and contributions use the clearer ``agent_team`` name.
Future UserAgent support is reserved as a separate capability and must not reuse
the AgentTeam ``team_id`` / member / role model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentTeamNaming:
    """Compatibility contract for the existing Team capability."""

    extension_type: str
    manifest_id: str
    legacy_agent_id: str
    legacy_api_prefix: str
    legacy_permission_prefix: str
    legacy_permissions: tuple[str, ...]
    legacy_chat_field: str


@dataclass(frozen=True)
class UserAgentNaming:
    """Reserved contract for future user-defined personal agents."""

    extension_type: str
    reuses_agent_team_model: bool
    forbidden_agent_team_fields: tuple[str, ...]


AGENT_TEAM_NAMING = AgentTeamNaming(
    extension_type="agent_team",
    manifest_id="agent-team",
    legacy_agent_id="team",
    legacy_api_prefix="/api/teams",
    legacy_permission_prefix="team",
    legacy_permissions=("team:read", "team:write", "team:delete"),
    legacy_chat_field="team_id",
)

USER_AGENT_NAMING = UserAgentNaming(
    extension_type="user_agent",
    reuses_agent_team_model=False,
    forbidden_agent_team_fields=(
        "team_id",
        "members",
        "member_id",
        "role_name",
        "role_tags",
        "role_instructions",
        "default_member_id",
        "team_instructions",
    ),
)
