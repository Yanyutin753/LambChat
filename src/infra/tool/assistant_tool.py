"""Chief management uses the same owner-scoped services as the assistant UI."""

from hashlib import sha256
from typing import Literal
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from langchain.tools import ToolRuntime, tool

from src.infra.assistant.service import AssistantService
from src.infra.assistant.store import AssistantStore
from src.infra.auth.tool_authority import resolve_tool_user
from src.infra.tool.backend_utils import get_session_id_from_runtime, get_user_id_from_runtime
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.assistant import AssistantCreate, AssistantTaskCreate, AssistantUpdate


async def chief_context(runtime, permission):
    user = await resolve_tool_user(get_user_id_from_runtime(runtime))
    config = runtime.config if runtime else {}
    metadata = config.get("metadata") or {}
    thread = str((config.get("configurable") or {}).get("thread_id", ""))
    if (
        not user
        or permission not in user.permissions
        or metadata.get("lambchat_subagent_id")
        or thread.startswith("subagent:")
        or "|" in str((config.get("configurable") or {}).get("checkpoint_ns", ""))
    ):
        raise AppError(ErrorCode.FORBIDDEN)
    session_id = get_session_id_from_runtime(runtime)
    if not session_id or (thread and thread != session_id):
        raise AppError(ErrorCode.FORBIDDEN)
    chief = await AssistantStore().for_session(user.sub, session_id)
    if chief is None or chief.kind != "chief" or chief.status != "active":
        raise AppError(ErrorCode.FORBIDDEN)
    return user


def public_assistant(value):
    return {
        **value.model_dump(
            mode="json",
            include={
                "id",
                "name",
                "kind",
                "instructions",
                "member_ids",
                "leader_id",
                "revision",
                "status",
            },
        ),
        "url": f"/assistants/{value.id}",
    }


@tool
async def list_assistants(skip: int = 0, runtime: ToolRuntime = None) -> dict:  # type: ignore[assignment]
    """Chief only: list your user's assistants and groups before creating or editing them.
    Returns IDs, roles and revisions, never their private conversation history. Page size 50.
    """
    user = await chief_context(runtime, "session:read")
    if skip < 0:
        raise AppError(ErrorCode.VALIDATION_ERROR)
    store = AssistantStore()
    return {
        "assistants": [
            public_assistant(item) for item in await store.list(user.sub, skip=skip, limit=50)
        ],
        "total": await store.count(user.sub),
        "skip": skip,
    }


@tool
async def create_assistant(
    name: str,
    instructions: str,
    kind: Literal["assistant", "group"] = "assistant",
    member_ids: list[str] | None = None,
    leader_id: str | None = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> dict:
    """Chief only: create a requested personal assistant or group chat.
    Search list_assistants first to reuse existing identities. Groups require 2-12 actual
    assistant IDs and leader_id from that list. New assistants use the account default model;
    configure execution environments in the UI. Does not grant new tools or share private history.
    """
    user = await chief_context(runtime, "chat:write")
    config = runtime.config.get("configurable") or {}
    if not runtime.tool_call_id:
        raise AppError(ErrorCode.VALIDATION_ERROR)
    identity = sha256(
        f"assistant-tool:{user.sub}:{config.get('thread_id')}:{config.get('run_id')}:{runtime.tool_call_id}".encode()
    ).hexdigest()
    value = await AssistantService().create(
        user,
        AssistantCreate(
            name=name,
            instructions=instructions,
            kind=kind,
            member_ids=member_ids or [],
            leader_id=leader_id,
        ),
        identity=identity,
    )
    return {"success": True, **public_assistant(value)}


@tool
async def update_assistant(
    assistant_id: str,
    revision: int,
    name: str | None = None,
    instructions: str | None = None,
    status: Literal["active", "paused", "archived"] | None = None,
    member_ids: list[str] | None = None,
    leader_id: str | None = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> dict:
    """Chief only: update a requested assistant/group using its current listed revision.
    Supports rename, duties, pause/resume/archive, and group membership/coordinator.
    When changing leader_id, also supply the full reviewed instructions in the SAME call:
    update references to the current coordinator, preserving unrelated duties and historical facts.
    If instructions are coordinator-neutral, supply them unchanged (including an empty string).
    Omitted fields stay unchanged. Never changes models, workspaces, credentials or permissions.
    Archive preserves history. Do not retry a conflict blindly: reload and assess the change.
    """
    user = await chief_context(runtime, "chat:write")
    service = AssistantService()
    current = await service.get(user, assistant_id)
    if (
        current.kind == "group"
        and leader_id is not None
        and leader_id != current.leader_id
        and instructions is None
    ):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            message="Changing a group coordinator requires full reviewed instructions in the same call. "
            "Update current-coordinator references; preserve unrelated duties and historical facts. "
            "If the purpose is coordinator-neutral, explicitly supply it unchanged.",
        )
    values = current.model_dump(include=set(AssistantCreate.model_fields), by_alias=True)
    for key, value in {
        "name": name,
        "instructions": instructions,
        "member_ids": member_ids,
        "leader_id": leader_id,
    }.items():
        if value is not None:
            values[key] = value
    saved = await service.update(
        user,
        assistant_id,
        AssistantUpdate(**values, revision=revision, status=status or current.status),
    )
    return {"success": True, **public_assistant(saved)}


@tool
async def delegate_assistant_task(
    assistant_id: str,
    description: str,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> dict:
    """Chief only: hand explicitly requested work to an existing assistant or group.
    List assistants first and use its actual ID. Include the user's task, constraints and
    required deliverable, not private chat history. Uses the target's saved configuration
    in an independent conversation; returns immediately, not a completed result. Do not
    send the same work twice. The user can follow the returned link and receives completion
    notification. Paused/archived assistants and Chief itself cannot receive delegated work.
    """
    from src.infra.assistant.tasks import AssistantTaskService

    user = await chief_context(runtime, "chat:write")
    target = await AssistantService().get(user, assistant_id)
    if target.kind == "chief" or target.status != "active":
        raise AppError(ErrorCode.CONFLICT)
    config = runtime.config.get("configurable") or {}
    source = get_session_id_from_runtime(runtime)
    run_id = config.get("run_id") or getattr(config.get("presenter"), "run_id", None)
    if not source or not run_id or not runtime.tool_call_id:
        raise AppError(ErrorCode.VALIDATION_ERROR)
    result = await AssistantTaskService().create(
        user,
        target.id,
        AssistantTaskCreate(
            request_id=uuid5(
                NAMESPACE_URL,
                f"assistant-delegation:{user.sub}:{source}:{run_id}:{runtime.tool_call_id}",
            ),
            description=description,
        ),
        language=(runtime.config.get("metadata") or {}).get("language") or "en",
        source_session_id=source,
        source_run_id=run_id,
    )
    result = {**result, "assistant_id": target.id, "assistant_name": target.name}
    if result.get("status") in {"queued", "running"} and result.get("session_id"):
        result["url"] = (
            f"/assistants/{quote(target.id, safe='')}/chat/{quote(result['session_id'], safe='')}"
        )
    return result


def get_assistant_tools():
    return [list_assistants, create_assistant, update_assistant, delegate_assistant_task]
