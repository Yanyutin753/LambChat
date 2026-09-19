from types import SimpleNamespace

import pytest

from src.infra.session.storage import SessionStorage


@pytest.mark.asyncio
async def test_move_to_project_invalidates_memory_scope_and_index_snapshots(monkeypatch):
    class FakeCollection:
        async def find_one_and_update(self, query, update, return_document):
            assert query == {"session_id": "s1", "user_id": "u1"}
            assert update["$set"]["metadata.project_id"] == "p2"
            return {"session_id": "s1", "metadata": {"project_id": "p2"}}

    storage = SessionStorage()
    storage._collection = FakeCollection()
    storage.ensure_indexes_if_needed = _noop_indexes  # type: ignore[method-assign]
    storage._build_session = lambda document: document  # type: ignore[method-assign]
    scope_invalidated: list[str | None] = []
    snapshots_invalidated: list[str] = []
    monkeypatch.setattr(
        "src.infra.memory.scope.invalidate_session_project_cache",
        scope_invalidated.append,
    )
    monkeypatch.setattr(
        "src.infra.agent.middleware.prompt_injection.invalidate_memory_index_snapshot",
        snapshots_invalidated.append,
    )

    result = await storage.move_to_project("s1", "u1", "p2")

    assert result["metadata"]["project_id"] == "p2"
    assert scope_invalidated == ["s1"]
    assert snapshots_invalidated == ["u1"]


async def _noop_indexes() -> None:
    return None


@pytest.mark.asyncio
async def test_clear_project_id_invalidates_all_scope_cache(monkeypatch):
    class FakeCollection:
        async def update_many(self, query, update):
            assert query == {"user_id": "u1", "metadata.project_id": "p1"}
            assert update["$set"]["metadata.project_id"] is None
            return SimpleNamespace(modified_count=2)

    storage = SessionStorage()
    storage._collection = FakeCollection()
    storage.ensure_indexes_if_needed = _noop_indexes  # type: ignore[method-assign]
    invalidated: list[str | None] = []
    snapshots_invalidated: list[str] = []
    monkeypatch.setattr(
        "src.infra.memory.scope.invalidate_session_project_cache",
        lambda session_id=None: invalidated.append(session_id),
    )
    monkeypatch.setattr(
        "src.infra.agent.middleware.prompt_injection.invalidate_memory_index_snapshot",
        snapshots_invalidated.append,
    )

    assert await storage.clear_project_id("p1", "u1") == 2
    assert invalidated == [None]
    assert snapshots_invalidated == ["u1"]
