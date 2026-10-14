"""Load discovered roles with their original prompts and authorized tool scopes."""

from typing import Any

from deepagents.middleware.subagents import SubAgent

from src.agents.core.subagent_prompts import (
    SUBAGENT_PROMPT,
    build_response_language_section,
    build_role_subagent_section,
)
from src.kernel.config import settings


async def build_persona_subagent_spec(
    preset_id: str,
    *,
    user_id: str,
    tool_context: Any,
    tools: list,
    llm: Any,
    session_id: str | None,
    agent_options: dict,
    memory_guide: str,
    build_subagent_middleware: Any,
    subagent_display_names: dict[str, str],
    subagent_avatars: dict[str, str],
) -> SubAgent:
    from src.agents.team_agent.role_tools import build_role_tool_scope
    from src.infra.skill.skill_search_tool import SkillSearchTool
    from src.infra.tool.team_tool import resolve_persona_for_subagent

    snapshot = await resolve_persona_for_subagent(preset_id, user_id=user_id)
    role_type = f"persona:{preset_id}"
    role_sections = [
        build_role_subagent_section(snapshot.name, snapshot.system_prompt),
        build_response_language_section(agent_options.get("response_language")),
        memory_guide,
    ]
    role_tools, role_manager = build_role_tool_scope(
        tools,
        tool_context.deferred_manager,
        mcp_servers=snapshot.mcp_server_names,
        scope=f"{session_id}:subagent:{role_type}",
    )
    role_skills = [
        skill
        for skill in tool_context.skills
        if (not snapshot.skill_names and not snapshot.missing_skill_names)
        or skill.get("name") in snapshot.skill_names
    ]
    if settings.ENABLE_SKILLS and role_skills:
        role_tools.append(SkillSearchTool(role_skills))
    spec: SubAgent = {
        "name": role_type,
        "description": snapshot.name,
        "model": llm,
        "tools": role_tools,
        "system_prompt": SUBAGENT_PROMPT,
        "middleware": build_subagent_middleware(
            role_type,
            prompt_sections=role_sections,
            deferred_manager=role_manager,
            tool_context=tool_context,
        ),
    }
    subagent_display_names[role_type] = snapshot.name
    if snapshot.avatar:
        subagent_avatars[role_type] = snapshot.avatar
    return spec
