"""Explicit, bounded authority for account and role administration."""

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from bson import ObjectId

from src.infra.auth.authority import authority_lookup
from src.infra.role.manager import RoleManager
from src.infra.role.storage import RoleStorage
from src.infra.storage.redis import get_redis_client
from src.infra.user.storage import UserStorage
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.role import Role
from src.kernel.schemas.user import TokenPayload, User


def require_capability(actor: TokenPayload, permission: str) -> None:
    if permission not in actor.permissions:
        raise AppError(ErrorCode.PERMISSION_MISSING, args={"permission": permission})


def is_system_administrator(actor: TokenPayload) -> bool:
    return "system:admin" in actor.permissions


@asynccontextmanager
async def authority_mutation(actor: TokenPayload) -> AsyncIterator[TokenPayload]:
    """Serialize authority changes across workers, then re-read the caller's authority."""
    from src.api.deps import _load_user_payload

    async with authority_lookup():
        lock = get_redis_client().lock(
            "auth:administration:mutation", timeout=60, thread_local=False
        )
        if not await lock.acquire(blocking=False):
            raise AppError(ErrorCode.CONFLICT)
        try:
            # Expire the operation before its lease, never execute after losing exclusivity.
            async with asyncio.timeout(20):
                yield await _load_user_payload(actor.sub)
        finally:
            await lock.release()


def ensure_role_within_scope(actor: TokenPayload, role: Role) -> None:
    if is_system_administrator(actor):
        return
    if (
        not set(role.permissions).issubset(actor.permissions)
        or not set(role.grantable_permissions).issubset(actor.grantable_permissions)
        or not set(role.assignable_role_ids).issubset(actor.assignable_role_ids)
    ):
        raise AppError(ErrorCode.FORBIDDEN)


async def ensure_user_target(actor: TokenPayload, target: User) -> list[Role]:
    roles = await RoleManager().get_roles_by_names(target.roles)
    # Unresolved authority is never an ordinary account by default.
    if not is_system_administrator(actor) and set(target.roles) != {role.name for role in roles}:
        raise AppError(ErrorCode.FORBIDDEN)
    for role in roles:
        ensure_role_within_scope(actor, role)
    await ensure_execution_scope(actor, roles)
    return roles


async def authorize_role_assignment(actor: TokenPayload, names: list[str]) -> list[Role]:
    require_capability(actor, "user:assign_roles")
    roles = await RoleManager().get_roles_by_names(names)
    if set(names) != {role.name for role in roles}:
        raise AppError(ErrorCode.ROLE_NOT_FOUND)
    if not is_system_administrator(actor):
        for role in roles:
            if role.id not in actor.assignable_role_ids:
                raise AppError(ErrorCode.FORBIDDEN)
            ensure_role_within_scope(actor, role)
        await ensure_execution_scope(actor, roles)
    return roles


async def ensure_execution_scope(actor: TokenPayload, target_roles: list[Role]) -> None:
    """Credentials and role assignment must not unlock stronger model or Agent access."""
    if is_system_administrator(actor):
        return
    from src.infra.agent.model_access import resolve_user_allowed_model_ids

    target = TokenPayload(sub="role-scope", username="", roles=[role.name for role in target_roles])
    own_models = await resolve_user_allowed_model_ids(actor)
    target_models = await resolve_user_allowed_model_ids(target)
    if own_models is not None:
        if target_models is None:
            raise AppError(ErrorCode.FORBIDDEN)
        extra = set(target_models) - set(own_models)
        if extra:
            from src.infra.agent.model_storage import get_model_storage

            by_id, _ = await get_model_storage().get_many_by_ids_and_values(list(extra))
            # A value grant covers every channel; a single ID must never imply that grant.
            if any(
                identifier not in by_id or by_id[identifier].value not in own_models
                for identifier in extra
            ):
                raise AppError(ErrorCode.FORBIDDEN)
    own_agents = await resolve_actor_agent_ids(actor)
    target_agents = await resolve_actor_agent_ids(target)
    if not target_agents.issubset(own_agents):
        raise AppError(ErrorCode.FORBIDDEN)


def authorize_permission_grants(
    actor: TokenPayload,
    permissions: Iterable[str],
    grantable_permissions: Iterable[str],
    assignable_role_ids: Iterable[str],
) -> None:
    require_capability(actor, "role:grant")
    if is_system_administrator(actor):
        return
    requested = set(permissions) | set(grantable_permissions)
    if (
        "system:admin" in requested
        or not requested.issubset(actor.permissions)
        or not requested.issubset(actor.grantable_permissions)
        or not set(assignable_role_ids).issubset(actor.assignable_role_ids)
    ):
        raise AppError(ErrorCode.FORBIDDEN)


async def ensure_usable_administrator(
    *, excluded_user_id: str | None = None, removed_role_name: str | None = None
) -> None:
    """A destructive change must leave an active highest-trust account able to log in."""
    names = [
        role["name"]
        async for role in RoleStorage().collection.find({"permissions": "system:admin"})
        if role["name"] != removed_role_name
    ]
    oauth_providers = [
        provider
        for provider in ("GOOGLE", "GITHUB", "APPLE")
        if getattr(settings, f"OAUTH_{provider}_ENABLED")
        and getattr(settings, f"OAUTH_{provider}_CLIENT_ID")
        and getattr(settings, f"OAUTH_{provider}_CLIENT_SECRET")
        and (provider != "APPLE" or (settings.OAUTH_APPLE_TEAM_ID and settings.OAUTH_APPLE_KEY_ID))
    ]
    query: dict = {
        "roles": {"$in": names},
        "is_active": {"$ne": False},
        "$or": [
            {"password_hash": {"$type": "string", "$ne": ""}, "oauth_provider": None},
            {
                "oauth_id": {"$type": "string", "$ne": ""},
                "oauth_provider": {"$in": [provider.lower() for provider in oauth_providers]},
            },
        ],
    }
    if settings.REQUIRE_EMAIL_VERIFICATION:
        query["email_verified"] = {"$ne": False}
    if excluded_user_id is not None:
        try:
            query["_id"] = {"$ne": ObjectId(excluded_user_id)}
        except Exception:
            query["_id"] = {"$ne": excluded_user_id}
    if not names or not await UserStorage().collection.find_one(query):
        raise AppError(ErrorCode.FORBIDDEN)


async def ensure_role_not_assigned(role: Role) -> None:
    # User assignments store role names; renaming/deleting an assigned role breaks access.
    if await UserStorage().collection.find_one({"roles": role.name}):
        raise AppError(ErrorCode.CONFLICT)


async def resolve_actor_agent_ids(actor: TokenPayload) -> set[str]:
    """Use the same effective role mappings and global enablement as Agent execution."""
    from src.agents.core.base import AgentFactory
    from src.infra.agent.config_storage import get_agent_config_storage
    from src.infra.role.manager import get_role_manager

    roles = await get_role_manager().get_roles_by_names(actor.roles)
    if not roles:
        return set()
    role_ids = [role.id for role in roles]
    mappings = await get_agent_config_storage().get_role_agents_by_ids(role_ids)
    agents = await AgentFactory.get_filtered_agents(role_ids, mappings)
    return {agent["id"] for agent in agents}


def authorize_assignment_target(actor: TokenPayload, role: Role) -> None:
    if not is_system_administrator(actor):
        if role.id not in actor.assignable_role_ids:
            raise AppError(ErrorCode.FORBIDDEN)
        ensure_role_within_scope(actor, role)
