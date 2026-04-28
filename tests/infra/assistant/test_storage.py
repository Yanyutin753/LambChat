from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, field: str, direction: int):
        reverse = direction == -1
        self._docs = sorted(self._docs, key=lambda doc: doc.get(field), reverse=reverse)
        return self

    def skip(self, _count: int):
        return self

    def limit(self, count: int):
        self._docs = self._docs[:count]
        return self

    async def to_list(self, length: int | None = None) -> list[dict]:
        if length is None:
            return [deepcopy(doc) for doc in self._docs]
        return [deepcopy(doc) for doc in self._docs[:length]]


class _FakeCollection:
    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self.indexes: list[tuple] = []

    async def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))

    async def insert_one(self, doc: dict):
        stored = deepcopy(doc)
        stored.setdefault("_id", f"id-{len(self.docs) + 1}")
        self.docs.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    async def find_one(self, query: dict):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return deepcopy(doc)
        return None

    def find(self, query: dict):
        matches = []
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                matches.append(doc)
        return _FakeCursor(matches)


@pytest.mark.asyncio
async def test_assistant_create_defaults_private_scope_and_version() -> None:
    from src.infra.assistant.types import AssistantCreate, AssistantScope

    assistant = AssistantCreate(name="Writing Coach", system_prompt="Be concise.")

    assert assistant.scope == AssistantScope.PRIVATE
    assert assistant.version == "1.0.0"
    assert assistant.tags == []


@pytest.mark.asyncio
async def test_storage_separates_public_and_private_assistants() -> None:
    from src.infra.assistant.storage import AssistantStorage

    storage = AssistantStorage()
    storage._collection = _FakeCollection(
        [
            {
                "_id": "id-1",
                "assistant_id": "public-1",
                "name": "Public One",
                "description": "",
                "system_prompt": "public",
                "scope": "public",
                "created_by": "admin-1",
                "is_active": True,
                "tags": ["general"],
                "updated_at": "2026-04-28T10:00:00Z",
                "created_at": "2026-04-28T10:00:00Z",
            },
            {
                "_id": "id-2",
                "assistant_id": "private-1",
                "name": "Private One",
                "description": "",
                "system_prompt": "private",
                "scope": "private",
                "created_by": "user-1",
                "is_active": True,
                "tags": ["focus"],
                "updated_at": "2026-04-28T11:00:00Z",
                "created_at": "2026-04-28T11:00:00Z",
            },
            {
                "_id": "id-3",
                "assistant_id": "private-2",
                "name": "Other Private",
                "description": "",
                "system_prompt": "other",
                "scope": "private",
                "created_by": "user-2",
                "is_active": True,
                "tags": [],
                "updated_at": "2026-04-28T12:00:00Z",
                "created_at": "2026-04-28T12:00:00Z",
            },
        ]
    )

    public_assistants = await storage.list_public_assistants()
    private_assistants = await storage.list_user_assistants("user-1")

    assert [assistant.assistant_id for assistant in public_assistants] == ["public-1"]
    assert [assistant.assistant_id for assistant in private_assistants] == ["private-1"]


@pytest.mark.asyncio
async def test_storage_clone_copies_prompt_fields_and_tracks_source() -> None:
    from src.infra.assistant.storage import AssistantStorage

    storage = AssistantStorage()
    storage._collection = _FakeCollection(
        [
            {
                "_id": "id-1",
                "assistant_id": "public-1",
                "name": "Public One",
                "description": "original",
                "system_prompt": "Be structured.",
                "scope": "public",
                "created_by": "admin-1",
                "is_active": True,
                "tags": ["general", "ops"],
                "updated_at": "2026-04-28T10:00:00Z",
                "created_at": "2026-04-28T10:00:00Z",
            }
        ]
    )

    cloned = await storage.clone_assistant("public-1", user_id="user-1")

    assert cloned.name == "Public One"
    assert cloned.description == "original"
    assert cloned.system_prompt == "Be structured."
    assert cloned.scope == "private"
    assert cloned.created_by == "user-1"
    assert cloned.tags == ["general", "ops"]
    assert cloned.cloned_from_assistant_id == "public-1"
