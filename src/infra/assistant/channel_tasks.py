"""Explicit channel task references reuse normal chat admission and its permission gates."""

import asyncio
import hashlib
import re

from starlette.requests import Request

from src.infra.assistant.discussions import DiscussionStore, validate_discussion
from src.infra.channel.inbox_worker import current_delivery
from src.infra.session.manager import SessionManager
from src.infra.task.background_task_store import BackgroundTaskStore
from src.infra.task.background_tasks import _load_user, _submit
from src.kernel.schemas.agent import AgentRequest


async def route_task_message(user_id, discussion_id, message, attachments=None):
    if not re.match(r"^/task(?:\s|$)", message.strip()):
        return None
    match = re.fullmatch(r"/task\s+([a-f0-9]{64})\s+(.+)", message.strip(), re.DOTALL)
    if not match or attachments:
        return "Use /task <task-id> <follow-up message>. Open the task in LambChat to attach files or change its scope."
    user = await _load_user(user_id)
    discussion = await DiscussionStore().get(user_id, discussion_id)
    assistant = await validate_discussion(discussion, user_id, require_active=False)
    task_id, text = match.groups()
    record = await BackgroundTaskStore().collection.find_one(
        {
            "_id": task_id,
            "user_id": user_id,
            "assistant_id": assistant.id,
            "$or": [
                {"assistant_source_session_id": discussion_id},
                {"parent_session_id": discussion_id},
            ],
        }
    )
    if not record:
        return (
            "This task is not available in this discussion. Open the authorized task in LambChat."
        )
    context = current_delivery.get()
    if context is None:
        return "Open the task in LambChat to continue; durable message admission is unavailable."
    identity = hashlib.sha256(f"{task_id}\0{text}".encode()).hexdigest()
    previous = context.checkpoint.get("assistant_task_route")
    uncertain = (
        "Check the task in LambChat before retrying: this message's execution outcome is uncertain."
    )
    if previous:
        if previous.get("identity") != identity:
            return uncertain
        return previous.get("reply") or uncertain
    session = await SessionManager().get_session(record["session_id"])
    metadata = session.metadata or {} if session else {}
    if (
        not session
        or session.user_id != user_id
        or metadata.get("background_task_id") != task_id
        or record["state"] != "submitted"
    ):
        return "Check the task in LambChat before continuing; its admission is not confirmed."
    if metadata.get("task_status") not in {"completed", "failed", "cancelled", "expired"}:
        return "The task is running or waiting for approval. Open it in LambChat to inspect, supplement or stop it."
    # Persist intent before submission; an unknown outcome cannot replay a new turn.
    claim = {
        "identity": identity,
        "task_id": task_id,
        "session_id": record["session_id"],
        "state": "admitting",
    }
    await context.save(assistant_task_route=claim)
    http = Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/api/chat/stream",
            "headers": [],
        }
    )
    try:
        async with asyncio.timeout(90):
            result = await _submit(
                AgentRequest(message=text, session_id=record["session_id"]),
                http,
                agent_id=record["agent_id"],
                user=user,
            )
        reply = f"Task update admitted with its original scope and environment. Open /chat/{record['session_id']} to follow progress."
        await context.save(
            assistant_task_route={
                **claim,
                "state": "submitted",
                "run_id": result.get("run_id"),
                "reply": reply,
            }
        )
        return reply
    except Exception:
        await context.save(assistant_task_route={**claim, "state": "uncertain", "reply": uncertain})
        return uncertain
