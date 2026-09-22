from __future__ import annotations

from typing import Any

import pytest

from src.infra.channel import channel_storage
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.feishu.storage import FeishuStorage
from src.kernel.schemas.channel import ChannelType


class _FakeCollection:
    def __init__(self) -> None:
        self.created_indexes: list[tuple[object, dict[str, object]]] = []

    async def create_index(self, keys, **kwargs):
        self.created_indexes.append((keys, kwargs))


class _EmptyCursor:
    def __init__(self) -> None:
        self.limit_calls: list[int] = []

    def limit(self, value: int):
        self.limit_calls.append(value)
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _ListCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.index = 0
        self.limit_calls: list[int] = []

    def limit(self, value: int):
        self.limit_calls.append(value)
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.docs):
            raise StopAsyncIteration
        doc = self.docs[self.index]
        self.index += 1
        return doc


class _ListCollection(_FakeCollection):
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self.find_queries: list[dict[str, object]] = []
        self.cursor = _ListCursor(docs) if docs is not None else _EmptyCursor()
        self.inserted_docs: list[dict[str, Any]] = []

    def find(self, query: dict[str, object]):
        self.find_queries.append(query)
        return self.cursor

    async def insert_one(self, doc: dict[str, Any]):
        self.inserted_docs.append(dict(doc))

    async def find_one(self, query: dict[str, Any]):
        for doc in getattr(self.cursor, "docs", []):
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None


class _FakeDb:
    def __init__(self, collection: _FakeCollection) -> None:
        self._collection = collection

    def __getitem__(self, name: str):
        return self._collection


class _FakeClient:
    def __init__(self, collection: _FakeCollection) -> None:
        self._db = _FakeDb(collection)
        self.close_calls = 0

    def __getitem__(self, name: str):
        return self._db

    def close(self) -> None:
        self.close_calls += 1


def _channel_doc() -> dict[str, Any]:
    return {
        "user_id": "user-1",
        "channel_type": "feishu",
        "instance_id": "instance-1",
        "name": "Feishu",
        "config": {
            "app_id": "cli_a",
            "app_secret": {"encrypted": "secret"},
        },
        "enabled": True,
    }


@pytest.mark.asyncio
async def test_channel_storage_indexes_created_once_across_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeCollection()
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.channel.channel_storage.get_mongo_client", lambda: client)
    monkeypatch.setattr(ChannelStorage, "_indexes_done", False, raising=False)
    monkeypatch.setattr(ChannelStorage, "_indexes_task", None, raising=False)
    monkeypatch.setattr(ChannelStorage, "_indexes_lock", None, raising=False)

    first = ChannelStorage()
    second = ChannelStorage()

    await first.ensure_indexes_if_needed()
    await second.ensure_indexes_if_needed()

    assert len(collection.created_indexes) == 2
    assert collection.created_indexes[0][1]["name"] == "user_channel_instance_idx"
    assert collection.created_indexes[1][1]["name"] == "channel_enabled_idx"


@pytest.mark.asyncio
async def test_list_user_configs_applies_storage_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.channel_storage import CHANNEL_CONFIG_LIST_LIMIT

    collection = _ListCollection()
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.channel.channel_storage.get_mongo_client", lambda: client)
    monkeypatch.setattr(ChannelStorage, "_indexes_done", True, raising=False)

    storage = ChannelStorage()
    configs = await storage.list_user_configs("user-1")

    assert configs == []
    assert collection.find_queries == [{"user_id": "user-1"}]
    assert collection.cursor.limit_calls == [CHANNEL_CONFIG_LIST_LIMIT]


@pytest.mark.asyncio
async def test_list_user_configs_by_type_applies_storage_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.channel_storage import CHANNEL_CONFIG_LIST_LIMIT
    from src.kernel.schemas.channel import ChannelType

    collection = _ListCollection()
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.channel.channel_storage.get_mongo_client", lambda: client)
    monkeypatch.setattr(ChannelStorage, "_indexes_done", True, raising=False)

    storage = ChannelStorage()
    configs = await storage.list_user_configs_by_type("user-1", ChannelType.FEISHU)

    assert configs == []
    assert collection.find_queries == [{"user_id": "user-1", "channel_type": "feishu"}]
    assert collection.cursor.limit_calls == [CHANNEL_CONFIG_LIST_LIMIT]


@pytest.mark.asyncio
async def test_iter_enabled_configs_applies_storage_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.channel_storage import CHANNEL_CONFIG_LIST_LIMIT

    collection = _ListCollection()
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.channel.channel_storage.get_mongo_client", lambda: client)
    monkeypatch.setattr(ChannelStorage, "_indexes_done", True, raising=False)

    storage = ChannelStorage()
    configs = [config async for config in storage.iter_enabled_configs(ChannelType.FEISHU)]

    assert configs == []
    assert collection.find_queries == [{"channel_type": "feishu", "enabled": True}]
    assert collection.cursor.limit_calls == [CHANNEL_CONFIG_LIST_LIMIT]


@pytest.mark.asyncio
async def test_list_user_configs_offloads_sensitive_field_decryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    collection = _ListCollection([_channel_doc()])
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.channel.channel_storage.get_mongo_client", lambda: client)
    monkeypatch.setattr(ChannelStorage, "_indexes_done", True, raising=False)

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return {"value": "plain-secret"}

    monkeypatch.setattr(
        channel_storage, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )

    storage = ChannelStorage()
    configs = await storage.list_user_configs("user-1")

    assert calls == [channel_storage.decrypt_value]
    assert configs[0]["app_secret"] == "plain-secret"


@pytest.mark.asyncio
async def test_create_config_offloads_sensitive_field_encryption_and_decryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    collection = _ListCollection([])
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.channel.channel_storage.get_mongo_client", lambda: client)
    monkeypatch.setattr(ChannelStorage, "_indexes_done", True, raising=False)

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        calls.append(func)
        if func is channel_storage.encrypt_value:
            return {"encrypted": args[0]}
        return {"value": "plain-secret"}

    monkeypatch.setattr(
        channel_storage, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )

    storage = ChannelStorage()
    config = await storage.create_config(
        "user-1",
        ChannelType.FEISHU,
        {"app_id": "cli_a", "app_secret": "plain-secret"},
        "Feishu",
    )

    assert calls == [channel_storage.encrypt_value, channel_storage.decrypt_value]
    assert collection.inserted_docs[0]["config"]["app_secret"] == {
        "encrypted": {"value": "plain-secret"}
    }
    assert config["app_secret"] == "plain-secret"


@pytest.mark.asyncio
async def test_feishu_list_enabled_configs_applies_storage_limit() -> None:
    from src.infra.channel.feishu.storage import FEISHU_CONFIG_LIST_LIMIT

    collection = _ListCollection()
    storage = FeishuStorage()
    storage._collection = collection

    configs = await storage.list_enabled_configs()

    assert configs == []
    assert collection.find_queries == [{"enabled": True}]
    assert collection.cursor.limit_calls == [FEISHU_CONFIG_LIST_LIMIT]


@pytest.mark.asyncio
async def test_feishu_storage_close_only_clears_local_refs() -> None:
    collection = _ListCollection()
    client = _FakeClient(collection)
    storage = FeishuStorage()
    storage._client = client
    storage._collection = collection

    await storage.close()

    assert client.close_calls == 0
    assert storage._client is None
    assert storage._collection is None
