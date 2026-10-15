"""Team member model access, agent access and prompt resolution."""

from typing import Any

from src.agents.search_agent.prompt import DEFAULT_SYSTEM_PROMPT as SEARCH_DEFAULT_SYSTEM_PROMPT
from src.agents.search_agent.prompt import SANDBOX_SYSTEM_PROMPT as SEARCH_SANDBOX_SYSTEM_PROMPT
from src.infra.logging import get_logger
from src.kernel.schemas.model import ModelConfig

logger = get_logger(__name__)


async def resolve_team_member_model_config(
    member_model_id: str | None,
    *,
    user_id: str | None = None,
) -> ModelConfig | None:
    """Resolve and validate a team member model override for runtime use."""
    if not member_model_id:
        return None

    from src.infra.agent.model_storage import get_model_storage

    try:
        model = await get_model_storage().get(member_model_id)
    except Exception as e:
        logger.warning("[TeamAgent] Failed to resolve member model %s: %s", member_model_id, e)
        raise ValueError("team_member_model_unavailable") from e

    if not model or not model.enabled:
        raise ValueError("team_member_model_unavailable")

    if user_id:
        try:
            from src.infra.agent.model_access import resolve_user_allowed_model_ids
            from src.infra.user.storage import UserStorage
            from src.kernel.schemas.user import TokenPayload

            user = await UserStorage().get_by_id(user_id)
            if not user:
                raise ValueError("team_member_model_not_allowed")
            allowed_model_ids = await resolve_user_allowed_model_ids(
                TokenPayload(
                    sub=user.id,
                    username=user.username,
                    roles=user.roles,
                    permissions=user.permissions,
                )
            )
            if allowed_model_ids is not None:
                allowed = set(allowed_model_ids)
                if model.id not in allowed and model.value not in allowed:
                    raise ValueError("team_member_model_not_allowed")
        except ValueError:
            raise
        except Exception as e:
            logger.warning(
                "[TeamAgent] Failed to validate member model access %s: %s",
                member_model_id,
                e,
            )
            raise ValueError("team_member_model_unavailable") from e
    return model


def _safe_member_model_config_dict(model: ModelConfig) -> dict[str, Any]:
    return model.model_copy(update={"api_key": None}).model_dump(mode="json")


async def resolve_team_member_agent_id(
    member_agent_id: str | None,
    *,
    user_id: str | None = None,
) -> str | None:
    """Resolve and validate a team member agent mode override for runtime use."""
    if not member_agent_id:
        return None

    from src.agents.core.base import normalize_agent_id

    member_agent_id = normalize_agent_id(member_agent_id)
    if member_agent_id == "team":
        raise ValueError("team_member_agent_unavailable")

    from src.agents.core.base import AgentFactory

    registered_agent_ids = {agent["id"] for agent in AgentFactory.list_agents()}
    if member_agent_id not in registered_agent_ids:
        raise ValueError("team_member_agent_unavailable")

    role_ids: list[str] = []
    role_agent_map: dict[str, list[str] | None] = {}
    try:
        if user_id:
            from src.infra.agent.config_storage import get_agent_config_storage
            from src.infra.role.manager import get_role_manager
            from src.infra.user.storage import UserStorage

            user = await UserStorage().get_by_id(user_id)
            if not user:
                raise ValueError("team_member_agent_not_allowed")

            storage = get_agent_config_storage()
            role_manager = get_role_manager()
            roles = await role_manager.get_roles_by_names(user.roles or [])
            role_ids = [role.id for role in roles]
            role_agent_map = await storage.get_role_agents_by_ids(role_ids)

        allowed_agents = await AgentFactory.get_filtered_agents(
            user_roles=role_ids,
            role_agent_map=role_agent_map,
        )
        allowed_agent_ids = {agent["id"] for agent in allowed_agents}
        if member_agent_id not in allowed_agent_ids:
            raise ValueError("team_member_agent_not_allowed")
    except ValueError:
        raise
    except Exception as e:
        logger.warning(
            "[TeamAgent] Failed to validate member agent access %s: %s",
            member_agent_id,
            e,
        )
        raise ValueError("team_member_agent_unavailable") from e

    return member_agent_id


def _build_member_agent_mode_sections(
    agent_id: str | None,
    *,
    sandbox_active: bool,
) -> list[str]:
    """Return mode-specific prompt sections for a team member subagent."""
    if not agent_id:
        return []
    if agent_id in {"search", "fast"}:
        return [SEARCH_SANDBOX_SYSTEM_PROMPT if sandbox_active else SEARCH_DEFAULT_SYSTEM_PROMPT]
    return []
