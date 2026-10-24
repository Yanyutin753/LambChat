"""Current account capabilities shared by tool discovery and invocation."""

from collections.abc import Iterable

from langchain_core.tools import BaseTool

from src.infra.auth.authority import authority_lookup
from src.infra.role.storage import ROLE_BATCH_LOOKUP_LIMIT, RoleStorage
from src.infra.user.storage import UserStorage
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

TOOL_PERMISSIONS = {
    "env_var_list": "envvar:read",
    "env_var_set": "envvar:write",
    "env_var_delete": "envvar:delete",
    "env_var_delete_all": "envvar:delete",
    "save_persona_preset": "persona_preset:write",
    "create_persona_preset": "persona_preset:write",
    "update_persona_preset": "persona_preset:write",
    "search_persona_presets": "persona_preset:read",
    "create_agent_team": "team:write",
    "search_conversation_history": "session:read",
    "get_conversation_detail": "session:read",
    "memory_retain": "memory:write",
    "memory_recall": "memory:read",
    "memory_delete": "memory:delete",
    "scheduled_task_create": "scheduled_task:write",
    "scheduled_task_list": "scheduled_task:read",
    "scheduled_task_update": "scheduled_task:write",
    "scheduled_task_delete": "scheduled_task:delete",
}


async def resolve_tool_user(user_id: str | None) -> TokenPayload | None:
    """Never trust the role snapshot stored in a running graph or deferred tool."""
    if not user_id:
        return None
    async with authority_lookup():
        user = await UserStorage().get_by_id(user_id)
        if not user or not user.is_active:
            return None
        role_names = user.roles or []
        role_storage = RoleStorage()
        roles = []
        for start in range(0, len(role_names), ROLE_BATCH_LOOKUP_LIMIT):
            roles.extend(
                await role_storage.get_by_names(role_names[start : start + ROLE_BATCH_LOOKUP_LIMIT])
            )
        permissions = {
            str(permission.value) if hasattr(permission, "value") else str(permission)
            for role in roles
            for permission in role.permissions
        }
        return TokenPayload(
            sub=user.id,
            username=user.username,
            roles=[role.name for role in roles],
            permissions=sorted(permissions),
        )


async def has_tool_permission(user_id: str | None, permission: str) -> bool:
    user = await resolve_tool_user(user_id)
    return bool(user and permission in user.permissions)


async def require_tool_file_read(user_id: str | None) -> None:
    if not await has_tool_permission(user_id, "file:read"):
        raise AppError(ErrorCode.PERMISSION_MISSING, args={"permission": "file:read"})


async def filter_authorized_tools(tools: Iterable[BaseTool], user_id: str | None) -> list[BaseTool]:
    user = await resolve_tool_user(user_id)
    permissions = set(user.permissions) if user else set()
    return [tool for tool in tools if TOOL_PERMISSIONS.get(tool.name) in permissions]
