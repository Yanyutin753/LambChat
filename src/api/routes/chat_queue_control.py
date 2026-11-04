"""Run-fenced follow-up controls shared by every API replica."""

import uuid

from fastapi import APIRouter, Depends, Query

from src.api.deps import require_permissions
from src.infra.task.status import TaskStatus
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def validate_follow_up_submission(session, expected_run_id: str) -> None:
    metadata = session.metadata or {}
    if (
        metadata.get("current_run_id") != expected_run_id
        or metadata.get("queue_paused_run_id") == expected_run_id
    ):
        raise AppError(ErrorCode.CONFLICT)


async def set_queue_paused(session, paused: bool) -> None:
    from src.infra.session.manager import SessionManager

    run_id = (session.metadata or {}).get("current_run_id")
    if not run_id:
        return
    updated = await SessionManager().storage.update_metadata_for_run(
        session.id,
        run_id,
        {
            "queue_paused_run_id": run_id if paused else None,
            "queue_pause_token": uuid.uuid4().hex if paused else None,
        },
    )
    if not updated:
        raise AppError(ErrorCode.CONFLICT)


@router.post("/sessions/{session_id}/queue/resume")
async def resume_follow_up_queue(
    session_id: str,
    run_id: str = Query(..., min_length=1, max_length=128),
    pause_token: str = Query(..., min_length=1, max_length=128),
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    from src.api.routes.chat import _get_owned_session
    from src.infra.scheduler.conversation import conversation_submission

    async with conversation_submission(session_id, user.sub, allow_busy=True):
        session = await _get_owned_session(session_id, user)
        metadata = session.metadata or {}
        if (
            metadata.get("current_run_id") != run_id
            or metadata.get("queue_pause_token") != pause_token
        ):
            raise AppError(ErrorCode.CONFLICT)
        await set_queue_paused(session, False)
        return {"session_id": session_id, "run_id": run_id, "queue_paused": False}


async def queue_status(session_id, session, run_id, task_manager):
    run_id = run_id or (session.metadata or {}).get("current_run_id")
    if run_id:
        status = await task_manager.get_run_status(session_id, run_id)
        error = await task_manager.get_run_error(run_id)
    else:
        status = await task_manager.get_status(session_id)
        error = await task_manager.get_error(session_id)

    if status not in {TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.EXPIRED}:
        error = None

    # A recovered run can retain an older trace error; prefer its current session code.
    error_code = None
    if error:
        metadata = session.metadata or {}
        if not run_id or metadata.get("current_run_id") == run_id:
            error_code = metadata.get("task_error_code")
        error_code = error_code or ("internal_error" if status is TaskStatus.FAILED else None)

    result = {
        "session_id": session_id,
        "run_id": run_id,
        "status": status.value,
        "error": error,
        "queue_pause_token": (session.metadata or {}).get("queue_pause_token")
        if (session.metadata or {}).get("current_run_id") == run_id
        else None,
        "queue_paused": bool(
            run_id and (session.metadata or {}).get("queue_paused_run_id") == run_id
        ),
    }
    if error_code:
        result["code"] = error_code
    return result
