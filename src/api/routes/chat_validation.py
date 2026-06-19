"""Validation helpers for chat routes."""

from src.kernel.schemas.agent import AgentRequest
from src.kernel.extensions.plugin_options import plugin_session_options_suppress_core_persona


def validate_team_agent_request(
    _agent_id: str,
    _request: AgentRequest,
    *,
    plugin_runtime=None,
) -> None:
    """Validate plugin-scoped chat request requirements before dispatch."""
    if plugin_session_options_suppress_core_persona(
        _agent_id,
        {
            "team_id": _request.team_id,
            "plugin_options": _request.plugin_options or {},
        },
        runtime=plugin_runtime,
    ):
        _request.enabled_skills = None
        if _request.persona_preset_id:
            _request.persona_preset_id = None
            _request.persona_snapshot = None
            _request.persona_system_prompt = None
    return None
