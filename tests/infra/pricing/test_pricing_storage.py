"""PricingStorage 持久化测试：价格快照与汇率文档的读写。"""

import asyncio
from types import SimpleNamespace

from src.infra.pricing.storage import PricingStorage


class _FakeCollection:
    def __init__(self):
        self.docs: dict = {}

    async def update_one(self, query, update, **kwargs):
        doc_id = query["_id"]
        doc = dict(update.get("$set", {}))
        doc["_id"] = doc_id
        self.docs[doc_id] = doc
        return SimpleNamespace(modified_count=1, upserted_id=doc_id)

    async def find_one(self, query, *args, **kwargs):
        doc = self.docs.get(query.get("_id"))
        if doc is None:
            return None
        return {k: v for k, v in doc.items() if k != "_id"}

    async def create_index(self, *args, **kwargs):
        return None


def _make_storage() -> tuple[PricingStorage, _FakeCollection]:
    fake = _FakeCollection()
    return PricingStorage(collection=fake), fake


class TestPriceSnapshot:
    def test_roundtrip(self):
        storage, _ = _make_storage()
        entries = [
            {
                "provider": "openai",
                "model_id": "gpt-4o",
                "name": "GPT-4o",
                "rates": {"input": 2.5, "output": 10, "cache_read": 1.25},
            }
        ]
        asyncio.run(storage.save_price_snapshot(entries, source_url="https://models.dev/api.json"))
        snapshot = asyncio.run(storage.load_price_snapshot())
        assert snapshot is not None
        assert snapshot["entry_count"] == 1
        assert snapshot["entries"] == entries
        assert snapshot["source_url"] == "https://models.dev/api.json"
        assert snapshot["synced_at"] is not None

    def test_missing_snapshot_returns_none(self):
        storage, _ = _make_storage()
        assert asyncio.run(storage.load_price_snapshot()) is None


class TestFxRates:
    def test_roundtrip(self):
        storage, _ = _make_storage()
        rates = {"USD": 1, "CNY": 7.1, "JPY": 150.0}
        asyncio.run(storage.save_fx_rates(rates, base="USD"))
        doc = asyncio.run(storage.load_fx_rates())
        assert doc is not None
        assert doc["base"] == "USD"
        assert doc["rates"] == rates
        assert doc["synced_at"] is not None

    def test_missing_fx_returns_none(self):
        storage, _ = _make_storage()
        assert asyncio.run(storage.load_fx_rates()) is None


class TestStatus:
    def test_status_reports_both_docs(self):
        storage, _ = _make_storage()
        asyncio.run(
            storage.save_price_snapshot(
                [{"provider": "p", "model_id": "m", "name": "", "rates": {}}],
                source_url="u",
            )
        )
        asyncio.run(storage.save_fx_rates({"USD": 1}, base="USD"))
        status = asyncio.run(storage.get_status())
        assert status["prices"]["entry_count"] == 1
        assert status["prices"]["synced_at"] is not None
        assert status["fx"]["base"] == "USD"
        assert status["fx"]["rate_count"] == 1

    def test_status_empty_when_never_synced(self):
        storage, _ = _make_storage()
        status = asyncio.run(storage.get_status())
        assert status["prices"]["entry_count"] == 0
        assert status["prices"]["synced_at"] is None
        assert status["fx"]["synced_at"] is None
