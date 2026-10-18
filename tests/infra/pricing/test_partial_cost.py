"""Unknown usage suppresses only the cost components that depend on it."""

from types import SimpleNamespace

import pytest

from src.infra.pricing import calculator, service
from src.infra.pricing.calculator import PriceRates
from src.infra.writer.present import create_presenter


def partial(**values):
    compute = getattr(calculator, "compute_partial_cost", None)
    assert callable(compute), "Independent known components must remain calculable"
    return compute(**values)


def test_missing_cache_write_preserves_known_output_and_cache_read_cost():
    result = partial(
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_read_tokens=200_000,
        cache_creation_tokens=None,
        rates=PriceRates(input=2, output=10, cache_read=0.2, cache_write=3),
        input_includes_cache=True,
    )
    assert result.components == {"output": 1.0, "cache_read": 0.04}
    assert result.total_usd == 1.04


@pytest.mark.parametrize("certificate", [False, 1, None])
def test_partial_fee_does_not_certify_unverified_input(certificate):
    result = partial(
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=0,
        cache_creation_tokens=None,
        rates=PriceRates(input=2, output=10),
        input_includes_cache=certificate,
    )
    assert result.components == {}


def test_missing_cache_price_preserves_other_known_components():
    result = partial(
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=50,
        cache_creation_tokens=20,
        rates=PriceRates(input=1, output=2, cache_write=1.2),
        input_includes_cache=True,
    )
    assert result.components == {"input": 0.00003, "output": 0.00002, "cache_write": 0.000024}
    assert result.total_usd == 0.000074


def test_explicit_zero_count_keeps_zero_cost_without_a_rate():
    result = partial(
        input_tokens=None,
        output_tokens=0,
        cache_read_tokens=None,
        cache_creation_tokens=None,
        rates=PriceRates(),
        input_includes_cache=True,
    )
    assert result.components == {"output": 0.0}


def test_contradictory_cache_counters_do_not_produce_confirmed_cache_components():
    result = partial(
        input_tokens=10,
        output_tokens=2,
        cache_read_tokens=20,
        cache_creation_tokens=5,
        rates=PriceRates(input=1, output=2, cache_read=0.1, cache_write=1.2),
        input_includes_cache=True,
    )
    assert result.components == {"output": 0.000004}


async def test_partial_pricing_resolves_rates_when_only_input_price_exists(monkeypatch):
    entry = SimpleNamespace(rates=PriceRates(input=2), provider="test", model_id="model")
    monkeypatch.setattr(service, "get_price_index", lambda: None)

    async def index():
        return SimpleNamespace(match=lambda *args, **kwargs: entry)

    monkeypatch.setattr(service, "get_price_index", index)
    function = getattr(service, "compute_partial_usage_cost", None)
    assert callable(function), "Incomplete usage must still resolve applicable prices"
    cost, rates, _ = await function(
        model_value="model",
        model_config_id=None,
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        input_includes_cache=True,
    )
    assert rates.input == 2 and rates.output is None
    assert cost.components == {"input": 0.0002, "cache_read": 0.0, "cache_write": 0.0}


def test_presenter_exposes_partial_amount_without_confirmed_total():
    cost = partial(
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=20,
        cache_creation_tokens=None,
        rates=PriceRates(input=1, output=2, cache_read=0.1),
        input_includes_cache=True,
    )
    presenter = create_presenter(session_id="partial-test", agent_id="search")
    data = presenter.present_token_usage(
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_read_tokens=20,
        cache_creation_tokens=None,
        unknown_usage_fields=["cache_creation_tokens"],
        input_includes_cache=True,
        cost=cost,
        rates=PriceRates(input=1, output=2, cache_read=0.1),
    )["data"]
    assert data["partial_cost_usd"] == 0.000022
    assert data["partial_cost_breakdown"] == {"output": 0.00002, "cache_read": 0.000002}
    assert "cost_usd" not in data and data["usage_incomplete"] is True


@pytest.mark.parametrize("missing_write", [True, False])
async def test_processor_retains_calculable_components_for_incomplete_bill(
    monkeypatch, missing_write
):
    from src.infra.agent.events.processor import AgentEventProcessor

    rates = PriceRates(
        input=1, output=2, cache_read=0.1 if missing_write else None, cache_write=1.2
    )

    async def index():
        return SimpleNamespace(
            match=lambda *args, **kwargs: SimpleNamespace(
                rates=rates, provider="test", model_id="model"
            )
        )

    monkeypatch.setattr(service, "get_price_index", index)
    presenter = create_presenter(session_id="partial-test", agent_id="search")
    processor = AgentEventProcessor(presenter)
    processor._usage_observed = True
    processor._input_includes_cache = True
    processor.total_input_tokens = 100
    processor.total_output_tokens = 10
    processor.total_tokens = 110
    processor.total_cache_read_tokens = 20
    processor.total_cache_creation_tokens = 0
    processor._usage_unknown_fields = {"cache_creation_tokens"} if missing_write else set()
    events = []

    async def emit(event):
        events.append(event)

    processor._presenter_emit = emit
    assert await processor.emit_token_usage(model="model")
    data = events[-1]["data"]
    assert data["partial_cost_usd"] == (0.000022 if missing_write else 0.0001)
    assert data["partial_cost_breakdown"]["output"] == 0.00002
    assert "cost_usd" not in data


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_tokens", True),
        ("output_tokens", -1),
        ("input_tokens", float("nan")),
        ("cache_read_tokens", False),
    ],
)
def test_exact_cost_rejects_invalid_counters(field, value):
    quantities = dict(
        input_tokens=100, output_tokens=10, cache_read_tokens=20, cache_creation_tokens=5
    )
    quantities[field] = value
    assert (
        calculator.compute_cost(
            **quantities, rates=PriceRates(input=1, output=2, cache_read=0.1, cache_write=1.2)
        )
        is None
    )


@pytest.mark.parametrize(
    "field,value",
    [("input", float("nan")), ("output", float("inf")), ("cache_read", -1), ("cache_write", True)],
)
def test_exact_cost_rejects_invalid_rates(field, value):
    rates = dict(input=1, output=2, cache_read=0.1, cache_write=1.2)
    rates[field] = value
    assert (
        calculator.compute_cost(
            input_tokens=100,
            output_tokens=10,
            cache_read_tokens=20,
            cache_creation_tokens=5,
            rates=PriceRates(**rates),
        )
        is None
    )


def test_exact_cost_rejects_contradictory_cache_counters():
    assert (
        calculator.compute_cost(
            input_tokens=100,
            output_tokens=10,
            cache_read_tokens=80,
            cache_creation_tokens=50,
            rates=PriceRates(input=1, output=2, cache_read=0.1, cache_write=1.2),
        )
        is None
    )


async def test_partial_fallback_prices_the_same_snapshot_as_the_event(monkeypatch):
    from src.infra.agent.events import processor as module

    processor = module.AgentEventProcessor(
        create_presenter(session_id="snapshot", agent_id="search")
    )
    processor._usage_observed = True
    processor._input_includes_cache = True
    processor.total_input_tokens = 100
    processor.total_output_tokens = 10
    processor.total_tokens = 110
    processor.total_cache_read_tokens = 20
    injected = False

    async def exact(**kwargs):
        nonlocal injected
        if not injected:
            injected = True
            processor._handle_token_usage(
                {
                    "data": {
                        "output": SimpleNamespace(
                            usage_metadata={
                                "input_tokens": 100,
                                "output_tokens": 10,
                                "total_tokens": 110,
                                "input_token_details": {"cache_read": 20, "cache_creation": 0},
                            }
                        )
                    }
                }
            )
        return None

    async def index():
        return SimpleNamespace(
            match=lambda *args, **kwargs: SimpleNamespace(
                rates=PriceRates(input=1, output=2), provider="test", model_id="model"
            )
        )

    monkeypatch.setattr(module, "compute_usage_cost", exact)
    monkeypatch.setattr(service, "get_price_index", index)
    events = []

    async def emit(event):
        events.append(event)

    processor._presenter_emit = emit
    await processor.emit_token_usage(model="model")
    assert events[-1]["data"]["input_tokens"] == 100
    assert events[-1]["data"]["partial_cost_usd"] == 0.0001
    await processor.emit_token_usage(model="model")
    assert events[-1]["data"]["input_tokens"] == 200
    assert events[-1]["data"]["partial_cost_usd"] == 0.0002
