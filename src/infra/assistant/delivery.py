"""Return detached results only to their still-authorized originating audience."""

from src.infra.assistant.discussions import task_discussion
from src.infra.channel.fallback import _build_delivery_text
from src.infra.channel.manager import get_channel_coordinator
from src.infra.logging import get_logger
from src.infra.task.background_task_store import BackgroundTaskStore
from src.infra.task.background_tasks import _load_user
from src.kernel.schemas.channel import ChannelType

logger = get_logger(__name__)


async def deliver_assistant_task_result(user_id, session_id, run_id, status, message):
    if status not in {"completed", "failed"}:
        return False
    try:
        record = await BackgroundTaskStore().collection.find_one(
            {"user_id": user_id, "session_id": session_id}
        )
        if not record or not record.get("assistant_id"):
            return False
        await _load_user(user_id)
        discussion = await task_discussion(record, user_id)
        if not discussion:
            return False
        text = await _build_delivery_text(session_id, run_id, status, message)
        if not text:
            return False
        return await get_channel_coordinator().send_message(
            user_id,
            ChannelType(discussion["channel_type"]),
            discussion["chat_id"],
            text,
            instance_id=discussion["channel_instance_id"],
        )
    except Exception as error:
        # Unknown transport outcomes must not replay an external send automatically.
        logger.warning("Assistant task result delivery failed: %s", type(error).__name__)
        return False
