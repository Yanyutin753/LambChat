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


@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4o-2024-08-06",
        "gpt-4o-mini-2024-07-18",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano-2025-04-14",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-5-codex",
        "gpt-5-2025-08-07",
        "gpt-5.1",
        "gpt-5.1-codex",
        "gpt-5.1-codex-mini",
        "gpt-5.1-codex-max",
        "gpt-5.2",
        "gpt-5.2-pro",
        "gpt-5.2-codex",
        "gpt-5.3-codex",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.5",
        "gpt-5.5-pro",
    ],
)
@pytest.mark.parametrize("write_rate", [None, 0])
async def test_official_legacy_openai_model_has_no_separate_write_bucket(
    monkeypatch,
    model,
    write_rate,
):
    entry = SimpleNamespace(
        rates=PriceRates(input=2, output=3, cache_read=0.2, cache_write=write_rate),
        provider="openai",
        model_id=model,
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(
            return_value=SimpleNamespace(
                match=lambda *args, **kwargs: entry,
            )
        ),
    )
    monkeypatch.setattr(service, "_load_model_override", AsyncMock(return_value=None))
    resolved = await service.resolve_price(value=model)
    assert resolved.rates.cache_write_included is True


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5.6",
        "gpt-5.6-sol",
        "gpt-5.6-mini",
        "gpt-5.10",
        "gpt-6",
        "gpt-6.1-sol",
        "gpt-4o-latest",
        "gpt-5-latest",
        "gpt-5.1-chat-latest",
        "gpt-5.5-latest",
        "chatgpt-4o-latest",
        "gpt-5.5-mystery",
        "gpt-unknown",
        "custom-model",
    ],
)
async def test_unknown_or_new_openai_models_do_not_infer_included_writes(monkeypatch, model):
    entry = SimpleNamespace(
        rates=PriceRates(input=2, output=3, cache_read=0.2, cache_write=0),
        provider="openai",
        model_id=model,
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(
            return_value=SimpleNamespace(
                match=lambda *args, **kwargs: entry,
            )
        ),
    )
    monkeypatch.setattr(service, "_load_model_override", AsyncMock(return_value=None))
    resolved = await service.resolve_price(value=model)
    assert resolved.rates.cache_write_included is False


async def test_drifting_request_alias_cannot_inherit_matched_legacy_openai_policy(monkeypatch):
    entry = SimpleNamespace(
        rates=PriceRates(input=2, output=3, cache_read=0.2, cache_write=0),
        provider="openai",
        model_id="gpt-5.5",
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(
            return_value=SimpleNamespace(
                match=lambda *args, **kwargs: entry,
            )
        ),
    )
    monkeypatch.setattr(service, "_load_model_override", AsyncMock(return_value=None))
    resolved = await service.resolve_price(value="gpt-5.5-latest")
    assert resolved.rates.cache_write_included is False


@pytest.mark.parametrize("provider", ["azure", "openrouter", "custom"])
async def test_legacy_openai_model_name_does_not_certify_other_provider_billing(
    monkeypatch, provider
):
    entry = SimpleNamespace(
        rates=PriceRates(input=2, output=3, cache_read=0.2, cache_write=0),
        provider=provider,
        model_id="gpt-4.1",
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(
            return_value=SimpleNamespace(
                match=lambda *args, **kwargs: entry,
            )
        ),
    )
    monkeypatch.setattr(service, "_load_model_override", AsyncMock(return_value=None))
    resolved = await service.resolve_price(value="gpt-4.1")
    assert resolved.rates.cache_write_included is False


@pytest.mark.parametrize("write_rate", [0.1, 2.5, True])
async def test_official_legacy_openai_nonzero_or_boolean_write_rate_is_not_included(
    monkeypatch, write_rate
):
    entry = SimpleNamespace(
        rates=PriceRates(input=2, output=3, cache_read=0.2, cache_write=write_rate),
        provider="openai",
        model_id="gpt-4.1",
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(
            return_value=SimpleNamespace(
                match=lambda *args, **kwargs: entry,
            )
        ),
    )
    monkeypatch.setattr(service, "_load_model_override", AsyncMock(return_value=None))
    resolved = await service.resolve_price(value="gpt-4.1")
    assert resolved.rates.cache_write_included is False


@pytest.mark.parametrize("write_override", [0, 0.5])
async def test_explicit_openai_write_override_disables_included_policy(monkeypatch, write_override):
    entry = SimpleNamespace(
        rates=PriceRates(input=2, output=3, cache_read=0.2, cache_write=0),
        provider="openai",
        model_id="gpt-4.1",
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(
            return_value=SimpleNamespace(
                match=lambda *args, **kwargs: entry,
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_load_model_override",
        AsyncMock(
            return_value=PriceRates(
                cache_write=write_override,
            )
        ),
    )
    resolved = await service.resolve_price(value="gpt-4.1", model_config_id="override")
    assert resolved.rates.cache_write_included is False


@pytest.mark.parametrize("api", ["chat", "responses"])
async def test_real_openai_sdk_missing_write_field_defaults_to_zero_and_prices_complete_bill(
    monkeypatch,
    api,
):
    from langchain_openai.chat_models.base import (
        _create_usage_metadata,
        _create_usage_metadata_responses,
    )

    from src.infra.agent.events.processor import AgentEventProcessor
    from src.infra.pricing.calculator import CostBreakdown

    if api == "chat":
        normalized = _create_usage_metadata(
            {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "total_tokens": 110,
                "prompt_tokens_details": {"cached_tokens": 20},
            }
        )
    else:
        normalized = _create_usage_metadata_responses(
            {
                "input_tokens": 100,
                "output_tokens": 10,
                "total_tokens": 110,
                "input_tokens_details": {"cached_tokens": 20},
            }
        )
    assert "cache_creation" not in normalized["input_token_details"]
    processor = AgentEventProcessor(create_presenter(session_id="openai-usage", agent_id="search"))
    processor._handle_token_usage(
        {
            "data": {
                "output": SimpleNamespace(
                    usage_metadata=normalized,
                    response_metadata={},
                )
            }
        }
    )
    snapshot = processor.usage_totals()
    assert snapshot["unknown_usage_fields"] == []
    assert snapshot["cache_creation_tokens"] == 0
    assert snapshot["input_includes_cache"] is True
    entry = SimpleNamespace(
        rates=PriceRates(input=2, output=3, cache_read=0.2),
        provider="openai",
        model_id="gpt-4.1",
    )
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(
            return_value=SimpleNamespace(
                match=lambda *args, **kwargs: entry,
            )
        ),
    )
    monkeypatch.setattr(service, "_load_model_override", AsyncMock(return_value=None))
    cost, rates, _ = await service.compute_partial_usage_cost(
        model_value="gpt-4.1",
        input_tokens=snapshot["input_tokens"],
        output_tokens=snapshot["output_tokens"],
        cache_read_tokens=snapshot["cache_read_tokens"],
        cache_creation_tokens=None,
        input_includes_cache=True,
    )
    assert isinstance(cost, CostBreakdown)
    assert cost.total_usd == pytest.approx(0.000194)
    data = processor.presenter.present_token_usage(
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_read_tokens=20,
        cache_creation_tokens=None,
        unknown_usage_fields=snapshot["unknown_usage_fields"],
        input_includes_cache=True,
        cost=cost,
        rates=rates,
    )["data"]
    assert data["cost_complete"] is True
    assert data["cost_usd"] == pytest.approx(0.000194)
    assert data["usage_incomplete"] is True
    assert data["unknown_usage_fields"] == ["cache_creation_tokens"]
    assert "cache_creation_tokens" not in data


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
