from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
import pytest

from src.infra.folder.storage import ProjectStorage
from src.kernel.schemas.project import ProjectUpdate

PROJECT_LIST_LIMIT = 100


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self.limit_value: int | None = None
        self.to_list_length: int | None = None

    def sort(self, *_args):
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    async def to_list(self, length: int | None = None):
        self.to_list_length = length
        cap = self.limit_value if self.limit_value is not None else length
        return self._docs[: cap or None]


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.cursor = _FakeCursor(docs)
        self.update_filter: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None

    def find(self, *_args):
        return self.cursor

    async def find_one_and_update(self, filter_doc, update_doc, return_document=None):
        self.update_filter = filter_doc
        self.update_payload = update_doc
        if not self.cursor._docs:
            return None
        updated = dict(self.cursor._docs[0])
        for key, value in update_doc.get("$set", {}).items():
            if key.startswith("metadata."):
                metadata_key = key.removeprefix("metadata.")
                metadata = dict(updated.get("metadata") or {})
                metadata[metadata_key] = value
                updated["metadata"] = metadata
            else:
                updated[key] = value
        return updated


def _project_doc(index: int) -> dict[str, Any]:
    return {
        "_id": f"project-{index}",
        "name": f"Project {index}",
        "type": "custom",
        "icon": "Folder",
        "sort_order": index,
        "user_id": "user-1",
        "created_at": datetime(2026, 4, 25, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 4, 25, tzinfo=timezone.utc),
    }


@pytest.mark.asyncio
async def test_list_projects_applies_cursor_limit() -> None:
    storage = ProjectStorage()
    storage._collection = _FakeCollection([_project_doc(index) for index in range(150)])

    projects = await storage.list_projects("user-1")

    assert len(projects) == PROJECT_LIST_LIMIT
    assert storage.collection.cursor.limit_value == PROJECT_LIST_LIMIT
    assert storage.collection.cursor.to_list_length == PROJECT_LIST_LIMIT


@pytest.mark.asyncio
async def test_update_project_writes_metadata_plugin_options() -> None:
    project_id = ObjectId()
    doc = _project_doc(1)
    doc["_id"] = project_id
    storage = ProjectStorage()
    storage._collection = _FakeCollection([doc])

    project = await storage.update(
        str(project_id),
        "user-1",
        ProjectUpdate(metadata={"plugin_options": {"agent_team": {"DEFAULT_TEAM_ID": "team-1"}}}),
    )

    assert project is not None
    assert project.metadata == {"plugin_options": {"agent_team": {"DEFAULT_TEAM_ID": "team-1"}}}
    assert storage.collection.update_payload is not None
    assert storage.collection.update_payload["$set"]["metadata.plugin_options"] == {
        "agent_team": {"DEFAULT_TEAM_ID": "team-1"}
    }
