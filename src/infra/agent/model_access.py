"""Model access helpers shared by chat execution and public model listing."""

from __future__ import annotations

from src.kernel.schemas.user import TokenPayload

ROLE_MODEL_ACCESS_LIMIT = 100


async def resolve_user_allowed_model_ids(user: TokenPayload) -> list[str] | None:
    """Return allowed model IDs for this user, or None when unrestricted.

    Missing assignments grant nothing. Only a persisted unrestricted_models flag
    grants unrestricted access; legacy roles receive it in the startup migration.

    角色与角色-模型配置均批量读取；合并阶段保持角色顺序与去重语义。
    """
    if not user.roles:
        return []

    from src.infra.agent.config_storage import get_agent_config_storage
    from src.infra.role.manager import get_role_manager

    storage = get_agent_config_storage()
    role_manager = get_role_manager()
    allowed: list[str] = []
    seen: set[str] = set()

    roles = await role_manager.get_roles_by_names(user.roles)
    models_by_role = await storage.get_role_models_by_ids([role.id for role in roles])

    for role in roles:
        if getattr(role, "unrestricted_models", False):
            return None
        role_models = models_by_role.get(role.id) or []
        for model_id in role_models:
            if model_id not in seen:
                seen.add(model_id)
                allowed.append(model_id)
                if len(allowed) >= ROLE_MODEL_ACCESS_LIMIT:
                    return allowed

    return allowed
