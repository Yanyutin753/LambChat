"""Authenticated, user-owned long-lived assistants."""

import asyncio

from fastapi import APIRouter, Depends, Query, Request

from src.api.deps import require_permissions
from src.infra.assistant.activity import load_assistant_activity
from src.infra.assistant.service import AssistantService, conversation_assistant
from src.kernel.schemas.assistant import (
    Assistant,
    AssistantCreate,
    AssistantList,
    AssistantRuleCreate,
    AssistantTaskCreate,
    AssistantTaskReview,
    AssistantUpdate,
)
from src.kernel.schemas.session import Session
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def _service() -> AssistantService:
    return AssistantService()


def _task_service():
    from src.infra.assistant.tasks import AssistantTaskService

    return AssistantTaskService()


@router.get("/conversation/{session_id}", response_model=Assistant | None)
async def get_conversation_assistant(
    session_id: str,
    user: TokenPayload = Depends(require_permissions("session:read")),
):
    from src.infra.assistant.service import assistant_scope_session

    assistant = await conversation_assistant(user.sub, session_id, store=_service().store)
    if assistant:
        return assistant.model_copy(
            update={"context_session_id": await assistant_scope_session(user.sub, session_id)}
        )
    from src.infra.assistant.discussions import task_discussion
    from src.infra.task.background_task_store import BackgroundTaskStore

    record = await BackgroundTaskStore().collection.find_one(
        {"user_id": user.sub, "session_id": session_id}
    )
    if not record or not record.get("assistant_id"):
        return None
    await task_discussion(record, user.sub)
    assistant = await _service().store.get(user.sub, record["assistant_id"])
    return (
        assistant.model_copy(
            update={
                "context_kind": "task",
                "context_task_id": record["_id"],
                "context_session_id": record.get("assistant_source_session_id")
                or record["parent_session_id"],
            }
        )
        if assistant
        else None
    )


@router.get("", response_model=AssistantList)
async def list_assistants(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    archived: bool = False,
    user: TokenPayload = Depends(require_permissions("session:read")),
):
    store = _service().store
    assistants, total = await asyncio.gather(
        store.list(user.sub, skip=skip, limit=limit, archived=archived),
        store.count(user.sub, archived=archived),
    )
    activity = await load_assistant_activity(user.sub, [item.id for item in assistants])
    assistants = [
        item.model_copy(update={"activity": activity.get(item.id)}) for item in assistants
    ]
    return AssistantList(assistants=assistants, total=total, skip=skip, limit=limit)


@router.post("", response_model=Assistant, status_code=201)
async def create_assistant(
    data: AssistantCreate,
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    return await _service().create(user, data)


@router.post("/chief", response_model=Assistant)
async def open_chief(user: TokenPayload = Depends(require_permissions("chat:write"))):
    return await _service().chief(user)


@router.get("/{assistant_id}/members")
async def get_group_members(
    assistant_id: str,
    user: TokenPayload = Depends(require_permissions("session:read")),
):
    group = await _service().get(user, assistant_id)
    members = []
    for identity in group.member_ids:
        member = await _service().store.get(user.sub, identity)
        if member:
            members.append(
                {
                    "id": member.id,
                    "name": member.name,
                    "status": member.status,
                    "avatar": member.avatar,
                }
            )
    return {"members": members}


@router.get("/{assistant_id}", response_model=Assistant)
async def get_assistant(
    assistant_id: str,
    user: TokenPayload = Depends(require_permissions("session:read")),
):
    return await _service().get(user, assistant_id)


@router.put("/{assistant_id}", response_model=Assistant)
async def update_assistant(
    assistant_id: str,
    data: AssistantUpdate,
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    return await _service().update(user, assistant_id, data)


@router.post("/{assistant_id}/conversation", response_model=Session)
async def open_assistant_conversation(
    assistant_id: str,
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    return await _service().open_conversation(user, assistant_id)


@router.get("/{assistant_id}/tasks")
async def list_assistant_tasks(
    assistant_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: TokenPayload = Depends(require_permissions("session:read")),
):
    return await _task_service().list(user, assistant_id, skip=skip, limit=limit)


@router.post("/{assistant_id}/tasks", status_code=202)
async def create_assistant_task(
    assistant_id: str,
    data: AssistantTaskCreate,
    request: Request,
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    from src.api.routes.chat import _get_language

    return await _task_service().create(user, assistant_id, data, language=_get_language(request))


@router.get("/{assistant_id}/tasks/{task_id}")
async def get_assistant_task(
    assistant_id: str,
    task_id: str,
    user: TokenPayload = Depends(require_permissions("session:read")),
):
    return await _task_service().get(user, assistant_id, task_id)


@router.put("/{assistant_id}/tasks/{task_id}/review")
async def review_assistant_task(
    assistant_id: str,
    task_id: str,
    data: AssistantTaskReview,
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    return await _task_service().review(user, assistant_id, task_id, data)


@router.get("/{assistant_id}/discussions")
async def list_assistant_discussions(
    assistant_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: TokenPayload = Depends(require_permissions("session:read")),
):
    from src.infra.assistant.discussions import DiscussionStore, validate_discussion
    from src.kernel.errors import AppError

    await _service().get(user, assistant_id)
    rows, total = await DiscussionStore().list(user.sub, assistant_id, skip=skip, limit=limit)
    discussions = []
    for row in rows:
        available = True
        try:
            await validate_discussion(row, user.sub, require_active=False)
        except AppError:
            available = False
        discussions.append(
            {
                **{
                    key: row.get(key)
                    for key in ("session_id", "channel_type", "chat_id", "created_at")
                },
                "available": available,
            }
        )
    return {"discussions": discussions, "total": total, "skip": skip, "limit": limit}


@router.post("/{assistant_id}/rules", status_code=201)
async def create_assistant_rule(
    assistant_id: str,
    data: AssistantRuleCreate,
    user: TokenPayload = Depends(require_permissions("chat:write", "scheduled_task:write")),
):
    from src.infra.assistant.service import assistant_agent
    from src.infra.scheduler.service import ScheduledTaskService
    from src.kernel.schemas.scheduled_task import ScheduledTaskCreate, TriggerType

    assistant = await _service().get(user, assistant_id)
    await _service().validate_configuration(user, assistant)
    policy = data.model_dump(exclude={"name", "instructions", "interval_seconds"})
    task = await ScheduledTaskService().create_task(
        ScheduledTaskCreate(
            name=data.name,
            agent_id=assistant_agent(assistant),
            trigger_type=TriggerType.INTERVAL,
            trigger_config={"seconds": data.interval_seconds},
            source_session_id=assistant.session_id,
            notification_policy="meaningful_changes",
            input_payload={
                "message": data.instructions,
                "assistant_rule": {"assistant_id": assistant.id, **policy},
            },
            enabled=data.mode != "off",
        ),
        owner_id=user.sub,
    )
    return {"id": task.id}


@router.get("/{assistant_id}/rules")
async def list_assistant_rules(
    assistant_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    user: TokenPayload = Depends(require_permissions("session:read", "scheduled_task:read")),
):
    from src.infra.scheduler.storage import get_scheduled_task_storage

    await _service().get(user, assistant_id)
    collection = get_scheduled_task_storage()._get_collection("scheduled_tasks")
    query = {
        "owner_id": user.sub,
        "input_payload.assistant_rule.assistant_id": assistant_id,
        "status": {"$ne": "deleted"},
    }
    rows = (
        await collection.find(
            query,
            {
                "_id": 1,
                "name": 1,
                "input_payload": 1,
                "trigger_type": 1,
                "trigger_config": 1,
                "enabled": 1,
                "status": 1,
                "assistant_rule_wakeups": 1,
                "assistant_rule_last_claim": 1,
            },
        )
        .sort([("created_at", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
        .to_list(length=limit)
    )
    return {
        "rules": [{"id": row.pop("_id"), **row} for row in rows],
        "total": await collection.count_documents(query),
    }
