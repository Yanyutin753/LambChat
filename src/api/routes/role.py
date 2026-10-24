"""Role metadata, delegation, assignment and quota operations have distinct authority."""

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_current_user_required, require_permissions
from src.infra.auth.delegation import (
    authority_mutation,
    authorize_assignment_target,
    authorize_permission_grants,
    ensure_role_not_assigned,
    ensure_role_within_scope,
    ensure_usable_administrator,
    is_system_administrator,
    require_capability,
    resolve_actor_agent_ids,
)
from src.infra.logging import get_logger
from src.infra.role.manager import RoleManager
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.role import (
    Role,
    RoleCreate,
    RoleLimits,
    RoleListResponse,
    RoleQuotaUpdate,
    RoleUpdate,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)
_GRANT_FIELDS = {"permissions", "grantable_permissions", "assignable_role_ids"}
_QUOTA_FIELDS = {"five_hour_budget_usd", "weekly_budget_usd"}


async def _authorize_role_fields(
    actor: TokenPayload, data: RoleCreate | RoleUpdate, target: Role | None = None
) -> None:
    fields = data.model_fields_set
    if target is None or fields & {"name", "description"} or not fields:
        require_capability(actor, "role:write")
    if fields & _GRANT_FIELDS:
        values = [getattr(data, name) for name in _GRANT_FIELDS & fields]
        if target is not None or any(values):
            authorize_permission_grants(
                actor,
                data.permissions or [],
                data.grantable_permissions or [],
                data.assignable_role_ids or [],
            )
            if (
                target is not None
                and target.name in actor.roles
                and not is_system_administrator(actor)
            ):
                raise AppError(ErrorCode.CANNOT_CHANGE_OWN_ROLE_PERMISSIONS)
    if data.limits is not None:
        limit_fields = data.limits.model_fields_set
        if limit_fields & _QUOTA_FIELDS:
            require_capability(actor, "usage:quota_manage")
        if limit_fields - _QUOTA_FIELDS:
            require_capability(actor, "role:write")
    if "allowed_agents" in fields:
        require_capability(actor, "agent:assign")
        if not is_system_administrator(actor):
            allowed = await resolve_actor_agent_ids(actor)
            if not set(data.allowed_agents or []).issubset(allowed):
                raise AppError(ErrorCode.FORBIDDEN)
    if "unrestricted_models" in fields:
        require_capability(actor, "model:assign")
        if data.unrestricted_models and not is_system_administrator(actor):
            own = await RoleManager().get_roles_by_names(actor.roles)
            if not any(role.unrestricted_models for role in own):
                raise AppError(ErrorCode.FORBIDDEN)
    if target is not None:
        if fields & {"allowed_agents", "unrestricted_models"}:
            authorize_assignment_target(actor, target)
        ensure_role_within_scope(actor, target)
        if data.name and data.name != target.name:
            await ensure_role_not_assigned(target)


@router.get("/", response_model=RoleListResponse)
async def list_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    q: str | None = None,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    if not set(current_user.permissions) & {
        "role:read",
        "user:assign_roles",
        "model:assign",
        "agent:assign",
    }:
        raise AppError(ErrorCode.PERMISSION_MISSING, args={"permission": "role:read"})
    manager = RoleManager()
    if not set(current_user.permissions) & {"role:read", "model:assign", "agent:assign"}:
        roles = [
            role
            for role_id in dict.fromkeys(current_user.assignable_role_ids)
            if (role := await manager.get_role(role_id))
        ]
        if q:
            roles = [
                role
                for role in roles
                if q.casefold() in f"{role.name} {role.description or ''}".casefold()
            ]
        roles.sort(key=lambda role: role.name)
        return RoleListResponse(
            roles=roles[skip : skip + limit], total=len(roles), skip=skip, limit=limit
        )
    roles = await manager.list_roles(skip, limit, q)
    total = await manager.count_roles(q)
    return RoleListResponse(roles=roles, total=total, skip=skip, limit=limit)


@router.post("/", response_model=Role)
async def create_role(
    role_data: RoleCreate,
    current_user: TokenPayload = Depends(require_permissions("role:write")),
):
    async with authority_mutation(current_user) as actor:
        await _authorize_role_fields(actor, role_data)
        role = await RoleManager().create_role(role_data)
        from src.infra.agent.config_storage import get_agent_config_storage

        await get_agent_config_storage().set_role_agents(
            role.id, role.name, role_data.allowed_agents
        )
        logger.info(
            "Role created actor=%s target=%s fields=%s",
            actor.sub,
            role.id,
            sorted(role_data.model_fields_set),
        )
        return role


@router.get("/{role_id}", response_model=Role)
async def get_role(
    role_id: str,
    _: TokenPayload = Depends(require_permissions("role:read")),
):
    role = await RoleManager().get_role(role_id)
    if not role:
        raise AppError(ErrorCode.ROLE_NOT_FOUND)
    return role


@router.put("/{role_id}", response_model=Role)
async def update_role(
    role_id: str,
    role_data: RoleUpdate,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    async with authority_mutation(current_user) as actor:
        manager = RoleManager()
        target = await manager.get_role(role_id)
        if not target:
            raise AppError(ErrorCode.ROLE_NOT_FOUND)
        await _authorize_role_fields(actor, role_data, target)
        if any(
            getattr(role_data, name) is None
            for name in role_data.model_fields_set
            & (_GRANT_FIELDS | {"allowed_agents", "unrestricted_models", "limits"})
        ):
            raise AppError(ErrorCode.BAD_REQUEST)
        if (
            "system:admin" in target.permissions
            and role_data.permissions is not None
            and "system:admin" not in role_data.permissions
        ):
            await ensure_usable_administrator(removed_role_name=target.name)
        if role_data.limits is not None:
            existing = target.limits.model_dump() if target.limits else {}
            role_data = role_data.model_copy(
                update={
                    "limits": RoleLimits(
                        **{**existing, **role_data.limits.model_dump(exclude_unset=True)}
                    )
                }
            )
        role = await manager.update_role(role_id, role_data)
        if not role:
            raise AppError(ErrorCode.ROLE_NOT_FOUND)
        if role_data.allowed_agents is not None:
            from src.infra.agent.config_storage import get_agent_config_storage

            await get_agent_config_storage().set_role_agents(
                role.id, role.name, role_data.allowed_agents
            )
        logger.info(
            "Role updated actor=%s target=%s fields=%s",
            actor.sub,
            role_id,
            sorted(role_data.model_fields_set),
        )
        return role


@router.patch("/{role_id}/usage-quota", response_model=Role)
async def update_role_usage_quota(
    role_id: str,
    quota: RoleQuotaUpdate,
    current_user: TokenPayload = Depends(require_permissions("usage:quota_manage")),
) -> Role:
    async with authority_mutation(current_user) as actor:
        require_capability(actor, "usage:quota_manage")
        role = await RoleManager().update_usage_quota(role_id, quota)
        logger.info(
            "Role quota updated actor=%s target=%s fields=%s",
            actor.sub,
            role_id,
            sorted(quota.model_fields_set),
        )
        return role


@router.delete("/{role_id}")
async def delete_role(
    role_id: str,
    current_user: TokenPayload = Depends(require_permissions("role:delete")),
):
    async with authority_mutation(current_user) as actor:
        require_capability(actor, "role:delete")
        manager = RoleManager()
        target = await manager.get_role(role_id)
        if not target:
            raise AppError(ErrorCode.ROLE_NOT_FOUND)
        ensure_role_within_scope(actor, target)
        await ensure_role_not_assigned(target)
        await manager.delete_role(role_id)
        logger.info("Role deleted actor=%s target=%s", actor.sub, role_id)
        return {"status": "deleted"}
