"""Unreported quantities and unknown rates must never silently become free usage."""

import pytest

from src.infra.pricing.calculator import PriceRates, compute_cost


@pytest.mark.parametrize("kind", ["cache_read", "cache_write"])
def test_positive_cache_usage_with_unknown_rate_is_unpriced(kind):
    quantities = {"cache_read_tokens": 0, "cache_creation_tokens": 0}
    quantities["cache_read_tokens" if kind == "cache_read" else "cache_creation_tokens"] = 50
    assert (
        compute_cost(
            input_tokens=100, output_tokens=10, rates=PriceRates(input=1, output=2), **quantities
        )
        is None
    )


@pytest.mark.parametrize(
    "field", ["input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"]
)
def test_unknown_usage_quantity_is_not_priced_as_zero(field):
    quantities = {
        "input_tokens": 100,
        "output_tokens": 10,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }
    quantities[field] = None
    assert (
        compute_cost(
            rates=PriceRates(input=1, output=2, cache_read=0.1, cache_write=1.2), **quantities
        )
        is None
    )


def test_explicit_free_cache_rates_remain_known_zero():
    result = compute_cost(
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=50,
        cache_creation_tokens=20,
        rates=PriceRates(input=1, output=2, cache_read=0, cache_write=0),
    )
    assert result is not None
    assert result.cache_read_usd == result.cache_write_usd == 0
    assert result.input_usd == 30 / 1_000_000
    assert result.output_usd == 20 / 1_000_000
