from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.infra.mcp import storage as mcp_storage
from src.infra.mcp.storage import MCPStorage
from src.kernel.schemas.mcp import MCPImportRequest, MCPServerUpdate


async def _cursor(docs):
    for doc in docs:
        yield dict(doc)


class _Collection:
    def __init__(self, docs):
        self.docs = docs
        self.find_calls = []
        self.point_calls = []
        self.atomic_calls = []
        self.inserted = []
        self.insert_errors = set()

    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            if isinstance(expected, dict):
                if "$in" in expected and doc.get(key) not in expected["$in"]:
                    return False
                if "$ne" in expected and doc.get(key) == expected["$ne"]:
                    return False
            elif doc.get(key) != expected:
                return False
        return True

    def find(self, query, projection):
        self.find_calls.append((query, projection))
        return _cursor([doc for doc in self.docs if self._matches(doc, query)])

    async def find_one(self, query):
        self.point_calls.append(query)
        return next((dict(doc) for doc in self.docs if self._matches(doc, query)), None)

    async def update_one(self, query, update):
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update["$set"])
        return SimpleNamespace(modified_count=1)

    async def find_one_and_update(self, query, update, *, return_document):
        self.atomic_calls.append(query)
        assert return_document == ReturnDocument.AFTER
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update["$set"])
                return dict(doc)
        return None

    async def insert_one(self, doc):
        if doc["name"] in self.insert_errors or any(
            existing["name"] == doc["name"] and existing.get("user_id") == doc.get("user_id")
            for existing in self.docs
        ):
            raise DuplicateKeyError("name reserved")
        self.inserted.append(dict(doc))
        self.docs.append(dict(doc))


def _doc(name, *, user_id="owner", transport="streamable_http"):
    return {"name": name, "user_id": user_id, "transport": transport}


def _storage(monkeypatch, collection, admin):
    storage = MCPStorage()
    storage._system_collection = collection
    storage._user_collection = collection
    storage._invalidate_user_cache = AsyncMock()
    storage._invalidate_all_cache = AsyncMock()
    storage._doc_to_user_server_async = AsyncMock(side_effect=lambda doc: doc)
    storage._doc_to_system_server_async = AsyncMock(side_effect=lambda doc: doc)
    monkeypatch.setattr(
        mcp_storage,
        "encrypt_server_secrets",
        lambda doc: {**doc, "headers": "encrypted"} if doc.get("headers") else doc,
    )
    monkeypatch.setattr(mcp_storage, "encrypt_value", lambda value: "encrypted")
    return storage


@pytest.mark.parametrize("count", [1, 100])
@pytest.mark.parametrize("admin", [False, True])
async def test_import_skipped_names_uses_one_batch_read(monkeypatch, count, admin):
    names = [f"server-{index}" for index in range(count)]
    collection = _Collection([_doc(name) for name in names])
    storage = _storage(monkeypatch, collection, admin)
    result = await storage.import_servers(
        MCPImportRequest(servers={name: {"url": "https://example.test/mcp"} for name in names}),
        "owner",
        is_admin=admin,
    )

    assert result == (0, count, [])
    query = {"name": {"$in": names}}
    if not admin:
        query["user_id"] = "owner"
    assert collection.find_calls == [(query, {"name": 1, "transport": 1})]
    assert collection.point_calls == []
    assert collection.atomic_calls == []
    assert collection.inserted == []


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("overwrite", [False, True])
async def test_import_preserves_reservations_partial_errors_encryption_and_owner(
    monkeypatch, admin, overwrite
):
    docs = [_doc("existing"), _doc("legacy", transport="sandbox")]
    if not admin:
        docs.append(_doc("new", user_id="other"))
    collection = _Collection(docs)
    collection.insert_errors.add("racing")
    storage = _storage(monkeypatch, collection, admin)
    config = {"url": "https://example.test/mcp", "headers": {"Authorization": "secret"}}
    result = await storage.import_servers(
        MCPImportRequest(
            servers={
                "existing": config,
                "legacy": config,
                "invalid": {"transport": "unsupported"},
                "racing": config,
                "new": config,
            },
            overwrite=overwrite,
        ),
        "owner",
        is_admin=admin,
    )

    assert result == (
        2 if overwrite else 1,
        1 if overwrite else 2,
        [
            "Invalid transport 'unsupported' for server 'invalid'",
            "Error importing 'racing': name reserved",
        ],
    )
    assert len(collection.find_calls) == 1
    assert collection.point_calls == []
    assert len(collection.atomic_calls) == int(overwrite)
    assert [doc["name"] for doc in collection.inserted] == ["new"]
    assert collection.inserted[0]["headers"] == "encrypted"
    assert next(doc for doc in collection.docs if doc["name"] == "legacy")["transport"] == "sandbox"
    if not admin:
        assert (
            next(doc for doc in docs if doc.get("user_id") == "other")["transport"]
            == "streamable_http"
        )
        assert storage._invalidate_user_cache.await_count == (2 if overwrite else 1)
    else:
        assert storage._invalidate_all_cache.await_count == (3 if overwrite else 2)


@pytest.mark.parametrize("admin", [False, True])
async def test_update_atomically_filters_legacy_and_returns_updated_document(monkeypatch, admin):
    collection = _Collection(
        [
            _doc("existing"),
            _doc("legacy", transport="sandbox"),
            _doc("foreign", user_id="other"),
        ]
    )
    storage = _storage(monkeypatch, collection, admin)
    updates = MCPServerUpdate(enabled=False, headers={"Authorization": "new-secret"})
    update = storage.update_system_server if admin else storage.update_user_server

    result = await update("existing", updates, "owner")
    assert result["enabled"] is False
    assert result["headers"] == "encrypted"
    assert await update("legacy", updates, "owner") is None
    if not admin:
        assert await update("foreign", updates, "owner") is None
    assert collection.point_calls == []
    expected_query = {"name": "existing", "transport": {"$ne": "sandbox"}}
    if not admin:
        expected_query["user_id"] = "owner"
    assert collection.atomic_calls[0] == expected_query


@pytest.mark.parametrize("admin", [False, True])
async def test_import_reports_stale_update_snapshot_as_an_item_error(monkeypatch, admin):
    collection = _Collection([_doc("existing")])
    storage = _storage(monkeypatch, collection, admin)
    collection.find_one_and_update = AsyncMock(return_value=None)
    result = await storage.import_servers(
        MCPImportRequest(servers={"existing": {"url": "https://example.test/mcp"}}, overwrite=True),
        "owner",
        is_admin=admin,
    )

    assert result == (0, 0, ["Error importing 'existing': Server is no longer available"])
    storage._invalidate_user_cache.assert_not_awaited()
    storage._invalidate_all_cache.assert_not_awaited()


async def test_import_batch_lookup_failure_keeps_item_validation_and_error_order(monkeypatch):
    collection = _Collection([])
    storage = _storage(monkeypatch, collection, False)

    def failed_lookup(*args):
        raise RuntimeError("lookup failed")

    monkeypatch.setattr(collection, "find", failed_lookup)
    collection.find_one = AsyncMock(side_effect=[RuntimeError("item lookup failed"), None, None])
    result = await storage.import_servers(
        MCPImportRequest(
            servers={
                "invalid": {"transport": "unsupported"},
                "unavailable": {"url": "https://example.test/mcp"},
                "valid": {"url": "https://example.test/mcp"},
            }
        ),
        "owner",
    )

    assert result == (
        1,
        0,
        [
            "Invalid transport 'unsupported' for server 'invalid'",
            "Error importing 'unavailable': item lookup failed",
        ],
    )
    assert [doc["name"] for doc in collection.inserted] == ["valid"]
