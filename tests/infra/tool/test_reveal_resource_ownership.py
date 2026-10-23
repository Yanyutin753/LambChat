"""Only resources actually uploaded by reveal_file receive a document association."""

import json
from copy import deepcopy
from importlib import import_module, util
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.storage.s3.types import UploadResult
from src.infra.tool import _reveal_file_support, reveal_file_tool
from src.kernel.errors import AppError

BASE = "https://chat.example"
PARENT = "revealed_files/server-page.html"
CHILD = "revealed_files/server-image.png"
KNOWN_OTHER = "image/owner/unrelated.png"


def _links():
    assert util.find_spec("src.infra.upload.resource_links") is not None, (
        "Server-generated resource associations are not implemented"
    )
    return import_module("src.infra.upload.resource_links")


async def test_reference_collector_only_records_successfully_uploaded_local_keys(monkeypatch):
    async def upload(local_path, *args):
        return BASE + "/api/upload/file/" + CHILD if local_path == "./image.png" else None

    monkeypatch.setattr(_reveal_file_support, "_upload_local_resource", upload)
    keys = []
    content = (
        '<img src="./image.png"><img src="./missing.png">'
        f'<img src="{BASE}/api/upload/file/{KNOWN_OTHER}">'
    ).encode()
    resolved = await _reveal_file_support._resolve_local_references(
        content, "/workspace", object(), object(), BASE, resource_keys=keys
    )
    assert keys == [CHILD]
    assert (BASE + "/api/upload/file/" + CHILD).encode() in resolved
    assert (BASE + "/api/upload/file/" + KNOWN_OTHER).encode() in resolved
    assert b"./missing.png" in resolved


async def test_existing_remote_urls_never_create_resource_associations(monkeypatch):
    upload = AsyncMock(side_effect=AssertionError("remote URLs must not be re-uploaded"))
    monkeypatch.setattr(_reveal_file_support, "_upload_local_resource", upload)
    content = f'<img src="{BASE}/api/upload/file/{KNOWN_OTHER}">'.encode()
    keys = []
    assert (
        await _reveal_file_support._resolve_local_references(
            content, "/workspace", object(), object(), BASE, resource_keys=keys
        )
        == content
    )
    assert keys == []


def _matches(document, query):
    for field, expected in query.items():
        if field == "$or":
            if not any(_matches(document, alternative) for alternative in expected):
                return False
        elif isinstance(expected, dict):
            if "$exists" in expected and (field in document) != expected["$exists"]:
                return False
            if "$in" in expected and document.get(field) not in expected["$in"]:
                return False
        elif document.get(field) != expected:
            return False
    return True


class _Records:
    def __init__(self):
        self.documents = {
            key: {"key": key, "uploaded_by": "owner", "hash": "generated:" + key}
            for key in [PARENT, CHILD]
        }
        self.collection = self
        self.race_child_owner = False

    async def find_by_key(self, key, *args):
        return deepcopy(self.documents.get(key))

    def find(self, query, *args):
        async def rows():
            for document in self.documents.values():
                if _matches(document, query):
                    yield deepcopy(document)

        return rows()

    async def update_one(self, query, update, **kwargs):
        if self.race_child_owner:
            self.documents[CHILD]["uploaded_by"] = "other"
            self.race_child_owner = False
        for document in self.documents.values():
            if _matches(document, query):
                document.update(update.get("$set", {}))
                for field, addition in update.get("$addToSet", {}).items():
                    for value in addition.get("$each", [addition]):
                        if value not in document.setdefault(field, []):
                            document[field].append(value)
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


@pytest.fixture
def registry(monkeypatch):
    module = _links()
    records = _Records()
    monkeypatch.setattr(module, "get_file_record_storage", lambda: records)
    return module, records


async def test_generated_resources_are_bound_to_their_parent_and_preserve_real_prior_links(
    registry,
):
    module, records = registry
    records.documents[PARENT]["resource_keys"] = ["revealed_files/previous.png"]
    await module.link_generated_resources(PARENT, "owner", [CHILD])
    assert records.documents[PARENT]["resource_keys"] == ["revealed_files/previous.png", CHILD]
    assert records.documents[CHILD]["resource_parent_key"] == PARENT
    assert records.documents[CHILD]["uploaded_by"] == "owner"


@pytest.mark.parametrize("key", [PARENT, CHILD])
async def test_resource_linking_rejects_a_foreign_parent_or_child(registry, key):
    module, records = registry
    records.documents[key]["uploaded_by"] = "other"
    before = deepcopy(records.documents)
    with pytest.raises(AppError):
        await module.link_generated_resources(PARENT, "owner", [CHILD])
    assert records.documents == before


@pytest.mark.parametrize(
    "flags",
    [
        {"hash": "ordinary-upload"},
        {"deleting_at": "pending"},
        {"private_session_id": "private"},
        {"resource_parent_key": "revealed_files/different.html"},
    ],
)
async def test_resource_linking_rejects_unproven_or_already_bound_children(registry, flags):
    module, records = registry
    records.documents[CHILD].update(flags)
    before = deepcopy(records.documents)
    with pytest.raises(AppError):
        await module.link_generated_resources(PARENT, "owner", [CHILD])
    assert records.documents == before


async def test_database_write_guard_rechecks_owner_after_the_read(registry):
    module, records = registry
    records.race_child_owner = True
    with pytest.raises(AppError):
        await module.link_generated_resources(PARENT, "owner", [CHILD])
    assert "resource_parent_key" not in records.documents[CHILD]
    assert CHILD not in records.documents[PARENT].get("resource_keys", [])


@pytest.mark.parametrize("reuse", [False, True])
async def test_reveal_file_registers_uploaded_resource_links_before_returning(
    registry, monkeypatch, reuse
):
    _, records = registry
    storage = SimpleNamespace(
        upload_file=AsyncMock(
            return_value=UploadResult(
                key=PARENT,
                url=BASE + "/api/upload/file/" + PARENT,
                size=10,
                content_type="text/html",
            )
        )
    )
    content = (
        '<img src="./image.png">'
        f'<script>const unrelated="{BASE}/api/upload/file/{KNOWN_OTHER}";</script>'
    ).encode()
    monkeypatch.setattr(reveal_file_tool, "_get_storage", AsyncMock(return_value=storage))
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: object())
    monkeypatch.setattr(
        reveal_file_tool, "_get_backend_file_size", AsyncMock(return_value=len(content))
    )
    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", AsyncMock(return_value=content)
    )
    monkeypatch.setattr(reveal_file_tool, "_index_revealed_file", AsyncMock())
    monkeypatch.setattr(reveal_file_tool, "_reveal_user_id", lambda runtime: "owner")
    monkeypatch.setattr(
        reveal_file_tool,
        "_try_reuse_upload",
        AsyncMock(
            return_value=UploadResult(key=PARENT, url="", size=10, content_type="text/html")
            if reuse
            else None
        ),
    )
    monkeypatch.setattr(
        _reveal_file_support,
        "_upload_local_resource",
        AsyncMock(return_value=BASE + "/api/upload/file/" + CHILD),
    )
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "base_url": BASE,
                "context": SimpleNamespace(user_id="owner", session_id="session"),
            }
        }
    )
    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine("/workspace/page.html", runtime=runtime)
    )
    assert result["key"] == PARENT
    assert records.documents[PARENT]["resource_keys"] == [CHILD]
    assert records.documents[CHILD]["resource_parent_key"] == PARENT
    assert KNOWN_OTHER not in records.documents[PARENT]["resource_keys"]
