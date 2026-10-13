"""Late goal publications must not replace newer lifecycle metadata across workers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.goal_continuation import publish_goal
from src.kernel.schemas.persistent_goal import PersistentGoal
from tests.api.routes.test_persistent_goal_hitl import SessionCollection, actual_storage


class GoalPublicationCollection(SessionCollection):
    def matches(self, query):
        plain = {}
        for key, expected in query.items():
            if key == "$or":
                if not any(self.matches(branch) for branch in expected):
                    return False
            elif isinstance(expected, dict):
                actual = self.doc
                for part in key.split("."):
                    actual = actual.get(part) if isinstance(actual, dict) else None
                if "$exists" in expected and (actual is not None) != expected["$exists"]:
                    return False
                if "$lte" in expected and (actual is None or actual > expected["$lte"]):
                    return False
            else:
                plain[key] = expected
        return super().matches(plain)


@pytest.mark.parametrize("object_id", [True, False])
async def test_late_old_goal_publication_preserves_new_goal_metadata(monkeypatch, object_id):
    collection = GoalPublicationCollection(object_id=object_id)
    actual_storage(monkeypatch, collection)
    writer = SimpleNamespace(write_event=AsyncMock())
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    current = PersistentGoal(
        id="new-goal",
        session_id=collection.session_id,
        user_id="u",
        objective="new",
        rubric="new",
        version=3,
        revision=30,
        status="active",
        current_run_id="new-run",
    )
    late = PersistentGoal(
        id="old-goal",
        session_id=collection.session_id,
        user_id="u",
        objective="old",
        rubric="old",
        version=2,
        revision=20,
        status="paused",
    )
    await publish_goal(current)
    await publish_goal(late)
    metadata = collection.doc["metadata"]
    assert metadata["persistent_goal_id"] == "new-goal"
    assert metadata["persistent_goal_status"] == "active"
    assert metadata["persistent_goal_run_id"] == "new-run"
    writer.write_event.assert_awaited_once()


async def test_old_status_publication_cannot_revert_newer_revision_of_same_goal(monkeypatch):
    collection = GoalPublicationCollection()
    actual_storage(monkeypatch, collection)
    writer = SimpleNamespace(write_event=AsyncMock())
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    current = PersistentGoal(
        id="same",
        session_id=collection.session_id,
        user_id="u",
        objective="work",
        rubric="tests",
        version=2,
        revision=30,
        status="paused",
    )
    late = current.model_copy(update={"status": "active", "revision": 20})
    await publish_goal(current)
    await publish_goal(late)
    assert collection.doc["metadata"]["persistent_goal_status"] == "paused"
    writer.write_event.assert_awaited_once()
