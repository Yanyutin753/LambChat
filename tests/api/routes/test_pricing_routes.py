"""pricing 路由测试：汇率查询、手动同步、状态、模型价格查询。"""

import pytest

from src.api.routes import pricing as pricing_routes
from src.kernel.schemas.user import TokenPayload


def _admin() -> TokenPayload:
    return TokenPayload(sub="admin-1", username="Admin", permissions=["model:admin"])


def _user() -> TokenPayload:
    return TokenPayload(sub="user-1", username="User", permissions=["chat:create"])


@pytest.mark.asyncio
async def test_get_rates_returns_fx_doc(monkeypatch):
    async def _fake_fx():
        return {
            "base": "USD",
            "rates": {"USD": 1, "CNY": 7.1},
            "synced_at": "2026-08-30T00:00:00+00:00",
        }

    monkeypatch.setattr(pricing_routes.pricing_service, "get_fx_rates", _fake_fx)
    response = await pricing_routes.get_fx_rates(user=_user())
    assert response.base == "USD"
    assert response.rates["CNY"] == 7.1
    assert response.synced_at is not None


@pytest.mark.asyncio
async def test_get_rates_falls_back_to_empty_when_never_synced(monkeypatch):
    async def _fake_fx():
        return None

    monkeypatch.setattr(pricing_routes.pricing_service, "get_fx_rates", _fake_fx)
    response = await pricing_routes.get_fx_rates(user=_user())
    assert response.base == "USD"
    assert response.rates == {}
    assert response.synced_at is None


@pytest.mark.asyncio
async def test_sync_returns_status_and_resets_cache(monkeypatch):
    calls = {}

    async def _fake_sync(**kwargs):
        calls.update(kwargs)
        return {
            "prices": {
                "entry_count": 4,
                "source_url": "u",
                "synced_at": "2026-08-30T00:00:00+00:00",
            },
            "fx": {"base": "USD", "rate_count": 3, "synced_at": "2026-08-30T00:00:00+00:00"},
            "refreshed": True,
            "error": None,
        }

    reset_calls = []
    monkeypatch.setattr(pricing_routes, "sync_pricing", _fake_sync)
    monkeypatch.setattr(
        pricing_routes.pricing_service, "reset_runtime_cache", lambda: reset_calls.append(True)
    )
    response = await pricing_routes.sync_pricing_prices(user=_admin())
    assert calls == {"force": True}
    assert response.prices.entry_count == 4
    assert response.fx.rate_count == 3
    assert response.refreshed is True
    assert response.error is None
    assert reset_calls == [True]


@pytest.mark.asyncio
async def test_status_returns_storage_status(monkeypatch):
    class _FakeStorage:
        async def get_status(self):
            return {
                "prices": {"entry_count": 0, "source_url": "", "synced_at": None},
                "fx": {"base": "USD", "rate_count": 0, "synced_at": None},
            }

    monkeypatch.setattr(pricing_routes, "get_pricing_storage", lambda: _FakeStorage())
    response = await pricing_routes.get_pricing_status(user=_admin())
    assert response.prices.entry_count == 0
    assert response.fx.rate_count == 0


@pytest.mark.asyncio
async def test_lookup_found(monkeypatch):
    from src.infra.pricing.calculator import PriceRates
    from src.infra.pricing.service import ResolvedPrice

    async def _fake_resolve(**kwargs):
        assert kwargs["value"] == "gpt-4o"
        return ResolvedPrice(
            rates=PriceRates(input=2.5, output=10, cache_read=1.25),
            source="models_dev",
            matched_provider="openai",
            matched_model_id="gpt-4o",
        )

    monkeypatch.setattr(pricing_routes.pricing_service, "resolve_price", _fake_resolve)
    response = await pricing_routes.lookup_price(value="gpt-4o", user=_admin())
    assert response.found is True
    assert response.source == "models_dev"
    assert response.rates["input"] == 2.5
    assert response.matched_provider == "openai"


@pytest.mark.asyncio
async def test_lookup_not_found(monkeypatch):
    async def _fake_resolve(**kwargs):
        return None

    monkeypatch.setattr(pricing_routes.pricing_service, "resolve_price", _fake_resolve)
    response = await pricing_routes.lookup_price(value="mystery", user=_admin())
    assert response.found is False
    assert response.rates is None
