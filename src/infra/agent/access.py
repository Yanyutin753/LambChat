"""Execution authority shared by interactive, resumed and scheduled Agent runs."""

from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload


async def validate_user_agent_access(agent_id: str, user: TokenPayload) -> None:
    from src.agents.core.base import AgentFactory, normalize_agent_id
    from src.infra.agent.config_storage import get_agent_config_storage
    from src.infra.role.manager import get_role_manager

    if "chat:write" not in user.permissions or not user.roles:
        raise AppError(ErrorCode.FORBIDDEN)
    roles = await get_role_manager().get_roles_by_names(user.roles)
    if not roles:
        raise AppError(ErrorCode.FORBIDDEN)
    role_ids = [role.id for role in roles]
    mapping = await get_agent_config_storage().get_role_agents_by_ids(role_ids)
    allowed = await AgentFactory.get_filtered_agents(user_roles=role_ids, role_agent_map=mapping)
    if normalize_agent_id(agent_id) not in {agent["id"] for agent in allowed}:
        raise AppError(ErrorCode.FORBIDDEN)


async def validate_current_execution(
    agent_id: str, user_id: str, options: dict | None = None
) -> dict:
    from src.api.deps import _load_user_payload
    from src.api.routes.chat import validate_agent_model_access

    user = await _load_user_payload(user_id)
    await validate_user_agent_access(agent_id, user)
    # Validation strips untrusted handoff fields; preserve the executor's accounting state.
    checked = dict(options or {})
    await validate_agent_model_access(checked, user)
    if options and "_handoff_usage" in options:
        checked["_handoff_usage"] = options["_handoff_usage"]
    return checked
