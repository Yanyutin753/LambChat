from __future__ import annotations

from typing import Any

import pytest

from src.infra.channel.feishu import storage as feishu_storage
from src.kernel.schemas.feishu import FeishuConfigCreate, FeishuGroupPolicy


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self._index = 0
        self.limit_value: int | None = None

    def limit(self, value: int):
        self.limit_value = value
        return self

    def __aiter__(self):
        if self.limit_value is not None:
            self._docs = self._docs[: self.limit_value]
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return doc


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = docs or []
        self.insert_calls: list[dict[str, Any]] = []
        self.update_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        return next((doc for doc in self.docs if _matches(doc, query)), None)

    async def insert_one(self, doc: dict[str, Any]) -> None:
        self.insert_calls.append(doc)
        self.docs.append(doc)

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> None:
        self.update_calls.append((query, update))
        doc = await self.find_one(query)
        if doc:
            doc.update(update.get("$set", {}))

    def find(self, query: dict[str, Any]) -> _AsyncCursor:
        return _AsyncCursor([doc for doc in self.docs if _matches(doc, query)])


def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    return all(doc.get(key) == value for key, value in query.items())


def _config_doc(user_id: str = "user-1", *, enabled: bool = True) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "app_id": "cli_a",
        "app_secret": {"encrypted": "secret"},
        "encrypt_key": "",
        "verification_token": "",
        "react_emoji": "THUMBSUP",
        "group_policy": "mention",
        "stream_reply": True,
        "auto_transcribe_audio": True,
        "audio_transcribe_prompt": "transcribe",
        "enabled": enabled,
        "created_at": "2026-04-25T00:00:00Z",
        "updated_at": "2026-04-25T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_get_config_offloads_secret_decryption(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    storage = feishu_storage.FeishuStorage()
    monkeypatch.setattr(storage, "_get_collection", lambda: _FakeCollection([_config_doc()]))

    async def _fake_run_long_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return {"value": "plain-secret"}

    monkeypatch.setattr(
        feishu_storage, "run_long_blocking_io", _fake_run_long_blocking_io, raising=False
    )

    config = await storage.get_config("user-1")

    assert calls == [feishu_storage.decrypt_value]
    assert config is not None
    assert config.app_secret == "plain-secret"


@pytest.mark.asyncio
async def test_create_config_offloads_secret_encryption_and_decryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    collection = _FakeCollection([])
    storage = feishu_storage.FeishuStorage()
    monkeypatch.setattr(storage, "_get_collection", lambda: collection)

    async def _fake_run_long_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        if func is feishu_storage.encrypt_value:
            return {"encrypted": args[0]}
        return {"value": "plain-secret"}

    monkeypatch.setattr(
        feishu_storage, "run_long_blocking_io", _fake_run_long_blocking_io, raising=False
    )

    config = await storage.create_config(
        FeishuConfigCreate(
            app_id="cli_a",
            app_secret="plain-secret",
            group_policy=FeishuGroupPolicy.MENTION,
        ),
        "user-1",
    )

    assert calls == [feishu_storage.encrypt_value, feishu_storage.decrypt_value]
    assert collection.insert_calls[0]["app_secret"] == {"encrypted": {"value": "plain-secret"}}
    assert config.app_secret == "plain-secret"


@pytest.mark.asyncio
async def test_list_enabled_configs_offloads_each_secret_decryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    storage = feishu_storage.FeishuStorage()
    monkeypatch.setattr(
        storage,
        "_get_collection",
        lambda: _FakeCollection([_config_doc("user-1"), _config_doc("user-2")]),
    )

    async def _fake_run_long_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return {"value": f"plain-{len(calls)}"}

    monkeypatch.setattr(
        feishu_storage, "run_long_blocking_io", _fake_run_long_blocking_io, raising=False
    )

    configs = await storage.list_enabled_configs()

    assert calls == [feishu_storage.decrypt_value, feishu_storage.decrypt_value]
    assert [config.app_secret for config in configs] == ["plain-1", "plain-2"]
