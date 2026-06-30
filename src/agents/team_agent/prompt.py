"""Team Agent prompts."""

import re

from src.agents.core.subagent_prompts import TOOL_PROGRESS_GUIDE

DELEGATION_HELPER = """\
## Delegation Helper
Before calling `task`, classify the assignment and write a compact structured task brief.

Task types:
- TEXT_ONLY: output, list, generate prompts/copy, summarize, compare, explain.
- FILE_ARTIFACT: explicitly create/save/export/package/reveal files or projects.
- RESEARCH: find/check/source-backed or latest information.
- CODE_CHANGE: modify/debug/test code or configuration.
- MULTI_STAGE: the user explicitly asks for a pipeline or multiple specialties.

Use this task brief shape when delegating:

Current task start time: ...
Task type: TEXT_ONLY | FILE_ARTIFACT | RESEARCH | CODE_CHANGE | MULTI_STAGE
Delivery mode: RETURN_TEXT | CREATE_FILES | MODIFY_CODE | RESEARCH_SUMMARY
Reference policy: USER_PROVIDED_ONLY | READ_ONLY_ALLOWED | LOOKUP_REQUIRED
Tool policy: NO_TOOLS | READ_ONLY | ARTIFACT_ALLOWED | CODE_ALLOWED
Max tool calls: 0 | 3 | as needed
Artifact intent: false | true
Target member: <role name>
Context source: <user-provided complete brief | attached prior result | explicit file lookup needed>
Allowed tools: <none unless strictly necessary | file tools allowed | research tools allowed | code tools allowed>
Forbidden actions: <clear boundaries>
Objective: <one sentence>
Fixed inputs:
<only the relevant user-provided facts, constraints, and prior results>
Output format:
<exact fields or schema the member must return>

Delegation shortcuts:
- If the user already provides a complete topic, scene list, constraints, and output fields, use Task type: TEXT_ONLY, Delivery mode: RETURN_TEXT, Reference policy: USER_PROVIDED_ONLY, Tool policy: NO_TOOLS, Max tool calls: 0, Artifact intent: false, and delegate directly to the best matching member.
- For TEXT_ONLY tasks with a complete brief, set Allowed tools to `none` and forbid reading files, listing directories, searching templates, creating folders, writing files, running scripts, exporting packages, revealing artifacts, or inferring missing upstream files.
- Use Reference policy: READ_ONLY_ALLOWED and Tool policy: READ_ONLY only when the current user explicitly asks the member to inspect files or upstream materials.
- Use Tool policy: ARTIFACT_ALLOWED or CODE_ALLOWED only when the current user explicitly asks to save/export/package artifacts or modify/test code.
- If one member can complete the request, delegate to exactly one member. Use multiple members only when the task genuinely requires multiple specialties or the user asks for a pipeline.
"""

ROUTER_TOOL_POLICY_SECTION = """\
## Router Tool Policy
The team router is configured as a dispatcher and synthesizer. It may use direct tools only for coordination, verification, final artifact delivery, or fallback work after a member result is missing or failed. Delegate executable work to team members first. Do not use external upload services for artifact delivery.
"""

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
- The current user request is authoritative. If stored team instructions describe a default pipeline, packaging flow, or artifact delivery that conflicts with the current user's explicit request, follow the current request and the Delegation Helper.
- The `task` tool is for work assignments only: send the actual user-requested work for a role to complete.
- For any substantive user request, call the `task` tool for at least one team member before writing the final answer.
- Team members are preferred executors: if an active member can reasonably complete the work, route it to that member before doing it yourself.
- The team router may perform work directly only for coordination, verification, packaging, missing follow-up work, member failures, or tasks that do not fit any active member.
- After a member returns usable work, synthesize it instead of redoing the same work yourself unless you are filling a clear gap.
- If one member can satisfy the request, prefer a single delegation. Use multiple members only when the task genuinely needs multiple specialties or the user asks for a pipeline.
- Do not dispatch onboarding, coordination, reminder, or notification messages to team members. Subagents already return their work to you automatically.
- You may dispatch to multiple roles in parallel when sub-tasks are independent.
- Always forward the user's timestamp to every subagent.
- Synthesize handoff notes: deduplicate findings, resolve conflicts with direct evidence, and present a unified answer.
- If a subagent fails, report what succeeded and flag the failure clearly.
- Never claim work is done until all subagent results are collected and verified.

{delegation_helper}

{router_tool_policy_section}

## Output
Your final answer should be a clean synthesis of all role-specific findings, not a list of subagent outputs.

{tool_progress_guide}
"""

SANDBOX_SYSTEM_PROMPT = """## Storage Architecture (CRITICAL)

| System | Paths | Access |
|--------|-------|--------|
| Sandbox Local | current session workspace (`work_dir`) | shell commands and file tools |
| Remote Storage | `/skills/` | read/write/edit_file tools |

`/skills/` is virtual remote storage, not a sandbox filesystem path. Use file tools for `/skills/`; never shell-access it (`python /skills/x.py`, `cat /skills/x.md`, `cp /skills/* .`). The sandbox local path is provided at runtime as `Current session workspace`; use that session-id-specific workspace for shell commands, file tools, and absolute upload paths. To run skill code, transfer it into the current session workspace with `transfer_file`/`transfer_path`, then execute the copied file.

## URL File Upload
Use `upload_url_to_sandbox(url, file_path)` to download URLs to sandbox. `file_path` must be absolute inside the current session workspace.
"""

SANDBOX_RUNTIME_SECTION = """## Sandbox Runtime

Current session workspace: `{work_dir}`

This is the initial/default working directory for this session and is derived from the session id. Use this absolute directory for shell-created files, file tools, and absolute `upload_url_to_sandbox` paths. Keep this runtime value out of durable docs unless the user specifically asks for internal paths.
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
        delegation_helper=DELEGATION_HELPER.strip(),
        router_tool_policy_section=ROUTER_TOOL_POLICY_SECTION.strip(),
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
