"""Persist failed/uncertain admission as visible work requiring attention."""

from src.infra.task.completion_events import TaskCompletionStore


async def publish_background_attention(record, state, sessions):
    session = await sessions.get_session(record["session_id"])
    if session is None or session.user_id != record["user_id"]:
        raise ValueError("Background attention session ownership changed")
    metadata = session.metadata or {}
    if metadata.get("background_task_id") != record["_id"]:
        raise ValueError("Background attention identity changed")
    busy = metadata.get("current_run_id") == record["run_id"] and metadata.get("task_status") in {
        "queued",
        "pending",
        "starting",
        "running",
        "waiting_human",
        "recovering",
        "cancelling",
    }
    message = (
        "Background task admission needs review; execution outcome is uncertain."
        if state == "uncertain"
        else "Background task could not be admitted; review permissions."
    )
    update = {"background_admission_state": state, "background_admission_error": message}
    if not busy:
        update.update(task_status="failed", task_error=message, current_run_id=record["run_id"])
    await sessions.update_session_metadata(record["session_id"], update)
    data, fresh = await TaskCompletionStore().record_once(
        record["user_id"],
        {
            "session_id": record["session_id"],
            "run_id": record["run_id"],
            "parent_session_id": record["parent_session_id"],
            "status": "waiting_human" if busy else "failed",
            "notification_kind": "waiting_human" if busy else "background_task_complete",
            "message": message,
            "dedupe_key": f"background-attention:{record['_id']}:{state}",
        },
    )
    if not fresh:
        return data
    # A durable journal remains even when real-time delivery is unavailable.
    try:
        from src.infra.websocket import get_connection_manager

        delivered = await get_connection_manager().send_to_user_with_broadcast(
            record["user_id"], {"type": "task:complete", "data": data}
        )
        if delivered <= 0:
            from src.infra.push.manager import PushManager

            await PushManager().send_push_to_user(
                record["user_id"],
                {
                    "title": "LambChat",
                    "body": message,
                    "url": f"/chat/{record['session_id']}",
                },
            )
    except Exception:
        pass
    return data
