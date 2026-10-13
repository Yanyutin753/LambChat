"""Authenticated catch-up for a user's own background completion events."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_current_user_required
from src.infra.task.completion_events import TaskCompletionStore
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


@router.get("/task-completions")
async def list_task_completions(
    cursor: str | None = Query(None, max_length=512),
    since: datetime | None = None,
    limit: int = Query(50, ge=1, le=50),
    user: TokenPayload = Depends(get_current_user_required),
):
    return await TaskCompletionStore().list_for_user(
        user.sub, cursor=cursor, since=since, limit=limit
    )
