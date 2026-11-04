"""Chief management uses the same owner-scoped services as the assistant UI."""

from hashlib import sha256
from typing import Literal

from langchain.tools import ToolRuntime, tool

from src.infra.assistant.service import AssistantService
from src.infra.assistant.store import AssistantStore
from src.infra.auth.tool_authority import resolve_tool_user
from src.infra.tool.backend_utils import get_session_id_from_runtime, get_user_id_from_runtime
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.assistant import AssistantCreate, AssistantUpdate


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
    Omitted fields stay unchanged. Never changes models, workspaces, credentials or permissions.
    Archive preserves history. Do not retry a conflict blindly: reload and assess the change.
    """
    user = await chief_context(runtime, "chat:write")
    service = AssistantService()
    current = await service.get(user, assistant_id)
    values = current.model_dump(include=set(AssistantCreate.model_fields))
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


def get_assistant_tools():
    return [list_assistants, create_assistant, update_assistant]
