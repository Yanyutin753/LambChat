"""User context helpers for workflow execution entrypoints."""

from __future__ import annotations

from src.kernel.schemas.user import TokenPayload


async def workflow_user_for_user_id(user_id: str) -> TokenPayload:
    """Build the user payload used by workflow runs and nested tool execution."""
    roles, _is_admin = await _resolve_user_workflow_access(user_id)
    return TokenPayload(
        sub=user_id,
        username=user_id,
        roles=roles,
        permissions=["workflow:read", "workflow:run"],
    )


async def _resolve_user_workflow_access(user_id: str) -> tuple[list[str], bool]:
    try:
        from src.infra.mcp.quota import resolve_user_mcp_access

        return await resolve_user_mcp_access(user_id)
    except Exception:
        return [], False


__all__ = ["workflow_user_for_user_id"]
