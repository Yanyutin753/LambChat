from types import SimpleNamespace

import pytest
from langgraph.store.base import GetOp, PutOp

from src.infra.storage import mongodb_store


class Collection:
    def __init__(self, docs):
        self.docs = docs
        self.find_queries = []
        self.point_queries = []

    def matching(self, query):
        clauses = query.get("$or", [query])
        return [
            doc
            for doc in self.docs
            if any(
                doc["namespace"] == clause["namespace"] and doc["key"] == clause["key"]
                for clause in clauses
            )
        ]

    def find(self, query):
        self.find_queries.append(query)
        return Cursor(self.matching(query))

    async def find_one(self, query):
        self.point_queries.append(query)
        docs = self.matching(query)
        return docs[0] if docs else None

    async def update_one(self, query, update, *, upsert):
        self.docs.append({**query, **update["$set"]})


class SyncCollection(Collection):
    def find_one(self, query):
        self.point_queries.append(query)
        docs = self.matching(query)
        return docs[0] if docs else None

    def update_one(self, query, update, *, upsert):
        self.docs.append({**query, **update["$set"]})


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def __iter__(self):
        return iter(self.docs)

    async def __aiter__(self):
        for doc in self.docs:
            yield doc


def docs(count, namespace=("memory", "owner")):
    return [
        {"namespace": list(namespace), "key": str(index), "value": {"text": f"full-{index}"}}
        for index in range(count)
    ]


@pytest.mark.parametrize("count", [1, 50])
@pytest.mark.parametrize("synchronous", [False, True])
async def test_get_only_store_batch_reads_once_and_preserves_protocol(
    monkeypatch, count, synchronous
):
    ns = ("memory", "owner")
    other = ("memory", "other")
    collection = (SyncCollection if synchronous else Collection)(docs(count) + docs(1, other))
    store = mongodb_store.MongoDBStore()
    store._collection = collection
    monkeypatch.setattr(mongodb_store.MongoDBStore, "_sync_collection", lambda self: collection)
    ops = [GetOp(ns, str(index)) for index in range(count)] + [
        GetOp(other, "0"),
        GetOp(ns, "absent"),
        GetOp(ns, "0"),
    ]

    results = store.batch(iter(ops)) if synchronous else await store.abatch(iter(ops))

    assert len(collection.find_queries) == 1
    assert collection.point_queries == []
    assert len(results) == len(ops)
    assert [item.key for item in results[:count]] == [str(index) for index in range(count)]
    assert all(item.namespace == ns for item in results[:count])
    assert results[count].namespace == other
    assert results[count + 1] is None
    assert results[-1].value == results[0].value


@pytest.mark.parametrize("synchronous", [False, True])
async def test_mixed_store_batch_keeps_existing_operation_path(monkeypatch, synchronous):
    monkeypatch.setattr(
        mongodb_store,
        "settings",
        SimpleNamespace(MONGODB_DB="test", MONGODB_STORE_BATCH_CONCURRENCY=1),
    )
    collection = (SyncCollection if synchronous else Collection)([])
    store = mongodb_store.MongoDBStore()
    store._collection = collection
    monkeypatch.setattr(mongodb_store.MongoDBStore, "_sync_collection", lambda self: collection)
    ops = [PutOp(("owner",), "key", {"text": "saved"}), GetOp(("owner",), "key")]
    result = store.batch(ops) if synchronous else await store.abatch(ops)
    assert result[0] is None
    assert result[1].value == {"text": "saved"}
    assert len(collection.point_queries) == 1
    assert collection.find_queries == []


async def test_get_batch_failure_propagates_without_partial_results():
    collection = Collection([])

    def fail(query):
        raise RuntimeError("store unavailable")

    collection.find = fail
    store = mongodb_store.MongoDBStore()
    store._collection = collection
    with pytest.raises(RuntimeError, match="store unavailable"):
        await store.abatch([GetOp(("owner",), "key")])
