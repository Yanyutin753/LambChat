from __future__ import annotations

from typing import Any

import pytest

from src.infra.agent import model_storage
from src.infra.agent.model_storage import ModelStorage


class _FakeModelCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = [dict(doc) for doc in docs]
        self._index = 0

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return dict(doc)


class _FakeModelCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.bulk_sizes: list[int] = []

    def find(self, query: dict):
        assert query == {"api_key": {"$ne": None}}
        return _FakeModelCursor(self.docs)

    async def bulk_write(self, operations: list[Any]):
        self.bulk_sizes.append(len(operations))

        class _Result:
            modified_count = len(operations)

        return _Result()


class _EmptyAsyncCursor:
    def __init__(self) -> None:
        self.sort_calls: list[tuple[str, int]] = []
        self.limit_calls: list[int] = []

    def sort(self, key: str, direction: int):
        self.sort_calls.append((key, direction))
        return self

    def limit(self, value: int):
        self.limit_calls.append(value)
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _RecordingModelCollection:
    def __init__(self) -> None:
        self.queries: list[dict[str, Any]] = []
        self.cursor = _EmptyAsyncCursor()

    def find(self, query: dict):
        self.queries.append(query)
        return self.cursor


class _BulkWriteRecordingCollection:
    def __init__(self) -> None:
        self.bulk_sizes: list[int] = []
        self.bulk_operations: list[Any] = []
        self.find_queries: list[dict[str, Any]] = []
        self.cursor = _EmptyAsyncCursor()

    async def bulk_write(self, operations: list[Any]):
        self.bulk_operations.extend(operations)
        self.bulk_sizes.append(len(operations))

        class _Result:
            modified_count = len(operations)

        return _Result()

    def find(self, query: dict[str, Any]):
        self.find_queries.append(query)
        return self.cursor


class _CrudModelCollection:
    def __init__(self, doc: dict[str, Any] | None = None) -> None:
        self.doc = dict(doc) if doc else None
        self.inserted_docs: list[dict[str, Any]] = []
        self.find_one_queries: list[dict[str, Any]] = []
        self.updated_queries: list[dict[str, Any]] = []

    async def find_one(self, query: dict[str, Any], **_kwargs):
        self.find_one_queries.append(query)
        if self.doc and all(self.doc.get(key) == value for key, value in query.items()):
            return dict(self.doc)
        return None

    async def insert_one(self, doc: dict[str, Any]):
        self.inserted_docs.append(dict(doc))

    async def find_one_and_update(self, query: dict[str, Any], *_args, **_kwargs):
        self.updated_queries.append(query)
        if self.doc and all(self.doc.get(key) == value for key, value in query.items()):
            return dict(self.doc)
        return None


def _model_doc() -> dict[str, Any]:
    return {
        "id": "model-1",
        "value": "openai/gpt-4.1",
        "label": "GPT 4.1",
        "api_key": {"encrypted": "secret"},
        "enabled": True,
        "order": 0,
    }


@pytest.mark.asyncio
async def test_migrate_plaintext_keys_flushes_in_bounded_batches() -> None:
    storage = ModelStorage()
    collection = _FakeModelCollection(
        [{"id": f"model-{index}", "api_key": f"plain-{index}"} for index in range(250)]
    )
    storage._collection = collection

    modified = await storage.migrate_plaintext_keys()

    assert modified == 250
    assert len(collection.bulk_sizes) > 1
    assert max(collection.bulk_sizes) <= 100


@pytest.mark.asyncio
async def test_get_offloads_api_key_decryption(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    storage = ModelStorage()
    storage._collection = _CrudModelCollection(_model_doc())

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return {"v": "plain-key"}

    monkeypatch.setattr(model_storage, "run_blocking_io", fake_run_blocking_io, raising=False)

    model = await storage.get("model-1")

    assert calls == [model_storage.decrypt_value]
    assert model is not None
    assert model.api_key == "plain-key"


@pytest.mark.asyncio
async def test_create_offloads_api_key_encryption_and_decryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    storage = ModelStorage()
    collection = _CrudModelCollection()
    storage._collection = collection

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        if func is model_storage.encrypt_value:
            return {"encrypted": args[0]}
        return {"v": "plain-key"}

    monkeypatch.setattr(model_storage, "run_blocking_io", fake_run_blocking_io, raising=False)

    model = await storage.create(
        model_storage.ModelConfig(
            id="model-1",
            value="openai/gpt-4.1",
            label="GPT 4.1",
            api_key="plain-key",
        )
    )

    assert calls == [model_storage.encrypt_value, model_storage.decrypt_value]
    assert collection.inserted_docs[0]["api_key"] == {"encrypted": {"v": "plain-key"}}
    assert model.api_key == "plain-key"


@pytest.mark.asyncio
async def test_list_enabled_by_ids_or_values_caps_mongo_in_query() -> None:
    storage = ModelStorage()
    collection = _RecordingModelCollection()
    storage._collection = collection

    values = [f"model-{index}" for index in range(model_storage.MODEL_RESTRICTED_LIST_LIMIT + 25)]

    result = await storage.list_enabled_by_ids_or_values(values)

    assert result == []
    query = collection.queries[0]
    assert query["enabled"] is True
    assert len(query["$or"][0]["id"]["$in"]) == model_storage.MODEL_RESTRICTED_LIST_LIMIT
    assert len(query["$or"][1]["value"]["$in"]) == model_storage.MODEL_RESTRICTED_LIST_LIMIT
    assert collection.cursor.sort_calls == [("order", 1)]
    assert collection.cursor.limit_calls == [model_storage.MODEL_RESTRICTED_LIST_LIMIT]


@pytest.mark.asyncio
async def test_list_models_applies_default_query_limit() -> None:
    storage = ModelStorage()
    collection = _RecordingModelCollection()
    storage._collection = collection

    result = await storage.list_models(include_disabled=False)

    assert result == []
    assert collection.queries == [{"enabled": True}]
    assert collection.cursor.sort_calls == [("order", 1)]
    assert collection.cursor.limit_calls == [model_storage.MODEL_LIST_LIMIT]


@pytest.mark.asyncio
async def test_reorder_flushes_updates_in_bounded_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_storage, "MODEL_BULK_WRITE_BATCH_SIZE", 100, raising=False)
    storage = ModelStorage()
    collection = _BulkWriteRecordingCollection()
    storage._collection = collection

    await storage.reorder([f"model-{index}" for index in range(250)])

    assert collection.bulk_sizes == [100, 100, 50]


@pytest.mark.asyncio
async def test_bulk_upsert_by_value_flushes_and_reads_back_in_bounded_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_storage, "MODEL_BULK_WRITE_BATCH_SIZE", 100, raising=False)
    monkeypatch.setattr(model_storage, "MODEL_RESTRICTED_LIST_LIMIT", 100, raising=False)
    storage = ModelStorage()
    collection = _BulkWriteRecordingCollection()
    storage._collection = collection
    models = [
        model_storage.ModelConfig(
            value=f"provider/model-{index}",
            label=f"Model {index}",
        )
        for index in range(250)
    ]

    await storage.bulk_upsert_by_value(models)

    assert collection.bulk_sizes == [100, 100, 50]
    assert [len(query["$or"]) for query in collection.find_queries] == [100, 100, 50]


@pytest.mark.asyncio
async def test_bulk_upsert_by_value_scopes_identity_to_provider_and_api_base() -> None:
    storage = ModelStorage()
    collection = _BulkWriteRecordingCollection()
    storage._collection = collection

    await storage.bulk_upsert_by_value(
        [
            model_storage.ModelConfig(
                value="gpt-4o-mini",
                provider="openai",
                api_base="https://api.openai.com/v1",
                label="OpenAI GPT-4o mini",
            ),
            model_storage.ModelConfig(
                value="gpt-4o-mini",
                provider="azure",
                api_base="https://example.openai.azure.com",
                label="Azure GPT-4o mini",
            ),
        ]
    )

    filters = [operation._filter for operation in collection.bulk_operations]
    assert filters == [
        {
            "value": "gpt-4o-mini",
            "provider": "openai",
            "api_base": "https://api.openai.com/v1",
        },
        {
            "value": "gpt-4o-mini",
            "provider": "azure",
            "api_base": "https://example.openai.azure.com",
        },
    ]
    assert collection.find_queries == [
        {
            "$or": [
                {
                    "value": "gpt-4o-mini",
                    "provider": "openai",
                    "api_base": "https://api.openai.com/v1",
                },
                {
                    "value": "gpt-4o-mini",
                    "provider": "azure",
                    "api_base": "https://example.openai.azure.com",
                },
            ]
        }
    ]


@pytest.mark.asyncio
async def test_upsert_by_value_does_not_overwrite_different_provider() -> None:
    storage = ModelStorage()
    collection = _CrudModelCollection(
        {
            "id": "openai-model",
            "value": "gpt-4o-mini",
            "provider": "openai",
            "api_base": "https://api.openai.com/v1",
            "label": "OpenAI GPT-4o mini",
            "enabled": True,
            "order": 0,
        }
    )
    storage._collection = collection

    model, created = await storage.upsert_by_value(
        model_storage.ModelConfig(
            value="gpt-4o-mini",
            provider="azure",
            api_base="https://example.openai.azure.com",
            label="Azure GPT-4o mini",
        )
    )

    assert created is True
    assert model.provider == "azure"
    assert collection.find_one_queries == [
        {
            "value": "gpt-4o-mini",
            "provider": "azure",
            "api_base": "https://example.openai.azure.com",
        }
    ]
    assert collection.updated_queries == []
    assert collection.inserted_docs[0]["provider"] == "azure"


class _ExistsCollection:
    """Fake collection recording count_documents calls (for exists checks)."""

    def __init__(self, count: int) -> None:
        self.count = count
        self.count_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def count_documents(self, query: dict[str, Any], **kwargs):
        self.count_calls.append((query, kwargs))
        return self.count


@pytest.mark.asyncio
async def test_exists_uses_count_documents_with_limit_and_avoids_loading_doc() -> None:
    storage = ModelStorage()

    # 存在：count=1 → True，用 count_documents(limit=1)，不读取整文档（含加密 api_key）
    present = _ExistsCollection(count=1)
    storage._collection = present
    assert await storage.exists("openai/gpt-4.1") is True
    query, kwargs = present.count_calls[0]
    assert query == {"value": "openai/gpt-4.1"}
    assert kwargs.get("limit") == 1

    # 不存在：count=0 → False
    absent = _ExistsCollection(count=0)
    storage._collection = absent
    assert await storage.exists("missing/model") is False
