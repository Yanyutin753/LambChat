"""Assistant memory uses explicit, owner-checked partitions rather than personal recall."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.kernel.errors import AppError


@pytest.mark.parametrize(
    "mode,expected",
    [("private", "assistant-memory:helper"), ("project", "assistant-project-memory:project")],
)
async def test_memory_partition_is_explicit_and_project_sharing_checks_live_ownership(
    monkeypatch, mode, expected
):
    from src.infra.assistant.memory import assistant_memory_partition
    from src.infra.folder.storage import ProjectStorage

    lookup = AsyncMock(return_value=SimpleNamespace(id="project"))
    monkeypatch.setattr(ProjectStorage, "get_by_id", lookup)
    helper = SimpleNamespace(id="helper", user_id="owner", memory_mode=mode, project_id="project")
    assert await assistant_memory_partition(helper) == expected
    if mode == "project":
        lookup.assert_awaited_once_with("project", "owner")
        lookup.return_value = None
        with pytest.raises(AppError):
            await assistant_memory_partition(helper)
    else:
        lookup.assert_not_awaited()


@pytest.mark.parametrize(
    "partition",
    ["assistant-memory:a", "assistant-project-memory:p", "assistant-discussion-memory:d"],
)
def test_assistant_search_never_includes_personal_or_other_assistant_memories(partition):
    from src.infra.memory.client.native.search import build_scope_clause

    assert build_scope_clause(partition) == {"scope": "project", "project_id": partition}


@pytest.mark.parametrize("requested", [None, "user", "reference", "project"])
def test_assistant_retain_cannot_escape_its_partition(requested):
    from src.infra.memory.scope import resolve_retain_scope

    assert resolve_retain_scope(scope=requested, project_id="assistant-memory:a") == (
        "project",
        "assistant-memory:a",
    )


async def test_memory_resolution_rejects_forged_assistant_marker(monkeypatch):
    from src.infra.assistant.memory import session_assistant_partition
    from src.infra.assistant.store import AssistantStore

    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=None))
    with pytest.raises(AppError):
        await session_assistant_partition("session", "owner", {"assistant_id": "foreign"})


async def test_assistant_memory_index_has_no_personal_candidate_scan():
    from src.infra.memory.client.native.indexing import build_memory_index

    queries = []

    class Cursor:
        def sort(self, *args):
            return self

        def limit(self, *args):
            return self

        async def to_list(self, **kwargs):
            return []

    class Collection:
        def find(self, query, projection):
            queries.append(query)
            return Cursor()

    backend = SimpleNamespace(_index_cache={}, _collection=Collection())
    assert await build_memory_index(backend, "owner", "assistant-memory:helper") == ""
    assert len(queries) == 1
    assert queries[0]["scope"] == "project"
    assert queries[0]["project_id"] == "assistant-memory:helper"


async def test_assistant_memory_scope_rechecks_sharing_without_a_ttl(monkeypatch):
    from src.infra.assistant.store import AssistantStore
    from src.infra.folder.storage import ProjectStorage
    from src.infra.memory import scope

    helper = SimpleNamespace(
        id="helper", user_id="owner", memory_mode="private", project_id="project"
    )
    lookup = AsyncMock(return_value=helper)
    monkeypatch.setattr(AssistantStore, "for_session", lookup)
    monkeypatch.setattr(ProjectStorage, "get_by_id", AsyncMock(return_value=object()))
    sessions = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "user_id": "owner",
                "metadata": {"assistant_id": "helper", "project_id": "project"},
            }
        )
    )
    monkeypatch.setattr(scope, "_get_sessions_collection", lambda: sessions)
    scope.invalidate_session_project_cache("assistant-session")
    assert await scope.resolve_session_project_id("assistant-session") == "assistant-memory:helper"
    helper.memory_mode = "project"
    assert (
        await scope.resolve_session_project_id("assistant-session")
        == "assistant-project-memory:project"
    )
    assert lookup.await_count == 2


async def test_failed_scope_lookup_replaces_an_old_navigation_index(monkeypatch):
    from langchain_core.messages import HumanMessage

    from src.infra.agent.middleware.prompt_injection import MemoryRecallIndexMiddleware
    from src.infra.memory.scope import ScopeResolutionError

    monkeypatch.setattr(
        "src.infra.memory.scope.resolve_session_project_id",
        AsyncMock(side_effect=ScopeResolutionError("unavailable")),
    )
    middleware = MemoryRecallIndexMiddleware(
        user_id="owner", session_id="session", recall_available=True
    )
    update = await middleware.abefore_agent(
        {"messages": [HumanMessage(content="Old private index", name="task_context")]}, None
    )
    assert update is not None
    assert "Old private index" not in update["messages"][0].content
    assert "absent index" in update["messages"][0].content
