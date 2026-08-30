"""usage_logs 历史费用回填测试。"""

import asyncio

import pytest

from src.infra.pricing import backfill as pricing_backfill
from src.infra.pricing import service as pricing_service
from src.infra.pricing.storage import PricingStorage


class _FakeUsageCollection:
    def __init__(self, docs):
        self.docs = {doc["trace_id"]: dict(doc) for doc in docs}
        self.queries = []

    def find(self, query, projection=None, *args, **kwargs):
        self.queries.append(query)
        matched = [d for d in self.docs.values() if self._match(d, query)]
        matched.sort(key=lambda d: d.get("started_at") or "")

        class _Cursor:
            def __init__(self, items):
                self._items = items
                self._skip = 0
                self._limit = None

            def sort(self, *a, **kw):
                return self

            def skip(self, v):
                self._skip = v
                return self

            def limit(self, v):
                self._limit = v
                return self

            async def to_list(self, length=None):
                items = self._items[self._skip : self._limit]
                return [dict(i) for i in items]

        return _Cursor(matched)

    def _match(self, doc, query):
        for key, expected in query.items():
            if key == "cost_available" and isinstance(expected, dict) and "$ne" in expected:
                if doc.get(key) == expected["$ne"]:
                    return False
            elif doc.get(key) != expected:
                return False
        return True

    async def update_one(self, query, update, **kwargs):
        trace_id = query.get("trace_id")
        if trace_id in self.docs:
            self.docs[trace_id].update(update.get("$set", {}))
        import types

        return types.SimpleNamespace(modified_count=1)

    async def count_documents(self, query):
        return sum(1 for d in self.docs.values() if self._match(d, query))


class _FakeUsageStorage:
    def __init__(self, docs):
        self.collection = _FakeUsageCollection(docs)

    async def list_unpriced_usage_logs(self, *, limit=500):
        cursor = self.collection.find({"cost_available": {"$ne": True}})
        return await cursor.to_list(length=limit)

    async def update_usage_cost(self, trace_id, cost_usd):
        await self.collection.update_one(
            {"trace_id": trace_id},
            {"$set": {"cost_usd": cost_usd, "cost_available": True}},
        )
        return True


class _PricingFakeCollection:
    def __init__(self):
        self.docs = {
            "models_dev_snapshot": {
                "entries": [
                    {
                        "provider": "zai",
                        "model_id": "glm-5.3",
                        "name": "GLM 5.3",
                        "rates": {
                            "input": 1.4,
                            "output": 4.4,
                            "cache_read": None,
                            "cache_write": None,
                        },
                    }
                ],
                "entry_count": 1,
                "model_owners": {"glm-5.3": ["zai"]},
                "source_url": "u",
                "synced_at": "2026-08-30T00:00:00",
            }
        }

    async def update_one(self, query, update, **kwargs):
        doc = dict(update.get("$set", {}))
        doc["_id"] = query["_id"]
        self.docs[query["_id"]] = doc
        return None

    async def find_one(self, query, *args, **kwargs):
        doc = self.docs.get(query.get("_id"))
        return None if doc is None else {k: v for k, v in doc.items() if k != "_id"}

    async def create_index(self, *a, **kw):
        return None


def _pricing_storage():
    return PricingStorage(collection=_PricingFakeCollection())


def _logs():
    return [
        {
            "trace_id": "t-priced",
            "model": "glm-5.3",
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "cost_usd": 0.001,
            "cost_available": True,
            "started_at": "2026-08-01T00:00:00",
        },
        {
            "trace_id": "t-open",
            "model": "glm-5.3",
            "input_tokens": 1_000_000,
            "output_tokens": 100_000,
            "total_tokens": 1_100_000,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 200_000,
            "started_at": "2026-08-02T00:00:00",
        },
        {
            "trace_id": "t-unknown",
            "model": "relay/custom-x",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "started_at": "2026-08-03T00:00:00",
        },
        {
            "trace_id": "t-nomodel",
            "model": "",
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "started_at": "2026-08-04T00:00:00",
        },
    ]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(pricing_service, "get_pricing_storage", _pricing_storage)
    pricing_service.reset_runtime_cache()

    async def _acquire(lock_key, ttl):
        return "test-token"

    async def _release(lock_key, token):
        return None

    monkeypatch.setattr(pricing_backfill, "acquire_pricing_lock", _acquire)
    monkeypatch.setattr(pricing_backfill, "release_pricing_lock", _release)
    yield
    pricing_service.reset_runtime_cache()


class TestBackfillUsageCosts:
    def test_prices_unpriced_and_skips_priced(self):
        usage = _FakeUsageStorage(_logs())
        summary = asyncio.run(pricing_backfill.backfill_usage_costs(usage_storage=usage))
        assert summary["scanned"] == 3  # 跳过已计价的 t-priced
        assert summary["priced"] == 1
        assert summary["still_unpriced"] == 2
        doc = usage.collection.docs["t-open"]
        assert doc["cost_available"] is True
        # billable input = 1M - 200k cache_read = 800k
        expected = 800_000 * 1.4 / 1e6 + 100_000 * 4.4 / 1e6
        assert doc["cost_usd"] == pytest.approx(expected)
        # 已计价的不动
        assert usage.collection.docs["t-priced"]["cost_usd"] == 0.001

    def test_unpriced_models_reported_by_model(self):
        usage = _FakeUsageStorage(_logs())
        summary = asyncio.run(pricing_backfill.backfill_usage_costs(usage_storage=usage))
        assert summary["unpriced_models"] == {"relay/custom-x": 1, "": 1}

    def test_dry_run_does_not_write(self):
        usage = _FakeUsageStorage(_logs())
        summary = asyncio.run(
            pricing_backfill.backfill_usage_costs(usage_storage=usage, dry_run=True)
        )
        assert summary["priced"] == 1
        assert "cost_usd" not in usage.collection.docs["t-open"]

    def test_model_config_override_by_value_applies(self, monkeypatch):
        from src.infra.pricing.calculator import PriceRates
        from src.kernel.schemas.model import ModelConfig

        async def _fake_resolve(*, value, provider=None, model_config_id=None):
            if model_config_id == "cfg-1":
                return pricing_service.ResolvedPrice(
                    rates=PriceRates(input=0.5, output=1.0), source="override"
                )
            if value == "glm-5.3":
                return pricing_service.ResolvedPrice(
                    rates=PriceRates(input=1.4, output=4.4), source="models_dev"
                )
            return None

        lookup_values = []

        async def _fake_get_by_value(value):
            lookup_values.append(value)
            if value == "relay/custom-x":
                return ModelConfig(id="cfg-1", value=value, label="Relay")
            return None

        import src.infra.agent.model_storage as model_storage_module

        monkeypatch.setattr(pricing_backfill, "resolve_price", _fake_resolve)
        monkeypatch.setattr(
            model_storage_module,
            "get_model_storage",
            lambda: type("S", (), {"get_by_value": staticmethod(_fake_get_by_value)})(),
        )
        usage = _FakeUsageStorage(_logs())
        summary = asyncio.run(pricing_backfill.backfill_usage_costs(usage_storage=usage))
        assert summary["priced"] == 2  # t-open（快照价）+ t-unknown（覆盖价）
        assert "relay/custom-x" in lookup_values
        doc = usage.collection.docs["t-unknown"]
        assert doc["cost_usd"] == pytest.approx(100 * 0.5 / 1e6 + 50 * 1.0 / 1e6)
