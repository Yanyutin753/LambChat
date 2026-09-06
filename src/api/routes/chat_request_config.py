"""chat 路由的请求预处理器（persona 解析 + 会话配置元数据构建）。

从 chat.py 抽出的纯辅助层：chat.py 受 1000 行守卫约束，且这些函数被
路由与测试共用。chat.py 转发导入以保持 `from ...chat import` 兼容。
"""

from __future__ import annotations

from src.infra.persona_preset.manager import PersonaPresetManager
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.persona_preset import PersonaPresetSnapshot
from src.kernel.schemas.user import TokenPayload


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
    conversation_config = {
        "current_run_id": run_id,
        "agent_id": agent_id,
        "executor_key": "agent_stream",
        "agent_options": request.agent_options or {},
        "disabled_tools": request.disabled_tools or [],
        "disabled_skills": request.disabled_skills or [],
        "enabled_skills": request.enabled_skills,
        "disabled_mcp_tools": request.disabled_mcp_tools or [],
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

    persona_manager = manager or PersonaPresetManager()
    snapshot = await persona_manager.use_preset(
        request.persona_preset_id,
        user_id=user.sub,
        is_admin="persona_preset:admin" in (user.permissions or []),
    )
    request.persona_snapshot = snapshot
    request.enabled_skills = _persona_enabled_skills_from_snapshot(snapshot)
    request.persona_system_prompt = snapshot.system_prompt
