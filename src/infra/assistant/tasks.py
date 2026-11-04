"""Assistant task views and explicit user admission over the existing work queue."""

import asyncio
import hashlib
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from src.infra.assistant.service import AssistantService, assistant_agent, assistant_options
from src.infra.task.background_tasks import INHERITED_FIELDS, BackgroundTaskService
from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.assistant import AssistantTaskCreate, AssistantTaskReview


def task_view(record, session):
    owned = (
        session is not None
        and session.user_id == record["user_id"]
        and (session.metadata or {}).get("background_task_id") == record["_id"]
    )
    metadata = session.metadata if owned else {}
    run_id = metadata.get("current_run_id") or record["run_id"]
    status = metadata.get("task_status")
    review = record.get("review") or {}
    reviewed = review.get("run_id") == run_id
    if record["state"] in {"failed", "uncertain"} or (not owned and record["state"] == "submitted"):
        state = "needs_attention"
    elif status == "completed":
        state = (
            ("accepted" if review.get("accepted") else "needs_revision")
            if reviewed
            else "awaiting_review"
        )
    else:
        state = status or "queued"
    started_at = record.get("authorized_run_started_at") or record["created_at"]
    timeout = record.get("timeout_seconds")
    return {
        "started_at": started_at,
        "deadline_at": started_at + timedelta(seconds=timeout) if timeout else None,
        "authorized_turns": 1 + record.get("followup_count", 0),
        "recovery_attempts": metadata.get("resume_attempts", 0)
        if metadata.get("resume_attempts_run_id") == run_id
        else 0,
        "id": record["_id"],
        "description": record["description"],
        "session_id": record["session_id"] if owned else None,
        "run_id": run_id,
        "state": state,
        "admission_state": record["state"],
        "execution_mode": record["execution_mode"],
        "created_at": record["created_at"],
        "environment": (record.get("agent_options") or {}).get("sandbox"),
        "timeout_seconds": record.get("timeout_seconds"),
        "review_revision": record.get("review_revision", 0),
        "source_run_id": record.get("parent_run_id"),
        "authorization": record.get(
            "authorization", {"kind": "conversation", "run_id": record.get("parent_run_id")}
        ),
        "error_code": metadata.get("task_error_code"),
    }


class AssistantTaskService:
    def __init__(self, *, assistants=None, background=None, completions=None):
        from src.infra.task.completion_events import TaskCompletionStore

        self.completions = completions or TaskCompletionStore()
        self.assistants = assistants or AssistantService()
        self.background = background or BackgroundTaskService()

    async def _record(self, user, assistant_id, task_id):
        assistant = await self.assistants.get(user, assistant_id)
        query = {
            "_id": task_id,
            "user_id": user.sub,
            "$or": [{"assistant_id": assistant.id}, {"parent_session_id": assistant.session_id}],
        }
        record = await self.background.store.collection.find_one(query)
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return record, query

    async def get(self, user, assistant_id, task_id):
        record, _ = await self._record(user, assistant_id, task_id)
        session = await self.background.sessions.get_session(record["session_id"])
        view = task_view(record, session)
        receipts = await self.completions.for_runs(user.sub, [view["run_id"]])
        return {**view, "notification": receipts.get(view["run_id"])}

    async def list(self, user, assistant_id, *, skip=0, limit=20):
        if skip < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid task page")
        assistant = await self.assistants.get(user, assistant_id)
        query = {
            "user_id": user.sub,
            "$or": [{"assistant_id": assistant.id}, {"parent_session_id": assistant.session_id}],
        }
        collection = self.background.store.collection
        records, total = await asyncio.gather(
            collection.find(query)
            .sort([("created_at", -1), ("_id", -1)])
            .skip(skip)
            .limit(limit)
            .to_list(length=limit),
            collection.count_documents(query),
        )
        sessions = await self.background.sessions.storage.get_by_session_ids(
            [record["session_id"] for record in records]
        )
        views = [task_view(record, sessions.get(record["session_id"])) for record in records]
        receipts = await self.completions.for_runs(user.sub, [view["run_id"] for view in views])
        return {
            "tasks": [{**view, "notification": receipts.get(view["run_id"])} for view in views],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def create(
        self,
        user,
        assistant_id,
        data: AssistantTaskCreate,
        *,
        language="en",
        authorization=None,
        quiet=False,
    ):
        from src.api.routes.chat_request_config import resolve_persona_request
        from src.infra.backend.workspace_selection import resolve_workspace_options

        assistant = await self.assistants.get(user, assistant_id)
        if assistant.status != "active":
            raise AppError(ErrorCode.CONFLICT)
        await self.assistants.validate_configuration(user, assistant)
        request = AgentRequest(
            message=data.description,
            persona_preset_id=assistant.persona_preset_id,
            team_id=assistant.team_id,
        )
        await resolve_persona_request(request, user)
        options = await resolve_workspace_options(
            assistant_options(assistant), user.sub, project_id=assistant.project_id
        )
        identity = hashlib.sha256(
            f"assistant-task\0{user.sub}\0{assistant.id}\0{data.request_id}".encode()
        ).hexdigest()
        task_input = data.model_dump(mode="json", exclude={"request_id"})
        record = await self.background.store.reserve(
            {
                "_id": identity,
                "user_id": user.sub,
                "parent_session_id": assistant.session_id,
                "parent_run_id": None,
                "call_id": str(data.request_id),
                "state": "reserved",
                "session_id": str(uuid5(NAMESPACE_URL, f"background:{identity}")),
                "run_id": str(uuid5(NAMESPACE_URL, f"background-run:{identity}")),
                "description": data.description,
                "input": task_input,
                "agent_id": assistant_agent(assistant),
                "agent_options": options,
                "config": {
                    **{
                        key: getattr(request, key)
                        for key in INHERITED_FIELDS
                        if getattr(request, key) is not None
                    },
                    "project_id": assistant.project_id,
                },
                "assistant_instructions": assistant.instructions,
                "assistant_id": assistant.id,
                "authorization": {
                    "kind": "user",
                    "request_id": str(data.request_id),
                    "assistant_revision": assistant.revision,
                    **(authorization or {}),
                },
                "quiet": quiet,
                "timeout_seconds": data.timeout_seconds,
                "language": language,
                "execution_mode": self._execution_mode(),
                "created_at": utc_now(),
            }
        )
        if record.get("input") != task_input:
            raise AppError(ErrorCode.CONFLICT)
        return await self.background.submit_reserved(record)

    @staticmethod
    def _execution_mode():
        from src.kernel.config import settings

        return settings.TASK_BACKEND

    async def review(self, user, assistant_id, task_id, data: AssistantTaskReview):
        record, query = await self._record(user, assistant_id, task_id)
        session = await self.background.sessions.get_session(record["session_id"])
        view = task_view(record, session)
        if view["run_id"] != data.run_id or view["state"] not in {
            "awaiting_review",
            "accepted",
            "needs_revision",
        }:
            raise AppError(ErrorCode.CONFLICT)
        query["$and"] = [{"$or": [{"review_revision": data.revision}]}]
        if data.revision == 0:
            query["$and"][0]["$or"].append({"review_revision": {"$exists": False}})
        review = {
            "run_id": data.run_id,
            "accepted": data.accepted,
            "reviewed_at": utc_now(),
            "user_id": user.sub,
        }
        changed = await self.background.store.collection.update_one(
            query, {"$set": {"review": review}, "$inc": {"review_revision": 1}}
        )
        if not changed.modified_count:
            raise AppError(ErrorCode.CONFLICT)
        return task_view(
            {**record, "review": review, "review_revision": data.revision + 1}, session
        )
