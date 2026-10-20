"""Older semantic facts must survive a busy user's recent memory volume."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.memory.client.native import search, vector_store
from src.infra.utils.datetime import utc_now


@pytest.mark.parametrize("query,expected", [([1.0, 0.0], [(1.0, "valid")]), ([0.0, 0.0], [])])
def test_bad_stored_vectors_do_not_poison_a_scoring_batch(query, expected):
    docs = [
        {"memory_id": "valid", "embedding": [1.0, 0.0]},
        {"memory_id": "broken", "embedding": ["not-a-number", 0]},
        {"memory_id": "wrong-dimensions", "embedding": [1.0]},
        {"memory_id": "zero", "embedding": [0.0, 0.0]},
        {"memory_id": "nonfinite", "embedding": [float("nan"), 1.0]},
    ]
    assert search._score_vector_batch(docs, query) == expected


async def test_mongo_fallback_finds_half_year_old_fact_behind_recent_noise(monkeypatch):
    now = utc_now()

    def memory(mid, embedding, age):
        return {
            "memory_id": mid,
            "user_id": "owner",
            "content": f"Durable fact {mid}.",
            "title": mid,
            "summary": mid,
            "tags": [],
            "memory_type": "user",
            "context": "user",
            "source": "auto_retained",
            "scope": "user",
            "created_at": now - timedelta(days=age),
            "updated_at": now - timedelta(days=age),
            "embedding": embedding,
        }

    docs = [memory(f"recent-{index}", [0.0, 1.0], 1) for index in range(1200)]
    docs.append(memory("six-month-anchor", [1.0, 0.0], 180))

    class Cursor:
        def __init__(self, values):
            self.values = values

        def sort(self, *_args, **_kwargs):
            self.values.sort(key=lambda doc: doc["updated_at"], reverse=True)
            return self

        def limit(self, count):
            self.values = self.values[:count]
            return self

        def batch_size(self, count):
            return self

        async def to_list(self, length=None):
            return self.values if length is None else self.values[:length]

        def __aiter__(self):
            async def iterate():
                for doc in self.values:
                    yield doc

            return iterate()

    class Collection:
        async def aggregate(self, pipeline):
            raise RuntimeError("No native vector index in this fallback configuration")

        def find(self, query, projection=None):
            assert query["user_id"] == "owner"
            wanted = query.get("memory_id", {}).get("$in")
            return Cursor(
                [dict(doc) for doc in docs if wanted is None or doc["memory_id"] in wanted]
            )

    monkeypatch.setattr(vector_store, "index_search", AsyncMock(return_value=None))
    backend = SimpleNamespace(
        _maybe_embed=AsyncMock(return_value=[1.0, 0.0]),
        _collection=Collection(),
        _logger=SimpleNamespace(debug=lambda *_args: None),
    )

    recalled = await search.vector_search(
        backend, "owner", "a semantically related request", 5, None
    )

    assert recalled[0]["memory_id"] == "six-month-anchor"
    assert len(recalled) <= 5
