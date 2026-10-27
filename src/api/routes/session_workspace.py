"""Workspace edits share chat admission's lease and validate the complete binding."""

from fastapi import Depends

from src.api.deps import require_permissions
from src.infra.backend.workspace_selection import validate_workspace_options
from src.infra.session.manager import SessionManager
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.session import SessionUpdate
from src.kernel.schemas.user import TokenPayload


def edits_workspace(metadata: dict | None) -> bool:
    return metadata is not None and any(
        key == "agent_options" or key.startswith("agent_options.") for key in metadata
    )


async def update_workspace(manager, session_id, data, user):
    from src.infra.scheduler.conversation import conversation_submission

    async with conversation_submission(session_id, user.sub):
        session = await manager.get_session(session_id)
        if session is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND)
        if session.user_id != user.sub:
            raise AppError(ErrorCode.SESSION_ACCESS_DENIED)
        if (session.metadata or {}).get("persistent_goal_status") in {"active", "waiting_human"}:
            raise AppError(ErrorCode.CONFLICT)
        patch = dict(data.metadata or {})
        stored = (session.metadata or {}).get("agent_options")
        options = dict(stored) if isinstance(stored, dict) else {}
        if "agent_options" in patch:
            replacement = patch["agent_options"]
            if not isinstance(replacement, dict):
                raise AppError(ErrorCode.SANDBOX_WORKSPACE_INVALID)
            if any(key.startswith("agent_options.") for key in patch):
                raise AppError(ErrorCode.BAD_REQUEST)
            options = replacement
        else:
            changes = {
                key.removeprefix("agent_options."): value
                for key, value in patch.items()
                if key.startswith("agent_options.")
            }
            if any("." in key or key.startswith("$") for key in changes):
                raise AppError(ErrorCode.BAD_REQUEST)
            # A machine-only switch cannot retain a folder bound to the old machine.
            if (
                "sandbox_machine_id" in changes
                and changes["sandbox_machine_id"] != options.get("sandbox_machine_id")
                and "sandbox_workspace" not in changes
            ):
                changes["sandbox_workspace"] = ""
                patch["agent_options.sandbox_workspace"] = ""
            options.update(changes)
        validate_workspace_options(options)
        return await manager.update_session(
            session_id, SessionUpdate(name=data.name, metadata=patch)
        )


async def get_workspace_locations(
    session_id: str,
    user: TokenPayload = Depends(require_permissions("session:read")),
):
    """List retained source locations; this endpoint never starts or moves a workspace."""
    session = await SessionManager().get_session(session_id)
    if session is None:
        raise AppError(ErrorCode.SESSION_NOT_FOUND)
    if session.user_id != user.sub:
        raise AppError(ErrorCode.SESSION_ACCESS_DENIED)
    from src.infra.session.workspace_locations import list_workspace_locations

    return {"locations": await list_workspace_locations(user.sub, session_id)}
