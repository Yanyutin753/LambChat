"""Management writes must keep recall indexes consistent with Mongo facts."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import memory as routes
from src.kernel.schemas.user import TokenPayload


class Collection:
    def __init__(self):
        self.doc = {
            "user_id": "owner",
            "memory_id": "memory-1",
            "title": "Answer preference",
            "summary": "Prefers concise answers",
            "content": "The user prefers concise answers.",
            "index_label": "Answer preference: Prefers concise answers",
            "content_storage_mode": "inline",
            "content_store_key": None,
            "embedding": [1.0, 0.0],
            "memory_type": "user",
            "context": "user",
            "scope": "user",
            "project_id": None,
            "source_refs": [],
            "updated_at": datetime.now(timezone.utc),
        }

    async def find_one(self, query, projection):
        assert query == {"user_id": "owner", "memory_id": "memory-1"}
        return {key: deepcopy(value) for key, value in self.doc.items() if projection.get(key)}

    async def insert_one(self, doc):
        self.doc = deepcopy(doc)

    async def update_one(self, query, update):
        assert query == {"user_id": "owner", "memory_id": "memory-1"}
        fields = (
            {
                key: value["$literal"]
                for key, value in update[0]["$set"].items()
                if key != "_content_cleanup"
            }
            if isinstance(update, list)
            else update["$set"]
        )
        self.doc.update(deepcopy(fields))
        return SimpleNamespace(matched_count=1)

    async def find_one_and_update(self, query, pipeline, **kwargs):
        doc = pipeline[0]["$replaceWith"]["$mergeObjects"][0]["$literal"]
        doc = dict(
            doc,
            origin_session_ids=list(
                dict.fromkeys([*self.doc.get("origin_session_ids", []), *doc["origin_session_ids"]])
            ),
        )
        previous = self.doc
        self.doc = deepcopy(doc)
        return previous


@pytest.fixture
def backend(monkeypatch):
    value = SimpleNamespace(
        _collection=Collection(),
        _store=None,
        _maybe_embed=AsyncMock(return_value=[0.0, 1.0]),
        _invalidate_cache=AsyncMock(),
    )
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=value))
    return value


async def test_editing_tags_preserves_navigation_label_without_reembedding(backend):
    await routes.update_memory(
        "memory-1",
        {"tags": ["answer-style"]},
        user=TokenPayload(sub="owner", username="tester", roles=["user"]),
    )

    assert "concise" in backend._collection.doc["index_label"].lower()
    backend._maybe_embed.assert_not_awaited()


async def test_failed_reembedding_does_not_reuse_the_previous_body_vector(monkeypatch, backend):
    backend._maybe_embed.return_value = None
    index = AsyncMock(return_value=True)
    monkeypatch.setattr("src.infra.memory.client.native.vector_store.index_write_through", index)

    await routes.update_memory(
        "memory-1",
        {"content": "The user now prefers detailed answers."},
        user=TokenPayload(sub="owner", username="tester", roles=["user"]),
    )

    assert backend._collection.doc["embedding"] is None
    assert index.await_args.kwargs["embedding"] is None


@pytest.mark.parametrize("row_exists", [True, False])
async def test_long_body_edit_stages_a_new_key_and_cleans_only_uncommitted_content(
    monkeypatch, backend, row_exists
):
    from src.kernel.errors import AppError

    monkeypatch.setattr(routes.settings, "NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS", 5)
    old_key = "memory:memory-1"

    class Store:
        def __init__(self):
            self.values = {old_key: {"text": "Original durable text."}}

        async def aput(self, namespace, key, value):
            if value is None:
                self.values.pop(key, None)
            else:
                self.values[key] = value

    backend._store = Store()
    backend._collection.doc.update(content_storage_mode="store", content_store_key=old_key)
    if not row_exists:
        backend._collection.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=0))
    user = TokenPayload(sub="owner", username="tester", roles=["user"])
    if row_exists:
        await routes.update_memory("memory-1", {"content": "Replacement durable text."}, user=user)
        new_key = backend._collection.doc["content_store_key"]
        assert new_key != old_key
        assert backend._store.values[new_key]["text"] == "Replacement durable text."
    else:
        with pytest.raises(AppError) as error:
            await routes.update_memory(
                "memory-1", {"content": "Replacement durable text."}, user=user
            )
        assert error.value.error_code.code == "memory_not_found"
        assert backend._store.values == {old_key: {"text": "Original durable text."}}
        backend._invalidate_cache.assert_not_awaited()


@pytest.mark.parametrize("operation", ["create", "update", "import"])
async def test_management_content_writes_update_vector_recall_index(
    monkeypatch, backend, operation
):
    index = AsyncMock(return_value=True)
    monkeypatch.setattr("src.infra.memory.client.native.vector_store.index_write_through", index)
    user = TokenPayload(sub="owner", username="tester", roles=["user"])
    payload = {"content": "The user prefers detailed answers.", "title": "Answer preference"}
    if operation == "create":
        await routes.create_memory(payload, user=user)
    elif operation == "update":
        await routes.update_memory("memory-1", payload, user=user)
    else:
        await routes.import_memories({"memories": [payload]}, user=user)

    index.assert_awaited_once()
    call = index.await_args.kwargs
    assert call["user_id"] == "owner"
    assert call["memory_id"] == backend._collection.doc["memory_id"]
    assert call["embedding"] == [0.0, 1.0]
    assert call["memory_type"] == "user"


async def test_memory_detail_reads_full_body_from_the_owned_store_namespace(monkeypatch, backend):
    body = "Long supplier handbook. " * 250 + "Warranty: 53 months."
    backend._collection.doc.update(
        content="Short preview", content_storage_mode="store", content_store_key="body-key"
    )

    class Store:
        async def aget(self, namespace, key):
            assert namespace[-2:] == ("owner", "content")
            assert key == "body-key"
            return {"text": body}

    backend._store = Store()
    monkeypatch.setattr(routes, "_validated_source_ref_docs", AsyncMock(return_value=[]))
    result = await routes.get_memory(
        "memory-1",
        user=TokenPayload(sub="owner", username="tester", roles=["user"]),
    )
    assert result["content"] == body


async def test_memory_detail_does_not_offer_a_preview_as_editable_full_content(
    monkeypatch, backend
):
    from src.kernel.errors import AppError

    backend._collection.doc.update(
        content="Short preview",
        content_storage_mode="store",
        content_store_key="temporarily-unavailable",
    )
    backend._store = SimpleNamespace(aget=AsyncMock(return_value=None))
    monkeypatch.setattr(routes, "_validated_source_ref_docs", AsyncMock(return_value=[]))
    with pytest.raises(AppError) as error:
        await routes.get_memory(
            "memory-1",
            user=TokenPayload(sub="owner", username="tester", roles=["user"]),
        )
    assert error.value.error_code.code == "memory_backend_unavailable"
