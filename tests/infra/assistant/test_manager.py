from __future__ import annotations

import pytest


class _FakeAssistantStorage:
    def __init__(self, docs: dict[str, dict]) -> None:
        self.docs = docs

    async def get_assistant_by_assistant_id(self, assistant_id: str):
        from src.infra.assistant.types import AssistantRecord

        doc = self.docs.get(assistant_id)
        if doc is None:
            return None
        return AssistantRecord.model_validate(doc)


@pytest.mark.asyncio
async def test_manager_prefers_session_prompt_snapshot() -> None:
    from src.infra.assistant.manager import AssistantManager

    manager = AssistantManager()
    manager.storage = _FakeAssistantStorage(
        {
            "public-1": {
                "assistant_id": "public-1",
                "name": "Public One",
                "description": "",
                "system_prompt": "latest live prompt",
                "scope": "public",
                "created_by": "admin-1",
                "is_active": True,
            }
        }
    )

    prompt, update = await manager.resolve_session_prompt_snapshot(
        {
            "assistant_id": "public-1",
            "assistant_name": "Public One",
            "assistant_prompt_snapshot": "snapshot prompt",
        },
        assistant_id="public-1",
    )

    assert prompt == "snapshot prompt"
    assert update == {}


@pytest.mark.asyncio
async def test_manager_snapshots_live_prompt_when_only_assistant_id_exists() -> None:
    from src.infra.assistant.manager import AssistantManager

    manager = AssistantManager()
    manager.storage = _FakeAssistantStorage(
        {
            "public-1": {
                "assistant_id": "public-1",
                "name": "Public One",
                "description": "desc",
                "system_prompt": "live prompt",
                "scope": "public",
                "created_by": "admin-1",
                "is_active": True,
            }
        }
    )

    prompt, update = await manager.resolve_session_prompt_snapshot({}, assistant_id="public-1")

    assert prompt == "live prompt"
    assert update == {
        "assistant_id": "public-1",
        "assistant_name": "Public One",
        "assistant_prompt_snapshot": "live prompt",
    }
