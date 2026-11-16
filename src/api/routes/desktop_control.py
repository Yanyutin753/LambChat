"""Authority for a desktop control lease bound to an owned live execution."""

from fastapi import APIRouter, Depends

from src.api.deps import require_pat_only
from src.api.routes.sandbox import _owned_session_or_404
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


@router.get("/control/status")
async def desktop_control_lifecycle(
    session_id: str,
    run_id: str,
    user: TokenPayload = Depends(require_pat_only("sandbox:execute")),
) -> dict[str, bool]:
    """A device may retain control only while its exact owning execution is running."""
    session = await _owned_session_or_404(user, session_id)
    metadata = session.metadata or {}
    return {
        "active": bool(run_id)
        and metadata.get("current_run_id") == run_id
        and metadata.get("task_status") == "running"
    }
