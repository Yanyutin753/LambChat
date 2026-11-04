"""Persist run completion and report only accepted notification transports."""

from typing import Any

from src.infra.logging import get_logger
from src.infra.session.favorites import is_session_favorite
from src.infra.task.status import TaskStatus

logger = get_logger(__name__)


async def send_task_notification(
    session_id: str,
    run_id: str,
    status: TaskStatus,
    user_id: str,
    message: str | None = None,
    *,
    prepared_completion: dict[str, Any] | None = None,
) -> bool:
    """Return whether notification finalization can be acknowledged."""
    try:
        from src.infra.websocket import get_connection_manager

        notification: dict[str, Any] = {
            "type": "task:complete",
            "data": {
                "session_id": session_id,
                "run_id": run_id,
                "status": status.value,
            },
        }
        if message:
            notification["data"]["message"] = message

        # 附带最新的 unread_count，让前端实时更新侧边栏
        session_metadata = {}
        try:
            from src.infra.session.manager import SessionManager

            session = await SessionManager().get_session(session_id)
            if session:
                session_metadata = session.metadata or {}
                favorites_project_id = None
                if session.user_id:
                    from src.infra.folder.storage import get_project_storage

                    favorites_project = await get_project_storage().get_by_type(
                        session.user_id,
                        "favorites",
                    )
                    favorites_project_id = favorites_project.id if favorites_project else None
                notification["data"]["unread_count"] = getattr(session, "unread_count", 0)
                notification["data"]["project_id"] = (
                    session.metadata.get("project_id") if session.metadata else None
                )
                notification["data"]["scheduled_task_id"] = (
                    session.metadata.get("scheduled_task_id") if session.metadata else None
                )
                notification["data"]["is_favorite"] = is_session_favorite(
                    session.metadata,
                    favorites_project_id,
                )
        except Exception:
            pass

        if run_id.startswith("scheduled-") or session_metadata.get("scheduled_task_id"):
            from src.infra.scheduler.conversation import completion_context

            scheduled_task_id, quiet = await completion_context(session_id, run_id, status.value)
            if quiet or (
                session_metadata.get("scheduled_target_session_id")
                and status == TaskStatus.COMPLETED
            ):
                return True
            if scheduled_task_id:
                notification["data"]["scheduled_task_id"] = scheduled_task_id

        if session_metadata.get("background_rule_id"):
            from src.infra.assistant.rules import quiet_rule_result

            if await quiet_rule_result(session_id, run_id, user_id, status.value):
                return True

        from src.infra.task.completion_events import TaskCompletionStore, prepare_completion

        completion = (
            dict(prepared_completion)
            if prepared_completion is not None
            else prepare_completion(notification["data"], session_metadata)
        )
        if completion is None:
            return True
        from src.infra.task.completion_recovery import TaskCompletionOutbox

        notification["data"] = completion
        outbox = TaskCompletionOutbox()
        try:
            await outbox.stage(session_id, user_id, completion)
        except Exception as error:
            logger.warning("Failed to stage task completion: %s", error)
        try:
            notification["data"], fresh = await TaskCompletionStore().record_once(
                user_id, completion
            )
        except Exception as error:
            logger.warning("Failed to persist task completion: %s", error)
            return False
        try:
            await outbox.clear(session_id, user_id, completion["dedupe_key"])
        except Exception as error:
            logger.warning("Failed to clear delivered completion marker: %s", error)
        if not fresh:
            return True
        if session_metadata.get("background_assistant_id") and not session_metadata.get(
            "channel_delivery"
        ):
            from src.infra.assistant.delivery import deliver_assistant_task_result

            if await deliver_assistant_task_result(
                user_id, session_id, run_id, completion["status"], completion.get("message")
            ):
                await TaskCompletionStore().record_delivery(
                    user_id, completion["dedupe_key"], "channel", 1
                )
        manager = get_connection_manager()
        delivered_count = await manager.send_to_user_with_broadcast(user_id, notification)
        if delivered_count <= 0:
            logger.warning(
                "Task notification had no active WebSocket delivery: "
                "user_id=%s, session=%s, status=%s, delivered=%s",
                user_id,
                session_id,
                status.value,
                delivered_count,
            )
            # Web Push fallback when WebSocket has no active connection
            push_delivered = 0
            try:
                from src.infra.push.manager import PushManager

                push_mgr = PushManager()
                push_payload = {
                    "title": "LambChat",
                    "body": notification["data"].get("message")
                    or f"Task {notification['data']['status']}",
                    "url": (
                        f"/scheduled-tasks/{completion['scheduled_task_id']}"
                        if completion.get("notification_kind")
                        in {"scheduled_failure", "scheduled_model_unavailable"}
                        and completion.get("scheduled_task_id")
                        else f"/chat/{session_id}"
                    ),
                }
                push_delivered = await push_mgr.send_push_to_user(user_id, push_payload)
                if push_delivered > 0:
                    await TaskCompletionStore().record_delivery(
                        user_id, completion["dedupe_key"], "web_push", push_delivered
                    )
                    logger.info(
                        "Push notification delivered as fallback: user_id=%s, count=%s",
                        user_id,
                        push_delivered,
                    )
            except Exception as push_err:
                logger.warning("Failed to send push notification fallback: %s", push_err)
            # 渠道兜底：WS 与 Web Push 均未送达时，把结果推到用户配置的
            # IM 渠道（push 已送达则不再双推手机）
            if push_delivered <= 0:
                try:
                    from src.infra.channel.fallback import deliver_task_fallback

                    fallback_delivered = await deliver_task_fallback(
                        user_id=user_id,
                        session_id=session_id,
                        run_id=run_id,
                        status_value=notification["data"]["status"],
                        message=notification["data"].get("message"),
                    )
                    if fallback_delivered:
                        await TaskCompletionStore().record_delivery(
                            user_id, completion["dedupe_key"], "channel", 1
                        )
                except Exception as channel_err:
                    logger.warning("Failed to send channel fallback notification: %s", channel_err)
        else:
            await TaskCompletionStore().record_delivery(
                user_id, completion["dedupe_key"], "websocket", delivered_count
            )
            logger.info(
                "Task notification delivered: user_id=%s, session=%s, status=%s, delivered=%s",
                user_id,
                session_id,
                status.value,
                delivered_count,
            )
    except Exception as e:
        logger.warning(f"Failed to send task notification: {e}")
        return False
    return True
