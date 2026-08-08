"""Team Agent prompts."""

import re

from src.agents.core.prompt_policy import SANDBOX_RUNTIME_POLICY, SANDBOX_STORAGE_POLICY
from src.agents.core.subagent_prompts import TOOL_PROGRESS_GUIDE

TEAM_ROUTER_SYSTEM_PROMPT = """You route work to a team with the `task` tool and synthesize its handoff evidence.

## Team

{team_members_description}

{team_instructions_section}

## Default Role
Dispatch unclear work to `{default_role}`.

## Routing Rules
- Match each real work item to the best role; do not dispatch coordination or reminder messages.
- Include the user's timestamp, scope, context, evidence, and acceptance criteria in every dispatch.
- Dispatch independent tasks in parallel; sequence dependent tasks after prerequisites.
- Read all handoffs, deduplicate findings, resolve conflict with direct evidence, and verify before claiming completion.
- Report partial success and failures clearly. Return one coherent synthesis, not a transcript.

{tool_progress_guide}
"""

SANDBOX_SYSTEM_PROMPT = SANDBOX_STORAGE_POLICY
SANDBOX_RUNTIME_SECTION = SANDBOX_RUNTIME_POLICY


def build_team_members_description(team, role_summaries: dict[str, str] | None = None) -> str:
    """Build a text description of team members for the router prompt."""
    role_summaries = role_summaries or {}
    lines = []
    for m in team.active_members:
        subagent_type = build_team_member_subagent_type(m)
        role_name = m.role_name or m.member_id
        lines.append(f"- `{subagent_type}`: **{role_name}** (member_id: {m.member_id})")
        role_summary = role_summaries.get(m.member_id)
        if role_summary:
            lines.append(f"  Capability summary: {role_summary}")
        if m.role_instructions:
            lines.append(f"  Instructions: {m.role_instructions}")
    return "\n".join(lines)


def summarize_role_system_prompt(system_prompt: str, max_chars: int = 500) -> str:
    """Build a compact role capability summary for the router prompt."""
    text = " ".join(line.strip() for line in (system_prompt or "").splitlines() if line.strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def build_team_router_system_prompt(
    team,
    *,
    default_role: str,
    role_summaries: dict[str, str] | None = None,
) -> str:
    """Build the router system prompt for a concrete team."""
    team_instructions = (getattr(team, "team_instructions", "") or "").strip()
    team_instructions_section = (
        f"## Team Instructions\n{team_instructions}" if team_instructions else ""
    )
    return TEAM_ROUTER_SYSTEM_PROMPT.format(
        team_members_description=build_team_members_description(
            team,
            role_summaries=role_summaries,
        ),
        team_instructions_section=team_instructions_section,
        default_role=default_role,
        tool_progress_guide=TOOL_PROGRESS_GUIDE.strip(),
    )


def build_team_subagent_display_names(team) -> dict[str, str]:
    """Map internal team subagent types to user-facing role names."""
    return {
        build_team_member_subagent_type(member): (member.role_name or member.member_id)
        for member in team.active_members
    }


def build_team_subagent_avatars(team) -> dict[str, str]:
    """Map internal team subagent types to user-facing role avatar URLs."""
    return {
        build_team_member_subagent_type(member): member.role_avatar
        for member in team.active_members
        if member.role_avatar
    }


def build_team_member_subagent_type(member) -> str:
    """Build a stable task-tool subagent type for a team member."""
    role_slug = re.sub(r"[^a-z0-9]+", "-", (member.role_name or "").lower()).strip("-")
    if not role_slug:
        role_slug = "role"
    member_slug = re.sub(r"[^a-z0-9-]+", "-", member.member_id.lower()).strip("-")
    if not member_slug:
        member_slug = "member"
    return f"team-{member_slug}-{role_slug}"
