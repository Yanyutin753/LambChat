"""Owner-facing management reuses memory CRUD with an explicit assistant partition."""

from src.infra.assistant.memory import assistant_memory_partition
from src.infra.assistant.store import AssistantStore
from src.kernel.errors import AppError, ErrorCode


async def memory_management_query(
    user_id: str, assistant_id: str | None, discussion_id: str | None = None
) -> dict:
    query = {"user_id": user_id}
    if discussion_id is not None:
        from src.infra.assistant.discussions import DiscussionStore, validate_discussion

        discussion = await DiscussionStore().get(user_id, discussion_id)
        if not assistant_id or not discussion or discussion["assistant_id"] != assistant_id:
            raise AppError(ErrorCode.NOT_FOUND)
        await validate_discussion(discussion, user_id, require_active=False)
        query.update(scope="project", project_id=f"assistant-discussion-memory:{discussion_id}")
    elif assistant_id is not None:
        assistant = await AssistantStore().get(user_id, assistant_id)
        if assistant is None:
            raise AppError(ErrorCode.NOT_FOUND)
        query.update(scope="project", project_id=await assistant_memory_partition(assistant))
    return query


async def authorize_memory_project(user_id: str, project_id: str) -> None:
    from src.infra.folder.storage import get_project_storage

    if project_id.startswith("assistant-discussion-memory:"):
        from src.infra.assistant.discussions import DiscussionStore, validate_discussion

        discussion = await DiscussionStore().get(
            user_id, project_id.removeprefix("assistant-discussion-memory:")
        )
        await validate_discussion(discussion, user_id, require_active=False)
        return
    if project_id.startswith("assistant-memory:"):
        if (
            await AssistantStore().get(user_id, project_id.removeprefix("assistant-memory:"))
            is None
        ):
            raise AppError(ErrorCode.NOT_FOUND)
        return
    if project_id.startswith("assistant-project-memory:"):
        project_id = project_id.removeprefix("assistant-project-memory:")
    if not await get_project_storage().get_by_id(project_id, user_id):
        raise AppError(ErrorCode.PROJECT_NOT_FOUND)
