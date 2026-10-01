from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from src.infra.folder.storage import ProjectStorage
from src.kernel.schemas.project import ProjectCreate, ProjectUpdate

WORKSPACE = {"id": "local-" + "a" * 32, "machineId": "mac", "path": "/Users/dev/project"}


async def test_project_workspace_is_saved_and_can_be_cleared():
    storage = ProjectStorage()
    identifier = ObjectId()
    collection = AsyncMock()
    collection.insert_one.return_value = SimpleNamespace(inserted_id=identifier)
    storage._collection = collection
    created = await storage.create(ProjectCreate(name="Project", workspace=WORKSPACE), "owner")
    assert collection.insert_one.call_args.args[0]["workspace"] == WORKSPACE
    doc = {**created.model_dump(by_alias=True), "_id": identifier}
    collection.find_one_and_update.side_effect = lambda *_a, **_kw: dict(doc)
    await storage.update(str(identifier), "owner", ProjectUpdate(workspace=None))
    assert collection.find_one_and_update.call_args.args[1]["$set"]["workspace"] is None
    await storage.update(str(identifier), "owner", ProjectUpdate(name="Renamed"))
    assert "workspace" not in collection.find_one_and_update.call_args.args[1]["$set"]


def test_project_rejects_non_opaque_workspace_identifier():
    with pytest.raises(ValueError):
        ProjectCreate(name="Project", workspace={**WORKSPACE, "id": "../../etc"})
