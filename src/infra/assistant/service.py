"""Assistant configuration resolves through the existing permission owners."""

from src.infra.assistant.store import AssistantStore
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.assistant import Assistant, AssistantCreate, AssistantUpdate
from src.kernel.schemas.user import TokenPayload


def assistant_options(assistant: AssistantCreate) -> dict:
    values: dict = {"model_id": assistant.model_id} if assistant.model_id else {}
    if assistant.sandbox or not assistant.project_id:
        values["sandbox"] = assistant.sandbox
    if assistant.workspace:
        values["sandbox_machine_id"] = assistant.workspace.machine_id
        values["sandbox_workspace"] = assistant.workspace.model_dump_json(by_alias=True)
    return values


def assistant_agent(assistant: AssistantCreate) -> str:
    return "team" if assistant.team_id or assistant.kind == "group" else "search"


async def assistant_scope_session(user_id: str, session_id: str) -> str:
    if not session_id.startswith("sch_conversation_"):
        return session_id
    from src.infra.scheduler.storage import get_scheduled_task_storage
    from src.infra.session.manager import SessionManager

    session = await SessionManager().get_session(session_id)
    metadata = (session.metadata or {}) if session else {}
    task = await get_scheduled_task_storage().get_task(session_id.removeprefix("sch_conversation_"))
    if (
        not session
        or session.user_id != user_id
        or not task
        or task.owner_id != user_id
        or task.execution_mode != "conversation"
        or metadata.get("scheduled_task_id") != task.id
        or metadata.get("scheduled_target_session_id") != task.target_session_id
    ):
        raise AppError(ErrorCode.FORBIDDEN)
    if not task.target_session_id or task.target_session_id.startswith("sch_conversation_"):
        raise AppError(ErrorCode.FORBIDDEN)
    return task.target_session_id


async def conversation_assistant(user_id: str, session_id: str, *, store=None):
    from src.infra.assistant.discussions import (
        DiscussionStore,
        is_discussion_session,
        validate_discussion,
    )

    session_id = await assistant_scope_session(user_id, session_id)
    if is_discussion_session(session_id):
        discussion = await DiscussionStore().get(user_id, session_id)
        return await validate_discussion(discussion, user_id, require_active=False)
    return await (store or AssistantStore()).for_session(user_id, session_id)


class AssistantService:
    def __init__(self, store: AssistantStore | None = None, sessions=None):
        self.store = store or AssistantStore()
        self.sessions = sessions

    async def get(self, user: TokenPayload, assistant_id: str) -> Assistant:
        assistant = await self.store.get(user.sub, assistant_id)
        if assistant is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return assistant

    async def validate_configuration(self, user: TokenPayload, data: AssistantCreate) -> None:
        if data.kind == "group":
            from src.infra.assistant.groups import group_members

            for member in await group_members(user, data, store=self.store):
                await self.validate_configuration(user, member)
        if data.team_id:
            from src.infra.team.storage import TeamStorage

            if await TeamStorage().get_team(data.team_id, owner_user_id=user.sub) is None:
                raise AppError(ErrorCode.TEAM_NOT_FOUND)
        if data.project_id:
            from src.infra.folder.storage import get_project_storage

            if await get_project_storage().get_by_id(data.project_id, user.sub) is None:
                raise AppError(ErrorCode.PROJECT_NOT_FOUND)
        if data.persona_preset_id:
            from src.infra.persona_preset.manager import get_persona_preset_manager
            from src.kernel.exceptions import NotFoundError

            try:
                await get_persona_preset_manager().get_preset(
                    data.persona_preset_id,
                    user_id=user.sub,
                    is_admin="persona_preset:admin" in user.permissions,
                )
            except NotFoundError:
                raise AppError(ErrorCode.PERSONA_PRESET_NOT_FOUND) from None
        from src.api.routes.chat import validate_agent_model_access

        await validate_agent_model_access(
            {"model_id": data.model_id} if data.model_id else {}, user
        )

    async def create(
        self, user: TokenPayload, data: AssistantCreate, *, identity=None
    ) -> Assistant:
        if data.kind == "chief":
            raise AppError(ErrorCode.FORBIDDEN)
        await self.validate_configuration(user, data)
        if identity:
            return await self.store.create(user.sub, data, identity=identity)
        return await self.store.create(user.sub, data)

    async def chief(self, user: TokenPayload) -> Assistant:
        from hashlib import sha256

        identity = "chief-" + sha256(user.sub.encode()).hexdigest()[:32]
        return await self.store.create(
            user.sub, AssistantCreate(name="Chief", kind="chief"), identity=identity
        )

    async def open_conversation(self, user: TokenPayload, assistant_id: str):
        from dataclasses import asdict

        from bson import ObjectId
        from pymongo import ReturnDocument
        from pymongo.errors import DuplicateKeyError

        from src.infra.session.search_index import compose_session_search_index
        from src.infra.session.storage import SessionStorage
        from src.infra.utils.datetime import utc_now

        assistant = await self.get(user, assistant_id)
        if assistant.status != "active":
            raise AppError(ErrorCode.CONFLICT)
        await self.validate_configuration(user, assistant)
        sessions = self.sessions or SessionStorage()
        await sessions.ensure_indexes_if_needed()
        now = utc_now()
        query = {
            "_id": ObjectId(assistant.session_id),
            "user_id": user.sub,
            "metadata.assistant_id": assistant.id,
        }
        metadata: dict = {
            "assistant_id": assistant.id,
            "agent_id": assistant_agent(assistant),
            "team_id": assistant.team_id,
        }
        if assistant.project_id:
            metadata["project_id"] = assistant.project_id
        from src.infra.backend.workspace_selection import resolve_workspace_options

        metadata["agent_options"] = await resolve_workspace_options(
            assistant_options(assistant),
            user.sub,
            project_id=assistant.project_id,
        )
        document = {
            "name": assistant.name,
            "user_id": user.sub,
            "metadata": metadata,
            "agent_id": assistant_agent(assistant),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            **asdict(
                compose_session_search_index(
                    session_name=assistant.name,
                    message_search_terms=[],
                    search_text="",
                    latest_user_message="",
                )
            ),
        }
        try:
            saved = await sessions.collection.find_one_and_update(
                query,
                {"$setOnInsert": document},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            saved = await sessions.collection.find_one(query)
        if saved is None:
            raise AppError(ErrorCode.CONFLICT)
        return SessionStorage._build_session(saved)

    async def update(
        self, user: TokenPayload, assistant_id: str, data: AssistantUpdate
    ) -> Assistant:
        current = await self.get(user, assistant_id)
        if data.kind != current.kind or (current.kind == "chief" and data.status == "archived"):
            raise AppError(ErrorCode.CONFLICT)
        # Pausing must remain possible after a model or project becomes unavailable.
        if data.status == "active":
            await self.validate_configuration(user, data)
        updated = await self.store.update(user.sub, assistant_id, data)
        if updated is None:
            raise AppError(ErrorCode.CONFLICT)
        return updated


async def prepare_assistant_request(
    request: AgentRequest,
    user: TokenPayload,
    metadata: dict | None,
    *,
    service: AssistantService | None = None,
) -> Assistant | None:
    if not request.session_id:
        return None
    owner = service or AssistantService()
    from src.infra.assistant.discussions import is_discussion_session, restrict_discussion_request

    assistant = await conversation_assistant(user.sub, request.session_id, store=owner.store)
    if assistant is None:
        if (metadata or {}).get("assistant_id") or (metadata or {}).get("assistant_discussion_id"):
            raise AppError(ErrorCode.FORBIDDEN)
        return None
    scope_session_id = await assistant_scope_session(user.sub, request.session_id)
    if not is_discussion_session(scope_session_id) and assistant.session_id != scope_session_id:
        raise AppError(ErrorCode.FORBIDDEN)
    if assistant.status != "active":
        raise AppError(ErrorCode.CONFLICT)
    await owner.validate_configuration(user, assistant)
    if is_discussion_session(scope_session_id):
        restrict_discussion_request(request)
    if assistant.kind == "group":
        restrict_discussion_request(request)
    request.persona_preset_id = assistant.persona_preset_id
    request.team_id = assistant.team_id
    request.project_id = assistant.project_id
    # Only server-owned model selection reaches the normal model-access validator.
    from src.infra.backend.workspace_selection import (
        WORKSPACE_OPTION_KEYS,
        resolve_workspace_options,
    )

    request.agent_options = await resolve_workspace_options(
        assistant_options(assistant),
        user.sub,
        project_id=assistant.project_id,
    )
    previous = (metadata or {}).get("agent_options") or {}
    if any(key in previous for key in WORKSPACE_OPTION_KEYS) and not any(
        key in request.agent_options for key in WORKSPACE_OPTION_KEYS
    ):
        # Explicit clearing prevents the ordinary chat resolver restoring an old binding.
        request.agent_options.update(dict.fromkeys(WORKSPACE_OPTION_KEYS))
    return assistant
