"""Assistant domain service layer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .storage import AssistantStorage
from .types import AssistantCreate, AssistantRecord, AssistantScope, AssistantUpdate


class AssistantManager:
    """Assistant orchestration logic."""

    def __init__(self, storage: AssistantStorage | None = None) -> None:
        self.storage = storage or AssistantStorage()

    async def list_assistants(
        self,
        user_id: str,
        scope: str = "public",
        search: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
    ) -> list[AssistantRecord]:
        public_items = await self.storage.list_public_assistants()
        private_items = await self.storage.list_user_assistants(user_id)

        if scope == "mine":
            items = private_items
        elif scope == "all":
            items = public_items + private_items
        else:
            items = public_items

        if category:
            items = [item for item in items if item.category == category]
        if search:
            needle = search.lower()
            items = [
                item
                for item in items
                if needle in item.name.lower() or needle in item.description.lower()
            ]
        if tags:
            required = set(tags)
            items = [item for item in items if required.issubset(set(item.tags))]
        return items

    async def get_assistant_for_user(
        self, assistant_id: str, user_id: str, is_admin: bool = False
    ) -> AssistantRecord | None:
        assistant = await self.storage.get_assistant_by_assistant_id(assistant_id)
        if assistant is None:
            return None
        if assistant.scope == AssistantScope.PUBLIC:
            if assistant.is_active or is_admin:
                return assistant
            return None
        if assistant.created_by == user_id or is_admin:
            return assistant
        return None

    async def create_private_assistant(
        self, data: AssistantCreate, user_id: str
    ) -> AssistantRecord:
        payload = data.model_copy(update={"scope": AssistantScope.PRIVATE})
        return await self.storage.create_assistant(payload, user_id)

    async def update_assistant_for_user(
        self,
        assistant_id: str,
        user_id: str,
        data: AssistantUpdate,
        is_admin: bool = False,
    ) -> AssistantRecord | None:
        assistant = await self.get_assistant_for_user(assistant_id, user_id, is_admin=is_admin)
        if assistant is None:
            return None
        if (
            assistant.scope == AssistantScope.PRIVATE
            and assistant.created_by != user_id
            and not is_admin
        ):
            return None
        if assistant.scope == AssistantScope.PUBLIC and not is_admin:
            return None
        return await self.storage.update_assistant(assistant_id, data)

    async def delete_assistant_for_user(
        self, assistant_id: str, user_id: str, is_admin: bool = False
    ) -> bool:
        assistant = await self.get_assistant_for_user(assistant_id, user_id, is_admin=is_admin)
        if assistant is None:
            return False
        if (
            assistant.scope == AssistantScope.PRIVATE
            and assistant.created_by != user_id
            and not is_admin
        ):
            return False
        if assistant.scope == AssistantScope.PUBLIC and not is_admin:
            return False
        return await self.storage.delete_assistant(assistant_id)

    async def resolve_session_prompt_snapshot(
        self,
        session_metadata: Mapping[str, Any],
        assistant_id: str | None,
    ) -> tuple[str | None, dict[str, Any]]:
        snapshot = session_metadata.get("assistant_prompt_snapshot")
        if isinstance(snapshot, str) and snapshot:
            return snapshot, {}

        if not assistant_id:
            return None, {}

        assistant = await self.storage.get_assistant_by_assistant_id(assistant_id)
        if assistant is None:
            return None, {}

        return assistant.system_prompt, {
            "assistant_id": assistant.assistant_id,
            "assistant_name": assistant.name,
            "assistant_prompt_snapshot": assistant.system_prompt,
        }

    async def clone_public_assistant(self, assistant_id: str, user_id: str):
        assistant = await self.storage.get_assistant_by_assistant_id(assistant_id)
        if assistant is None or assistant.scope != AssistantScope.PUBLIC or not assistant.is_active:
            raise ValueError(f"Assistant '{assistant_id}' not found")
        return await self.storage.clone_assistant(assistant_id, user_id)

    async def select_assistant_for_session(
        self, assistant_id: str, session_id: str, user_id: str
    ) -> dict[str, Any]:
        del session_id
        prompt, update = await self.resolve_session_prompt_snapshot({}, assistant_id=assistant_id)
        if prompt is None:
            raise ValueError(f"Assistant '{assistant_id}' not found")
        assistant = await self.get_assistant_for_user(assistant_id, user_id)
        if assistant is None:
            raise ValueError(f"Assistant '{assistant_id}' not found")
        return update
