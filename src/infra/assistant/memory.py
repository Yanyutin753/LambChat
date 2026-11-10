"""Assistant partitions reuse memory storage without exposing the owner's personal bank."""

from src.infra.assistant.store import AssistantStore
from src.kernel.errors import AppError, ErrorCode


async def assistant_memory_partition(assistant):
    if assistant.memory_mode == "project":
        from src.infra.folder.storage import get_project_storage

        if (
            not assistant.project_id
            or await get_project_storage().get_by_id(assistant.project_id, assistant.user_id)
            is None
        ):
            raise AppError(ErrorCode.PROJECT_NOT_FOUND)
        return f"assistant-project-memory:{assistant.project_id}"
    return f"assistant-memory:{assistant.id}"


async def session_assistant_partition(session_id, user_id, metadata):
    from src.infra.assistant.discussions import (
        DiscussionStore,
        is_discussion_session,
        validate_discussion,
    )

    if session_id.startswith("sch_conversation_"):
        from src.infra.assistant.service import assistant_scope_session, conversation_assistant

        target = await assistant_scope_session(user_id, session_id)
        assistant = await conversation_assistant(user_id, target)
        if assistant is None:
            return None
        return await session_assistant_partition(target, user_id, {"assistant_id": assistant.id})
    if is_discussion_session(session_id):
        discussion = await DiscussionStore().get(user_id, session_id)
        await validate_discussion(discussion, user_id, require_active=False)
        return f"assistant-discussion-memory:{session_id}"
    assistant = None
    if metadata.get("assistant_id"):
        assistant = await AssistantStore().for_session(user_id, session_id)
        if assistant is None or assistant.id != metadata["assistant_id"]:
            raise AppError(ErrorCode.FORBIDDEN)
    elif metadata.get("background_task_id"):
        from src.infra.task.background_task_store import BackgroundTaskStore

        record = await BackgroundTaskStore().collection.find_one(
            {"_id": metadata["background_task_id"], "user_id": user_id, "session_id": session_id}
        )
        if record is None:
            raise AppError(ErrorCode.FORBIDDEN)
        if record.get("assistant_id"):
            from src.infra.assistant.discussions import task_discussion

            discussion = await task_discussion(record, user_id)
            if discussion:
                return f"assistant-discussion-memory:{discussion['session_id']}"
            assistant = await AssistantStore().get(user_id, record["assistant_id"])
            if assistant is None or assistant.session_id != (
                record.get("assistant_source_session_id") or record["parent_session_id"]
            ):
                raise AppError(ErrorCode.FORBIDDEN)
    return await assistant_memory_partition(assistant) if assistant else None
