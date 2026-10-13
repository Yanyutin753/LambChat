"""Fence detached execution to its registered run and current conversation owner."""

from src.infra.goal_runtime import GoalRunAdmissionError
from src.infra.session.manager import SessionManager
from src.infra.task.background_task_store import BackgroundTaskStore


async def validate_background_run_admission(session_id: str, user_id: str, run_id: str) -> None:
    session = await SessionManager().get_session(session_id)
    metadata = (session.metadata or {}) if session else {}
    task_id = metadata.get("background_task_id")
    if (
        not session
        or session.user_id != user_id
        or not task_id
        or metadata.get("current_run_id") != run_id
    ):
        raise GoalRunAdmissionError("Background task no longer owns this conversation")
    status = metadata.get("task_status")
    if status in {"completed", "cancelled", "cancelling", "expired"} or (
        status == "failed"
        and (
            metadata.get("task_recoverable") is not True
            or metadata.get("task_error_code") == "cancelled"
        )
    ):
        raise GoalRunAdmissionError("Background task is terminal and cannot execute again")
    record = await BackgroundTaskStore().collection.find_one(
        {"_id": task_id, "session_id": session_id, "user_id": user_id}
    )
    if (
        not record
        or record.get("session_id") != session_id
        or record.get("user_id") != user_id
        or record.get("run_id") != run_id
        or record.get("state") not in {"submitting", "submitted", "uncertain"}
    ):
        raise GoalRunAdmissionError("Background task registration no longer authorizes this run")


async def validate_background_resume(storage, session_id: str, user_id: str, run_id: str) -> bool:
    """Later human turns in the child chat have ordinary recovery, not task identity."""
    lookup = getattr(storage, "get_by_session_id", None)
    if not callable(lookup):
        return False
    session = await lookup(session_id)
    if session is None:
        by_id = getattr(storage, "get_by_id", None)
        session = await by_id(session_id) if callable(by_id) else None
    task_id = ((session.metadata or {}) if session else {}).get("background_task_id")
    if not task_id:
        return False
    record = await BackgroundTaskStore().collection.find_one(
        {"_id": task_id, "session_id": session_id, "user_id": user_id}
    )
    if record and record.get("run_id") != run_id:
        return False
    await validate_background_run_admission(session_id, user_id, run_id)
    return True
