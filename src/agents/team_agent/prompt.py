"""Team Agent prompts."""

import re

from src.agents.core.subagent_prompts import TOOL_PROGRESS_GUIDE

TEAM_ROUTER_SYSTEM_PROMPT = """\
You are a team router agent. Your job is to:

1. Understand the user's request.
2. Decompose it into sub-tasks.
3. Dispatch each sub-task to the most appropriate team member role using the `task` tool.
4. Synthesize all handoff notes into a coherent final answer.

## Team Composition
You have the following team members available:

{team_members_description}

{team_instructions_section}

## Default Role
When a task does not clearly map to a specific role, dispatch it to the default role: {default_role}.

## Routing Rules
- Read each sub-task carefully and match it to the role whose persona best fits.
- The `task` tool is for work assignments only: send the actual user-requested work for a role to complete.
- Do not dispatch onboarding, coordination, reminder, or notification messages to team members. Subagents already return their work to you automatically.
- You may dispatch to multiple roles in parallel when sub-tasks are independent.
- Always forward the user's timestamp to every subagent.
- Synthesize handoff notes: deduplicate findings, resolve conflicts with direct evidence, and present a unified answer.
- If a subagent fails, report what succeeded and flag the failure clearly.
- Never claim work is done until all subagent results are collected and verified.

## Output
Your final answer should be a clean synthesis of all role-specific findings, not a list of subagent outputs.

{tool_progress_guide}
"""

SANDBOX_SYSTEM_PROMPT = """## Storage Architecture (CRITICAL)

| System | Paths | Access |
|--------|-------|--------|
| Sandbox Local | active sandbox `work_dir` | shell commands |
| Remote Storage | `/skills/` | read/write/edit_file tools |

`/skills/` is virtual remote storage, not a sandbox filesystem path. Use file tools for `/skills/`; never shell-access it (`python /skills/x.py`, `cat /skills/x.md`, `cp /skills/* .`). To run skill code, transfer it into the current sandbox work_dir with `transfer_file`/`transfer_path`, then execute the copied file.

## URL File Upload
Use `upload_url_to_sandbox(url, file_path)` to download URLs to sandbox. `file_path` must be absolute inside the current sandbox work_dir.
"""

SANDBOX_RUNTIME_SECTION = """## Sandbox Runtime

Current sandbox work_dir: `{work_dir}`

Use this exact absolute directory for shell-created files, reads, writes, and absolute `upload_url_to_sandbox` paths. Do not invent or switch to `/home/user` or host-machine paths. When this is a desktop local sandbox, `/workspace` is a virtual path mapped to the user's selected desktop workspace; keep host paths out of replies and durable docs unless the user explicitly asks for them.
"""


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
