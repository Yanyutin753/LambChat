"""An inapplicable write bucket must not block otherwise complete billing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.pricing import service
from src.infra.pricing.calculator import PriceRates, compute_cost
from src.infra.writer.present import create_presenter


def included_rates(**changes):
    values = dict(input=1.4, output=4.4, cache_read=0.26, cache_write=0, cache_write_included=True)
    values.update(changes)
    return PriceRates(**values)


@pytest.mark.parametrize("writes", [None, 0, 100])
def test_included_cache_creation_is_charged_in_regular_input_without_a_separate_bucket(writes):
    rates = included_rates()
    result = compute_cost(
        input_tokens=12822,
        output_tokens=86,
        cache_read_tokens=10880,
        cache_creation_tokens=writes,
        rates=rates,
    )
    assert result is not None
    assert result.total_usd == pytest.approx(0.005926)
    assert result.input_usd == pytest.approx(0.0027188)
    assert result.cache_write_usd == 0


def test_a_separate_free_write_bucket_still_requires_its_actual_count():
    rates = PriceRates(input=2, output=3, cache_read=0.2, cache_write=0)
    assert (
        compute_cost(
            input_tokens=100,
            output_tokens=10,
            cache_read_tokens=20,
            cache_creation_tokens=None,
            rates=rates,
        )
        is None
    )
    result = compute_cost(
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=20,
        cache_creation_tokens=50,
        rates=rates,
    )
    assert result.input_usd == pytest.approx(30 * 2 / 1_000_000)


async def test_zai_resolved_policy_restores_normal_cost_without_fabricating_usage(monkeypatch):
    entry = SimpleNamespace(
        rates=PriceRates(input=1.4, output=4.4, cache_read=0.26, cache_write=0),
        provider="zai",
        model_id="glm-5.3",
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(return_value=SimpleNamespace(match=lambda *args, **kwargs: entry)),
    )
    monkeypatch.setattr(service, "_load_model_override", AsyncMock(return_value=None))
    result = await service.compute_partial_usage_cost(
        model_value="glm-5.3",
        input_tokens=12822,
        output_tokens=86,
        cache_read_tokens=10880,
        cache_creation_tokens=None,
        input_includes_cache=True,
    )
    assert result is not None
    cost, rates, _ = result
    assert cost.total_usd == pytest.approx(0.005926)
    data = create_presenter(session_id="s", agent_id="a", agent_name="Agent").present_token_usage(
        input_tokens=12822,
        output_tokens=86,
        total_tokens=12908,
        cache_read_tokens=10880,
        cache_creation_tokens=None,
        unknown_usage_fields=["cache_creation_tokens"],
        input_includes_cache=True,
        cost=cost,
        rates=rates,
    )["data"]
    assert data["cost_complete"] is True
    assert data["cost_usd"] == pytest.approx(0.005926)
    assert data["usage_incomplete"] is True
    assert "cache_creation_tokens" not in data
    assert data["cost_rates"]["cache_write_included"] is True


@pytest.mark.parametrize("provider", ["anthropic", "amazon-bedrock", "custom"])
async def test_free_write_price_does_not_infer_an_included_policy_for_other_providers(
    monkeypatch, provider
):
    entry = SimpleNamespace(
        rates=PriceRates(input=2, output=3, cache_read=0.2, cache_write=0),
        provider=provider,
        model_id="model",
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(return_value=SimpleNamespace(match=lambda *args, **kwargs: entry)),
    )
    monkeypatch.setattr(service, "_load_model_override", AsyncMock(return_value=None))
    resolved = await service.resolve_price(value="model")
    assert resolved.rates.cache_write_included is False


async def test_an_explicit_separate_write_override_disables_provider_included_policy(monkeypatch):
    entry = SimpleNamespace(
        rates=PriceRates(input=2, output=3, cache_read=0.2, cache_write=0),
        provider="zai",
        model_id="glm-5.3",
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(return_value=SimpleNamespace(match=lambda *args, **kwargs: entry)),
    )
    monkeypatch.setattr(
        service, "_load_model_override", AsyncMock(return_value=PriceRates(cache_write=0))
    )
    resolved = await service.resolve_price(value="glm-5.3", model_config_id="override")
    assert resolved.rates.cache_write_included is False


@pytest.mark.parametrize("writes", [None, 50])
def test_included_policy_preserves_independent_input_cost_when_output_price_is_missing(writes):
    from src.infra.pricing.calculator import compute_partial_cost

    result = compute_partial_cost(
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=20,
        cache_creation_tokens=writes,
        rates=included_rates(input=2, output=None, cache_read=0),
        input_includes_cache=True,
    )
    assert result.components["input"] == pytest.approx(0.00016)
    assert result.components["cache_read"] == 0
    assert "cache_write" not in result.components
