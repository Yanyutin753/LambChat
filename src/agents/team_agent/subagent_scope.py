"""Rebuild authorized team/persona child scopes at each persistent execution."""

from typing import Any

from src.agents.core.persona_subagent import build_persona_subagent_spec
from src.agents.core.subagent_prompts import (
    build_response_language_section,
    build_role_subagent_section,
)
from src.agents.team_agent.member_config import (
    _build_member_agent_mode_sections,
    _safe_member_model_config_dict,
)
from src.agents.team_agent.prompt import build_team_member_subagent_type
from src.infra.tool.computer_use_tool import filter_computer_use_tools, resolve_computer_use_context
from src.kernel.config import settings
from src.kernel.schemas.model import effective_image_url_mode


def create_team_subagent_resolver(
    *,
    context: Any,
    runtime_subagent_specs: dict,
    model_id: str | None,
    llm: Any,
    thinking_config: dict,
    team: Any,
    team_id: str | None,
    user_input: str,
    session_id: str | None,
    agent_options: dict,
    persona_sections: list,
    memory_guide: str,
    sandbox_active: bool,
    image_url_mode: str,
    supports_vision: bool,
    subagent_display_names: dict,
    subagent_avatars: dict,
    build_subagent_middleware: Any,
    refresh_context: Any,
    resolve_team: Any,
    resolve_member_model: Any,
    resolve_member_agent: Any,
    get_model: Any,
):
    async def available_tools(tool_context):
        return filter_computer_use_tools(
            list(tool_context.filter_tools()),
            await resolve_computer_use_context(context.user_id or "", agent_options),
        )

    async def resolve_session_spec(role_type):
        await resolve_member_model(model_id, user_id=context.user_id)
        fresh_context = await refresh_context(context)
        if role_type.startswith("persona:"):
            return await build_persona_subagent_spec(
                role_type.removeprefix("persona:"),
                user_id=context.user_id or "",
                tool_context=fresh_context,
                tools=await available_tools(fresh_context),
                llm=llm,
                session_id=session_id,
                agent_options=agent_options,
                memory_guide=memory_guide,
                build_subagent_middleware=build_subagent_middleware,
                subagent_display_names=subagent_display_names,
                subagent_avatars=subagent_avatars,
            )
        spec = runtime_subagent_specs.get(role_type)
        if spec is None:
            raise ValueError("Unknown subagent type")
        if team:
            current_team = await resolve_team(
                team_id=team_id, context=context, user_input=user_input
            )
            member = (
                next(
                    (
                        member
                        for member in current_team.active_members
                        if build_team_member_subagent_type(member) == role_type
                    ),
                    None,
                )
                if current_team
                else None
            )
            if member is None:
                raise ValueError("Subagent role is no longer available")
            from src.agents.team_agent.role_tools import build_role_tool_scope
            from src.infra.persona_preset.manager import get_persona_preset_manager
            from src.infra.skill.skill_search_tool import SkillSearchTool

            current_preset = await get_persona_preset_manager().use_preset(
                member.persona_preset_id, user_id=context.user_id or "default", is_admin=False
            )
            current_agent_id = await resolve_member_agent(member.agent_id, user_id=context.user_id)
            current_model = await resolve_member_model(member.model_id, user_id=context.user_id)
            if current_model is not None:
                spec = {
                    **spec,
                    "model": await get_model(
                        model=current_model.value,
                        model_id=current_model.id,
                        model_config=_safe_member_model_config_dict(current_model),
                        thinking=thinking_config,
                    ),
                }
            role_section = build_role_subagent_section(
                role_name=member.role_name or role_type,
                role_system_prompt=current_preset.system_prompt,
                team_name=current_team.name,
                team_instructions=current_team.team_instructions or None,
                role_instructions=member.role_instructions or None,
            )
            member_tools, member_manager = build_role_tool_scope(
                [
                    tool
                    for tool in await available_tools(fresh_context)
                    if tool.name != "search_skills"
                ],
                fresh_context.deferred_manager,
                mcp_servers=current_preset.mcp_server_names,
                scope=f"{session_id}:subagent:{role_type}",
            )
            skill_names = set(getattr(current_preset, "skill_names", []) or [])
            member_skills = [
                skill
                for skill in fresh_context.skills
                if (not skill_names and not current_preset.missing_skill_names)
                or skill.get("name") in skill_names
            ]
            if settings.ENABLE_SKILLS and member_skills:
                member_tools.append(SkillSearchTool(member_skills))
            spec = {
                **spec,
                "tools": member_tools,
                "middleware": build_subagent_middleware(
                    role_type,
                    tool_context=fresh_context,
                    deferred_manager=member_manager,
                    prompt_sections=[
                        *_build_member_agent_mode_sections(
                            current_agent_id, sandbox_active=sandbox_active
                        ),
                        role_section,
                        memory_guide,
                        build_response_language_section(agent_options.get("response_language")),
                    ],
                    member_image_url_mode=effective_image_url_mode(current_model.profile)
                    if current_model
                    else image_url_mode,
                    member_supports_vision=bool(
                        current_model.profile and current_model.profile.supports_vision
                    )
                    if current_model
                    else supports_vision,
                ),
            }
        if not team:
            spec = {
                **spec,
                "tools": await available_tools(fresh_context),
                "middleware": build_subagent_middleware(
                    role_type,
                    tool_context=fresh_context,
                    prompt_sections=[s for s in (*persona_sections, memory_guide) if s],
                ),
            }
        return spec

    return resolve_session_spec
