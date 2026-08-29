"""pricing 同步测试：models.dev / 汇率拉取、解析、TTL 与失败降级。"""

import asyncio

import httpx
import pytest

from src.infra.pricing import sync as pricing_sync
from src.infra.pricing.storage import PricingStorage

MODELS_DEV_PAYLOAD = {
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "models": {
            "gpt-4o": {"name": "GPT-4o", "cost": {"input": 2.5, "output": 10}},
        },
    }
}

FX_PAYLOAD = {
    "result": "success",
    "base_code": "USD",
    "time_last_update_unix": 1787961751,
    "rates": {"USD": 1, "CNY": 7.1, "JPY": 150.0},
}


class _FakeCollection:
    def __init__(self):
        self.docs: dict = {}

    async def update_one(self, query, update, **kwargs):
        doc = dict(update.get("$set", {}))
        doc["_id"] = query["_id"]
        self.docs[query["_id"]] = doc
        return None

    async def find_one(self, query, *args, **kwargs):
        doc = self.docs.get(query.get("_id"))
        if doc is None:
            return None
        return {k: v for k, v in doc.items() if k != "_id"}

    async def create_index(self, *args, **kwargs):
        return None


def _http_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestFetchModelsDev:
    def test_returns_snapshot_entries(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://models.dev/api.json"
            return httpx.Response(200, json=MODELS_DEV_PAYLOAD)

        async def run():
            async with _http_client(handler) as client:
                return await pricing_sync.fetch_models_dev(client)

        entries = asyncio.run(run())
        assert entries == [
            {
                "provider": "openai",
                "model_id": "gpt-4o",
                "name": "GPT-4o",
                "rates": {"input": 2.5, "output": 10, "cache_read": None, "cache_write": None},
            }
        ]

    def test_non_200_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="unavailable")

        async def run():
            async with _http_client(handler) as client:
                return await pricing_sync.fetch_models_dev(client)

        with pytest.raises(Exception):
            asyncio.run(run())


class TestParseFxPayload:
    def test_success_payload(self):
        doc = pricing_sync.parse_fx_payload(FX_PAYLOAD)
        assert doc is not None
        assert doc["base"] == "USD"
        assert doc["rates"] == {"USD": 1, "CNY": 7.1, "JPY": 150.0}
        assert doc["source_updated_at"] == 1787961751

    def test_failure_payload_returns_none(self):
        assert pricing_sync.parse_fx_payload({"result": "error"}) is None

    def test_missing_rates_returns_none(self):
        assert pricing_sync.parse_fx_payload({"result": "success"}) is None


class TestSyncPricing:
    def _storage(self) -> PricingStorage:
        return PricingStorage(collection=_FakeCollection())

    def test_first_sync_fetches_and_persists(self, monkeypatch):
        monkeypatch.setattr(pricing_sync, "get_pricing_storage", self._storage)

        def handler(request: httpx.Request) -> httpx.Response:
            if "models.dev" in str(request.url):
                return httpx.Response(200, json=MODELS_DEV_PAYLOAD)
            return httpx.Response(200, json=FX_PAYLOAD)

        monkeypatch.setattr(pricing_sync, "_build_http_client", lambda: _http_client(handler))
        status = asyncio.run(pricing_sync.sync_pricing())
        assert status["prices"]["entry_count"] == 1
        assert status["fx"]["rate_count"] == 3
        assert status["refreshed"] is True
        assert status["error"] is None

    def test_fresh_snapshot_skips_fetch(self, monkeypatch):
        storage = self._storage()
        monkeypatch.setattr(pricing_sync, "get_pricing_storage", lambda: storage)

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("should not fetch when snapshot is fresh")

        asyncio.run(
            storage.save_price_snapshot(
                [{"provider": "p", "model_id": "m", "name": "", "rates": {}}],
                source_url="u",
            )
        )
        asyncio.run(storage.save_fx_rates({"USD": 1}, base="USD"))
        monkeypatch.setattr(pricing_sync, "_build_http_client", lambda: _http_client(handler))
        status = asyncio.run(pricing_sync.sync_pricing())
        assert status["refreshed"] is False

    def test_force_refetches_even_when_fresh(self, monkeypatch):
        storage = self._storage()
        monkeypatch.setattr(pricing_sync, "get_pricing_storage", lambda: storage)

        def handler(request: httpx.Request) -> httpx.Response:
            if "models.dev" in str(request.url):
                return httpx.Response(200, json=MODELS_DEV_PAYLOAD)
            return httpx.Response(200, json=FX_PAYLOAD)

        asyncio.run(storage.save_fx_rates({"USD": 1}, base="USD"))
        monkeypatch.setattr(pricing_sync, "_build_http_client", lambda: _http_client(handler))
        status = asyncio.run(pricing_sync.sync_pricing(force=True))
        assert status["refreshed"] is True
        assert status["prices"]["entry_count"] == 1

    def test_fetch_failure_keeps_old_snapshot(self, monkeypatch):
        storage = self._storage()
        monkeypatch.setattr(pricing_sync, "get_pricing_storage", lambda: storage)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        asyncio.run(
            storage.save_price_snapshot(
                [{"provider": "p", "model_id": "old", "name": "", "rates": {}}],
                source_url="u",
            )
        )
        monkeypatch.setattr(pricing_sync, "_build_http_client", lambda: _http_client(handler))
        status = asyncio.run(pricing_sync.sync_pricing(force=True))
        assert status["error"] is not None
        # 旧快照仍在
        snapshot = asyncio.run(storage.load_price_snapshot())
        assert snapshot is not None
        assert snapshot["entries"][0]["model_id"] == "old"

    def test_models_dev_and_fx_failures_are_independent(self, monkeypatch):
        storage = self._storage()
        monkeypatch.setattr(pricing_sync, "get_pricing_storage", lambda: storage)

        def handler(request: httpx.Request) -> httpx.Response:
            if "models.dev" in str(request.url):
                return httpx.Response(500, text="down")
            return httpx.Response(200, json=FX_PAYLOAD)

        monkeypatch.setattr(pricing_sync, "_build_http_client", lambda: _http_client(handler))
        status = asyncio.run(pricing_sync.sync_pricing(force=True))
        # FX 成功、价格失败：状态里两者独立呈现
        assert status["fx"]["rate_count"] == 3
        assert status["prices"]["entry_count"] == 0
