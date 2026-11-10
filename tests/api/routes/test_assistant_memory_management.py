"""Management endpoints bind writes and restores to the selected assistant bank."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import memory as routes
from src.infra.assistant.store import AssistantStore
from src.kernel.errors import AppError
from src.kernel.schemas.user import TokenPayload
from tests.api.routes.test_memory_import_export import _FakeBackend


def user():
    return TokenPayload(sub="user-1", username="tester", roles=["user"])


@pytest.fixture
def bank(monkeypatch):
    backend = _FakeBackend([])
    backend._collection.insert_one = AsyncMock(
        side_effect=lambda doc: backend._collection.docs.append(dict(doc))
    )
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    monkeypatch.setattr(routes, "_write_vector_index", AsyncMock())
    lookup = AsyncMock(
        return_value=SimpleNamespace(id="helper", user_id="user-1", memory_mode="private")
    )
    monkeypatch.setattr(AssistantStore, "get", lookup)
    return backend, lookup


async def test_manual_assistant_memory_is_partitioned_and_exported(bank):
    backend, lookup = bank
    result = await routes.create_memory(
        {"content": "Remember the weekly research brief."}, user=user(), assistant_id="helper"
    )
    doc = backend._collection.docs[0]
    assert doc["scope"] == "project"
    assert doc["project_id"] == "assistant-memory:helper"
    response = await routes.export_memories(user=user(), assistant_id="helper")
    exported = json.loads("".join([part async for part in response.body_iterator]))
    assert [item["memory_id"] for item in exported["memories"]] == [result["memory_id"]]
    lookup.assert_awaited_with("user-1", "helper")


async def test_scoped_restore_keeps_destination_private_and_rejects_other_banks(bank):
    backend, _ = bank
    await routes.import_memories(
        {"memories": [{"memory_id": "one", "content": "Private assistant fact", "scope": "user"}]},
        user=user(),
        assistant_id="helper",
    )
    assert backend._collection.docs[0]["project_id"] == "assistant-memory:helper"
    backend._collection.docs[0]["project_id"] = "assistant-memory:other"
    with pytest.raises(AppError):
        await routes.import_memories(
            {"memories": [{"memory_id": "one", "content": "Do not overwrite another bank"}]},
            user=user(),
            assistant_id="helper",
            validate_only=True,
        )
    assert backend._collection.docs[0]["content"] == "Private assistant fact"


async def test_global_backup_can_restore_an_owned_assistant_partition(bank):
    backend, _ = bank
    await routes.import_memories(
        {
            "memories": [
                {
                    "content": "Private assistant fact",
                    "scope": "project",
                    "project_id": "assistant-memory:helper",
                }
            ]
        },
        user=user(),
    )
    assert backend._collection.docs[0]["project_id"] == "assistant-memory:helper"


async def test_foreign_assistant_bank_is_rejected_before_content_write(bank):
    backend, lookup = bank
    lookup.return_value = None
    with pytest.raises(AppError):
        await routes.create_memory(
            {"content": "Never write foreign state"}, user=user(), assistant_id="foreign"
        )
    assert backend._collection.docs == []


async def test_discussion_management_cannot_select_private_assistant_memory(bank, monkeypatch):
    from src.infra.assistant.discussions import DiscussionStore

    backend, _ = bank
    discussion = {"assistant_id": "helper", "user_id": "user-1", "session_id": "discussion"}
    monkeypatch.setattr(DiscussionStore, "get", AsyncMock(return_value=discussion))
    validate = AsyncMock(return_value=SimpleNamespace(id="helper"))
    monkeypatch.setattr("src.infra.assistant.discussions.validate_discussion", validate)
    await routes.create_memory(
        {"content": "Fact shared only in this discussion"},
        user=user(),
        assistant_id="helper",
        discussion_id="discussion",
    )
    assert backend._collection.docs[0]["project_id"] == "assistant-discussion-memory:discussion"
    discussion["assistant_id"] = "another-assistant"
    with pytest.raises(AppError):
        await routes.create_memory(
            {"content": "Wrong binding"},
            user=user(),
            assistant_id="helper",
            discussion_id="discussion",
        )
    assert len(backend._collection.docs) == 1
