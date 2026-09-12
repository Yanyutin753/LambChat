from __future__ import annotations

from typing import Any

import pytest

from src.infra.plugin import storage as plugin_storage_module
from src.infra.plugin.storage import PluginStorage
from src.infra.plugin.types import PluginStatus


def _passthrough(value: Any) -> Any:
    return value


@pytest.fixture()
def plain_encryption(monkeypatch: pytest.MonkeyPatch) -> None:
    """绕开 Fernet（测试环境可能缺少密钥），直接透传 headers。"""
    monkeypatch.setattr(plugin_storage_module, "encrypt_value", _passthrough)
    monkeypatch.setattr(plugin_storage_module, "decrypt_value", _passthrough)


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    def sort(self, *_args, **_kwargs):
        return self

    def skip(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def batch_size(self, *_args, **_kwargs):
        return self


class _FakeCollection:
    """极简内存 collection，覆盖 PluginStorage 用到的操作子集。"""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    def _match(self, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, expected in query.items():
            value = doc.get(key)
            if key == "$or":
                if not any(self._match(doc, sub) for sub in expected):
                    return False
            elif isinstance(expected, dict):
                if "$in" in expected and value not in expected["$in"]:
                    return False
                if "$ne" in expected and value == expected["$ne"]:
                    return False
                if "$nin" in expected and value in expected["$nin"]:
                    return False
            elif value != expected:
                return False
        return True

    def find(self, query: dict[str, Any] | None = None, *_args, **_kwargs):
        query = query or {}
        return _FakeCursor([doc for doc in self.docs if self._match(doc, query)])

    async def find_one(self, query: dict[str, Any], *_args, **_kwargs):
        for doc in self.docs:
            if self._match(doc, query):
                return doc
        return None

    async def insert_one(self, doc: dict[str, Any]):
        self.docs.append(dict(doc))

    async def update_one(self, query: dict[str, Any], update: dict[str, Any], *_a, **_kw):
        target = None
        for doc in self.docs:
            if self._match(doc, query):
                target = doc
                break
        if target is None:
            if update.get("$setOnInsert") is not None and update.get("$set") is None:
                self.docs.append({**query, **update["$setOnInsert"]})
                return
            if update.get("$set") is not None and update.get("$setOnInsert") is not None:
                self.docs.append({**query, **update["$set"], **update["$setOnInsert"]})
                return
            return
        for key, value in update.get("$set", {}).items():
            target[key] = value
        for key, value in update.get("$setOnInsert", {}).items():
            target.setdefault(key, value)
        if "$inc" in update:
            for key, delta in update["$inc"].items():
                target[key] = target.get(key, 0) + delta

    async def delete_one(self, query: dict[str, Any]):
        for doc in self.docs:
            if self._match(doc, query):
                self.docs.remove(doc)
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    async def delete_many(self, query: dict[str, Any]):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not self._match(doc, query)]
        return type("R", (), {"deleted_count": before - len(self.docs)})()

    async def count_documents(self, query: dict[str, Any]):
        return sum(1 for doc in self.docs if self._match(doc, query))

    def create_index(self, *_args, **_kwargs):
        return None

    async def bulk_write(self, operations, ordered=True):
        for op in operations:
            await self.update_one(
                dict(op._filter),
                {"$set": op._doc["$set"], "$setOnInsert": op._doc.get("$setOnInsert", {})},
            )
        return None


def _make_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PluginStorage, _FakeCollection, _FakeCollection, _FakeCollection]:
    storage = PluginStorage()
    plugins = _FakeCollection()
    files = _FakeCollection()
    installs = _FakeCollection()
    monkeypatch.setattr(storage, "_get_plugins_collection", lambda: plugins)
    monkeypatch.setattr(storage, "_get_files_collection", lambda: files)
    monkeypatch.setattr(storage, "_get_installs_collection", lambda: installs)

    async def _no_usernames(user_ids):
        return {uid: f"user-{uid}" for uid in user_ids}

    monkeypatch.setattr(storage, "_batch_get_usernames", _no_usernames)
    return storage, plugins, files, installs


@pytest.mark.asyncio
async def test_create_and_get_plugin_masks_mcp_headers(
    monkeypatch: pytest.MonkeyPatch, plain_encryption: None
) -> None:
    storage, plugins, _files, _installs = _make_storage(monkeypatch)
    doc = {
        "name": "research-kit",
        "skills": [{"skill_name": "deep-research", "description": "", "tags": []}],
        "mcp_servers": [
            {
                "name": "arxiv",
                "transport": "streamable_http",
                "url": "https://x",
                "headers": {"Authorization": "secret"},
            }
        ],
        "status": PluginStatus.ACTIVE.value,
        "created_by": "user-1",
    }
    await storage.create_plugin(doc)

    stored = plugins.docs[0]
    assert stored["mcp_servers"][0]["headers"] == {"Authorization": "secret"}

    response = await storage.get_plugin_response("research-kit", viewer_id="user-1")
    assert response is not None
    assert response.mcp_servers[0].headers == {"Authorization": "•••••"}
    assert response.status is PluginStatus.ACTIVE
    assert response.is_owner is True


@pytest.mark.asyncio
async def test_list_plugins_filters_by_active_or_owner(
    monkeypatch: pytest.MonkeyPatch, plain_encryption: None
) -> None:
    storage, plugins, _f, _i = _make_storage(monkeypatch)
    plugins.docs = [
        {"name": "a", "status": "active", "created_by": "other", "updated_at": "3"},
        {"name": "b", "status": "draft", "created_by": "user-1", "updated_at": "2"},
        {"name": "c", "status": "deactivated", "created_by": "other", "updated_at": "1"},
    ]
    results, total = await storage.list_plugins(viewer_id="user-1", user_id="user-1")
    assert [r.name for r in results] == ["a", "b"]
    assert total == 2


@pytest.mark.asyncio
async def test_install_record_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    storage, _p, _f, installs = _make_storage(monkeypatch)
    assert await storage.get_install("user-1", "research-kit") is None
    await storage.upsert_install("user-1", "research-kit", "1.2.0")
    record = await storage.get_install("user-1", "research-kit")
    assert record is not None
    assert record.version == "1.2.0"
    versions = await storage.get_install_versions("user-1", ["research-kit", "missing"])
    assert versions == {"research-kit": "1.2.0"}
    assert await storage.delete_install("user-1", "research-kit") is True
    assert await storage.get_install("user-1", "research-kit") is None


@pytest.mark.asyncio
async def test_write_and_read_skill_files(monkeypatch: pytest.MonkeyPatch) -> None:
    storage, _p, files, _i = _make_storage(monkeypatch)
    await storage.write_skill_files(
        "research-kit", "deep-research", {"SKILL.md": "# Hi", "notes.md": "x"}
    )
    await storage.write_skill_files("research-kit", "deep-research", {"SKILL.md": "# Hi"})

    paths = await storage.list_skill_file_paths("research-kit", "deep-research")
    assert paths == ["SKILL.md"]
    assert await storage.read_skill_file("research-kit", "deep-research", "SKILL.md") == "# Hi"
