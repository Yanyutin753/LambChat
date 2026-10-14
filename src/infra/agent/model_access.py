"""Model access helpers shared by chat execution and public model listing."""

from __future__ import annotations

from src.kernel.schemas.user import TokenPayload

ROLE_MODEL_ACCESS_LIMIT = 100


async def resolve_user_allowed_model_ids(user: TokenPayload) -> list[str] | None:
    """Return allowed model IDs for this user, or None when unrestricted.

    A missing role-model assignment means the role is not configured and remains
    unrestricted for backward compatibility. An existing assignment with an empty
    list means the role allows no models.

    角色与角色-模型配置均批量读取；合并阶段保持角色顺序与去重语义。
    """
    if not user.roles:
        return None

    from src.infra.agent.config_storage import get_agent_config_storage
    from src.infra.role.manager import get_role_manager

    storage = get_agent_config_storage()
    role_manager = get_role_manager()
    allowed: list[str] = []
    seen: set[str] = set()
    has_restricted_role = False

    roles = await role_manager.get_roles_by_names(user.roles)
    models_by_role = await storage.get_role_models_by_ids([role.id for role in roles])

    for role in roles:
        role_models = models_by_role[role.id]
        if role_models is None:
            return None
        has_restricted_role = True
        for model_id in role_models:
            if model_id not in seen:
                seen.add(model_id)
                allowed.append(model_id)
                if len(allowed) >= ROLE_MODEL_ACCESS_LIMIT:
                    return allowed

    return allowed if has_restricted_role else None
