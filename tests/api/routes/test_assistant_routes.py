from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


class _FakeAssistantManager:
    def __init__(self) -> None:
        self.selected: list[tuple[str, str, str]] = []
        self.cloned: list[tuple[str, str]] = []

    async def list_assistants(
        self,
        user_id: str,
        scope: str,
        search: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
    ):
        from src.infra.assistant.types import AssistantRecord

        del user_id, search, tags, category
        items = [
            AssistantRecord(
                assistant_id="public-1",
                name="Public One",
                description="",
                system_prompt="prompt",
                scope="public",
                created_by="admin-1",
                is_active=True,
                tags=["general"],
            )
        ]
        if scope == "mine":
            return []
        return items

    async def select_assistant_for_session(
        self, assistant_id: str, session_id: str, user_id: str
    ) -> dict:
        self.selected.append((assistant_id, session_id, user_id))
        return {
            "assistant_id": assistant_id,
            "assistant_name": "Public One",
            "assistant_prompt_snapshot": "prompt",
        }

    async def clone_public_assistant(self, assistant_id: str, user_id: str):
        from src.infra.assistant.types import AssistantRecord

        self.cloned.append((assistant_id, user_id))
        return AssistantRecord(
            assistant_id="private-1",
            name="Public One",
            description="",
            system_prompt="prompt",
            scope="private",
            created_by=user_id,
            is_active=True,
            tags=["general"],
            cloned_from_assistant_id=assistant_id,
        )

    async def get_assistant_for_user(self, assistant_id: str, user_id: str, is_admin: bool = False):
        from src.infra.assistant.types import AssistantRecord

        if assistant_id == "owned-private":
            return AssistantRecord(
                assistant_id=assistant_id,
                name="Mine",
                description="",
                system_prompt="prompt",
                scope="private",
                created_by=user_id,
                is_active=True,
                tags=[],
            )
        if assistant_id == "other-private":
            return AssistantRecord(
                assistant_id=assistant_id,
                name="Not Mine",
                description="",
                system_prompt="prompt",
                scope="private",
                created_by="other-user",
                is_active=True,
                tags=[],
            )
        return None


class _FakeSessionManager:
    def __init__(self) -> None:
        self.updates: list[tuple[str, dict]] = []

    async def update_session(self, session_id: str, session_data):
        self.updates.append((session_id, session_data.metadata or {}))
        return {"session_id": session_id}


def _load_assistant_routes_module():
    class _DummyLogger:
        def debug(self, *args, **kwargs):
            return None

        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    sys.modules["src.api.deps"] = SimpleNamespace(get_current_user_required=lambda: None)
    sys.modules["src.infra.logging"] = SimpleNamespace(get_logger=lambda _name: _DummyLogger())
    sys.modules["src.infra.session.manager"] = SimpleNamespace(SessionManager=_FakeSessionManager)
    path = Path(__file__).parents[3] / "src/api/routes/assistant.py"
    spec = importlib.util.spec_from_file_location("assistant_routes_under_test", path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError("src.api.routes.assistant")
    module = importlib.util.module_from_spec(spec)
    sys.modules["assistant_routes_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_assistant_collection_routes_use_empty_root_path() -> None:
    assistant_routes = _load_assistant_routes_module()

    route_paths = {route.path for route in assistant_routes.router.routes}

    assert "" in route_paths
    assert "/" not in route_paths


@pytest.mark.asyncio
async def test_list_assistants_returns_public_items() -> None:
    assistant_routes = _load_assistant_routes_module()

    manager = _FakeAssistantManager()

    result = await assistant_routes.list_assistants(
        scope="public",
        search=None,
        tags=None,
        category=None,
        user=SimpleNamespace(sub="user-1", roles=["user"]),
        manager=manager,
    )

    assert [item.assistant_id for item in result] == ["public-1"]


@pytest.mark.asyncio
async def test_select_assistant_writes_snapshot_to_session() -> None:
    from src.infra.assistant.types import AssistantSelectRequest

    assistant_routes = _load_assistant_routes_module()
    manager = _FakeAssistantManager()
    session_manager = _FakeSessionManager()

    result = await assistant_routes.select_assistant(
        assistant_id="public-1",
        request=AssistantSelectRequest(session_id="session-1"),
        user=SimpleNamespace(sub="user-1", roles=["user"]),
        manager=manager,
        session_manager=session_manager,
    )

    assert result["assistant_id"] == "public-1"
    assert session_manager.updates == [
        (
            "session-1",
            {
                "assistant_id": "public-1",
                "assistant_name": "Public One",
                "assistant_prompt_snapshot": "prompt",
            },
        )
    ]


@pytest.mark.asyncio
async def test_clone_assistant_creates_private_copy_for_user() -> None:
    assistant_routes = _load_assistant_routes_module()

    manager = _FakeAssistantManager()

    result = await assistant_routes.clone_assistant(
        assistant_id="public-1",
        user=SimpleNamespace(sub="user-1", roles=["user"]),
        manager=manager,
    )

    assert result.assistant_id == "private-1"
    assert manager.cloned == [("public-1", "user-1")]


@pytest.mark.asyncio
async def test_get_assistant_for_update_rejects_other_users_private_assistant() -> None:
    assistant_routes = _load_assistant_routes_module()

    manager = _FakeAssistantManager()

    with pytest.raises(HTTPException) as exc:
        await assistant_routes._require_owned_or_public_admin_assistant(
            assistant_id="other-private",
            user=SimpleNamespace(sub="user-1", roles=["user"]),
            manager=manager,
        )

    assert exc.value.status_code == 403
