"""Assistant identity is durable, tenant-scoped and updated without lost writes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError


def test_assistant_configuration_rejects_blank_names_and_injected_authority():
    from src.kernel.schemas.assistant import AssistantCreate

    for data in (
        {"name": "  "},
        {"name": "Helper", "user_id": "other"},
        {"name": "Helper", "api_key": "secret"},
    ):
        with pytest.raises(ValidationError):
            AssistantCreate(**data)
    assert AssistantCreate(name=" Helper ").name == "Helper"


def test_assistant_updates_require_a_positive_integer_revision():
    from src.kernel.schemas.assistant import AssistantUpdate

    for revision in (0, -1, True, "1"):
        with pytest.raises(ValidationError):
            AssistantUpdate(name="Helper", revision=revision)


async def test_create_owns_identity_and_has_no_implicit_automation():
    from src.infra.assistant.store import AssistantStore
    from src.kernel.schemas.assistant import AssistantCreate

    collection = SimpleNamespace(insert_one=AsyncMock())
    assistant = await AssistantStore(collection).create("owner", AssistantCreate(name="Helper"))
    saved = collection.insert_one.call_args.args[0]
    assert saved["_id"] == assistant.id
    assert saved["user_id"] == "owner"
    assert assistant.status == "active"
    assert assistant.revision == 1
    assert assistant.session_id != assistant.id
    assert "api_key" not in saved


async def test_reads_always_include_the_owner():
    from src.infra.assistant.store import AssistantStore

    collection = SimpleNamespace(find_one=AsyncMock(return_value=None))
    assert await AssistantStore(collection).get("other", "assistant") is None
    collection.find_one.assert_awaited_once_with({"_id": "assistant", "user_id": "other"})


async def test_update_is_fenced_by_owner_and_revision_and_keeps_session_identity():
    from src.infra.assistant.store import AssistantStore
    from src.kernel.schemas.assistant import AssistantUpdate

    collection = SimpleNamespace(find_one_and_update=AsyncMock(return_value=None))
    result = await AssistantStore(collection).update(
        "owner", "assistant", AssistantUpdate(name="Renamed", revision=3)
    )
    assert result is None
    query, change = collection.find_one_and_update.call_args.args
    assert query == {"_id": "assistant", "user_id": "owner", "revision": 3}
    assert change["$inc"] == {"revision": 1}
    assert change["$set"]["name"] == "Renamed"
    assert not {"session_id", "user_id", "_id", "revision"} & change["$set"].keys()


async def test_list_is_paginated_and_owner_scoped():
    from src.infra.assistant.store import AssistantStore

    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    collection = SimpleNamespace(find=MagicMock(return_value=cursor))
    assert await AssistantStore(collection).list("owner", skip=10, limit=20) == []
    collection.find.assert_called_once_with({"user_id": "owner", "status": {"$ne": "archived"}})
    cursor.skip.assert_called_once_with(10)
    cursor.limit.assert_called_once_with(20)
    with pytest.raises(ValueError):
        await AssistantStore(collection).list("owner", limit=10000)


async def test_legacy_update_does_not_erase_agent_presentation():
    from src.infra.assistant.store import AssistantStore
    from src.kernel.schemas.assistant import AssistantUpdate

    collection = SimpleNamespace(find_one_and_update=AsyncMock(return_value=None))
    store = AssistantStore(collection)
    await store.update("owner", "assistant", AssistantUpdate(name="New", revision=3))
    saved = collection.find_one_and_update.call_args.args[1]["$set"]
    assert "avatar" not in saved and "starter_prompts" not in saved
    await store.update(
        "owner",
        "assistant",
        AssistantUpdate(name="New", revision=3, avatar=None, starter_prompts=[]),
    )
    saved = collection.find_one_and_update.call_args.args[1]["$set"]
    assert saved["avatar"] is None and saved["starter_prompts"] == []


def test_assistant_starters_reuse_localized_text_validation():
    from src.kernel.schemas.assistant import AssistantCreate

    with pytest.raises(ValidationError):
        AssistantCreate(name="Helper", starter_prompts=[{"text": {"zh": " "}}])
