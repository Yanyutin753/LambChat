"""chat 路由的请求预处理器（persona 解析 + 会话配置元数据构建）。

从 chat.py 抽出的纯辅助层：chat.py 受 1000 行守卫约束，且这些函数被
路由与测试共用。chat.py 转发导入以保持 `from ...chat import` 兼容。
"""

from __future__ import annotations

from src.infra.persona_preset.manager import (
    PersonaPresetManager,
    get_persona_preset_manager,
)
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.persona_preset import PersonaPresetSnapshot
from src.kernel.schemas.user import TokenPayload


def _persona_enabled_mcp_servers_from_snapshot(
    snapshot: PersonaPresetSnapshot,
) -> list[str] | None:
    """Return a MCP server whitelist only when the persona pins servers."""
    if snapshot.mcp_server_names:
        return snapshot.mcp_server_names
    return None


def _persona_enabled_skills_from_snapshot(
    snapshot: PersonaPresetSnapshot,
) -> list[str] | None:
    """Return a whitelist only when the persona has usable skills."""
    if snapshot.skill_names:
        return snapshot.skill_names
    return None


def build_conversation_config(
    run_id: str,
    agent_id: str,
    request: AgentRequest,
    language: str,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> dict:
    """Build session metadata for conversation configuration."""
    from src.infra.task.background_tasks import BACKGROUND_EXECUTOR_KEY, BACKGROUND_SUBMISSION_RUN

    conversation_config = {
        "current_run_id": run_id,
        "agent_id": agent_id,
        "executor_key": BACKGROUND_EXECUTOR_KEY
        if BACKGROUND_SUBMISSION_RUN.get()
        else "agent_stream",
        "agent_options": request.agent_options or {},
        "disabled_tools": request.disabled_tools or [],
        "disabled_skills": request.disabled_skills or [],
        "enabled_skills": request.enabled_skills,
        "disabled_mcp_tools": request.disabled_mcp_tools or [],
        "enabled_mcp_servers": request.enabled_mcp_servers,
        "language": language,
        "auto_mode": request.auto_mode,
    }
    if trace_id:
        conversation_config["trace_id"] = trace_id
    if request.persona_preset_id:
        conversation_config["persona_preset_id"] = request.persona_preset_id
    if request.persona_preset_id and request.persona_snapshot:
        conversation_config["persona_preset_name"] = request.persona_snapshot.name
        conversation_config["persona_snapshot"] = request.persona_snapshot.model_dump()
        if request.persona_snapshot.avatar:
            conversation_config["persona_avatar"] = request.persona_snapshot.avatar
    if request.project_id:
        conversation_config["project_id"] = request.project_id
    if request.user_timezone:
        conversation_config["user_timezone"] = request.user_timezone
    if agent_id == "team" and request.team_id:
        conversation_config["team_id"] = request.team_id
    return conversation_config


async def resolve_persona_request(
    request: AgentRequest,
    user: TokenPayload,
    manager: PersonaPresetManager | None = None,
) -> None:
    """Resolve persona preset data and drop any client-supplied prompt injection."""
    request.persona_snapshot = None
    request.persona_system_prompt = None

    if not request.persona_preset_id:
        return

    persona_manager = manager or get_persona_preset_manager()
    snapshot = await persona_manager.use_preset(
        request.persona_preset_id,
        user_id=user.sub,
        is_admin="persona_preset:admin" in (user.permissions or []),
        user_roles=list(user.roles or []),
    )
    request.persona_snapshot = snapshot
    request.enabled_skills = _persona_enabled_skills_from_snapshot(snapshot)
    request.enabled_mcp_servers = _persona_enabled_mcp_servers_from_snapshot(snapshot)
    request.persona_system_prompt = snapshot.system_prompt


async def build_assistant_identity(
    agent_id: str, request: AgentRequest, user_id: str, language: str
) -> dict:
    """Snapshot display identity once per submitted run, independent of session configuration."""
    from src.agents.core import AgentFactory
    from src.infra.agent.config_storage import get_agent_config_storage
    from src.infra.team.manager import get_team_manager

    if agent_id == "team" and request.team_id:
        team = await get_team_manager().get_team(request.team_id, owner_user_id=user_id)
        member = next((m for m in team.members if m.member_id == team.default_member_id), None)
        member = member or next((m for m in team.members if m.enabled), None)
        member = member or (team.members[0] if team.members else None)
        return {
            "seed": team.name,
            "name": team.name,
            "avatar": team.avatar or (member.role_avatar if member else None),
        }
    if request.persona_snapshot:
        snapshot = request.persona_snapshot
        return {"seed": snapshot.preset_id, "name": snapshot.name, "avatar": snapshot.avatar}

    agent = next((item for item in AgentFactory.list_agents() if item["id"] == agent_id), {})
    catalog = next(
        (
            item
            for item in await get_agent_config_storage().get_catalog_config()
            if item.id == agent_id
        ),
        None,
    )
    label = catalog.labels.get(language) if catalog else None
    return {
        "seed": agent_id,
        "name": (label.name if label and label.name else catalog.name)
        if catalog
        else agent.get("name"),
        "avatar": catalog.icon if catalog else agent.get("icon"),
    }
