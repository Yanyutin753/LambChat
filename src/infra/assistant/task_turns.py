"""Explicit human turns retain the task's admitted configuration and execution bounds."""

from src.infra.task.background_task_store import BackgroundTaskStore
from src.infra.task.background_tasks import apply_background_restrictions
from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode


async def prepare_task_turn(request, user, metadata):
    task_id = (metadata or {}).get("background_task_id")
    if not task_id:
        return None
    record = await BackgroundTaskStore().collection.find_one(
        {"_id": task_id, "user_id": user.sub, "session_id": request.session_id}
    )
    if record is None:
        raise AppError(ErrorCode.FORBIDDEN)
    if not record.get("assistant_id"):
        return None
    from src.infra.assistant.discussions import task_discussion
    from src.infra.assistant.tasks import validate_task_assistant

    await validate_task_assistant(record, user.sub)
    await task_discussion(record, user.sub)
    config = record["config"]
    project_id = config.get("project_id")
    if project_id:
        from src.infra.folder.storage import get_project_storage

        if await get_project_storage().get_by_id(project_id, user.sub) is None:
            raise AppError(ErrorCode.PROJECT_NOT_FOUND)
    request.agent_options = dict(record["agent_options"])
    request.persona_preset_id = config.get("persona_preset_id")
    request.project_id = project_id
    request.team_id = config.get("team_id")
    apply_background_restrictions(request, config)
    return record


async def authorize_task_turn(record, run_id):
    if record["state"] != "submitted":
        raise AppError(ErrorCode.CONFLICT)
    changed = await BackgroundTaskStore().collection.update_one(
        {
            "_id": record["_id"],
            "user_id": record["user_id"],
            "session_id": record["session_id"],
            "state": "submitted",
            "authorized_run_id": record.get("authorized_run_id"),
        },
        {
            "$set": {"authorized_run_id": run_id, "authorized_run_started_at": utc_now()},
            "$inc": {"followup_count": 1},
        },
    )
    if not changed.modified_count:
        raise AppError(ErrorCode.CONFLICT)
