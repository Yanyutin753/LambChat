"""pricing service 测试：价格解析（覆盖 > models.dev 匹配）与成本计算入口。"""

import asyncio

import pytest

from src.infra.pricing import service as pricing_service
from src.infra.pricing.calculator import PriceRates
from src.infra.pricing.storage import PricingStorage


def _async_return(value):
    async def _wrapper(_model_config_id):
        return value

    return _wrapper


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


def _storage_with_snapshot() -> PricingStorage:
    storage = PricingStorage(collection=_FakeCollection())
    asyncio.run(
        storage.save_price_snapshot(
            [
                {
                    "provider": "openai",
                    "model_id": "gpt-4o",
                    "name": "GPT-4o",
                    "rates": {
                        "input": 2.5,
                        "output": 10,
                        "cache_read": 1.25,
                        "cache_write": None,
                    },
                }
            ],
            source_url="u",
        )
    )
    asyncio.run(storage.save_fx_rates({"USD": 1, "CNY": 7.1}, base="USD"))
    return storage


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    storage = _storage_with_snapshot()
    monkeypatch.setattr(pricing_service, "get_pricing_storage", lambda: storage)
    pricing_service.reset_runtime_cache()
    yield
    pricing_service.reset_runtime_cache()


class TestResolvePrice:
    def test_matches_models_dev_snapshot(self):
        resolved = asyncio.run(pricing_service.resolve_price(value="gpt-4o"))
        assert resolved is not None
        assert resolved.source == "models_dev"
        assert resolved.rates.input == 2.5
        assert resolved.matched_provider == "openai"
        assert resolved.matched_model_id == "gpt-4o"

    def test_unknown_model_returns_none(self):
        assert asyncio.run(pricing_service.resolve_price(value="nope")) is None

    def test_model_config_override_wins(self, monkeypatch):
        monkeypatch.setattr(
            pricing_service,
            "_load_model_override",
            _async_return(PriceRates(input=1.0, output=2.0)),
        )
        resolved = asyncio.run(
            pricing_service.resolve_price(value="gpt-4o", model_config_id="model-uuid-1")
        )
        assert resolved is not None
        assert resolved.source == "override"
        assert resolved.rates.input == 1.0

    def test_partial_override_merges_over_matched_base(self, monkeypatch):
        monkeypatch.setattr(
            pricing_service,
            "_load_model_override",
            _async_return(PriceRates(input=9.0)),
        )
        resolved = asyncio.run(pricing_service.resolve_price(value="gpt-4o", model_config_id="m1"))
        assert resolved is not None
        assert resolved.source == "override"
        # 未覆盖的字段沿用 models.dev 匹配值
        assert resolved.rates.input == 9.0
        assert resolved.rates.output == 10
        assert resolved.rates.cache_read == 1.25

    def test_override_without_match_uses_override_only(self, monkeypatch):
        monkeypatch.setattr(
            pricing_service,
            "_load_model_override",
            _async_return(PriceRates(input=1.0, output=2.0)),
        )
        resolved = asyncio.run(
            pricing_service.resolve_price(value="relay/custom-model", model_config_id="m1")
        )
        assert resolved is not None
        assert resolved.source == "override"
        assert resolved.rates.input == 1.0

    def test_partial_override_without_match_is_unpriced(self, monkeypatch):
        monkeypatch.setattr(
            pricing_service,
            "_load_model_override",
            _async_return(PriceRates(input=1.0)),
        )
        resolved = asyncio.run(
            pricing_service.resolve_price(value="relay/custom", model_config_id="m1")
        )
        # 只覆盖 input、无匹配基准 → 无法计价
        assert resolved is None or not resolved.rates.is_priced()


class TestGetFxRates:
    def test_loads_from_storage(self):
        doc = asyncio.run(pricing_service.get_fx_rates())
        assert doc is not None
        assert doc["base"] == "USD"
        assert doc["rates"]["CNY"] == 7.1

    def test_missing_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            pricing_service,
            "get_pricing_storage",
            lambda: PricingStorage(collection=_FakeCollection()),
        )
        pricing_service.reset_runtime_cache()
        assert asyncio.run(pricing_service.get_fx_rates()) is None


class TestComputeUsageCost:
    def test_end_to_end(self):
        result = asyncio.run(
            pricing_service.compute_usage_cost(
                model_value="gpt-4o",
                input_tokens=1_000_000,
                output_tokens=100_000,
                cache_read_tokens=200_000,
            )
        )
        assert result is not None
        breakdown, rates, source = result
        assert source == "models_dev"
        assert rates.input == 2.5
        assert breakdown.input_usd == 800_000 * 2.5 / 1_000_000
        assert breakdown.cache_read_usd == 200_000 * 1.25 / 1_000_000
        assert breakdown.output_usd == 100_000 * 10 / 1_000_000

    def test_unmatched_model_returns_none(self):
        assert (
            asyncio.run(
                pricing_service.compute_usage_cost(
                    model_value="unknown",
                    input_tokens=100,
                    output_tokens=100,
                )
            )
            is None
        )
