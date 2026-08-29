"""Pricing calculator 纯函数测试：token 计数 × 单价 → USD 成本。"""

from src.infra.pricing.calculator import CostBreakdown, PriceRates, compute_cost


class TestComputeCost:
    def test_basic_input_output_cost(self):
        rates = PriceRates(input=3.0, output=15.0)
        cost = compute_cost(
            input_tokens=1_000_000,
            output_tokens=200_000,
            rates=rates,
        )
        assert cost is not None
        assert cost.input_usd == 3.0
        assert cost.output_usd == 3.0
        assert cost.total_usd == 6.0

    def test_price_is_per_million_tokens(self):
        rates = PriceRates(input=1.0, output=1.0)
        cost = compute_cost(input_tokens=1_000, output_tokens=0, rates=rates)
        assert cost is not None
        assert cost.input_usd == 0.001

    def test_cache_tokens_excluded_from_billable_input(self):
        # LangChain 口径：input_tokens 包含 cache_read + cache_creation
        rates = PriceRates(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75)
        cost = compute_cost(
            input_tokens=1_000_000,
            output_tokens=100_000,
            cache_read_tokens=600_000,
            cache_creation_tokens=100_000,
            rates=rates,
        )
        assert cost is not None
        # billable input = 1M - 600k - 100k = 300k
        assert cost.input_usd == 300_000 * 3.0 / 1_000_000
        assert cost.cache_read_usd == 600_000 * 0.3 / 1_000_000
        assert cost.cache_write_usd == 100_000 * 3.75 / 1_000_000
        assert cost.output_usd == 100_000 * 15.0 / 1_000_000
        assert cost.total_usd == (
            cost.input_usd + cost.cache_read_usd + cost.cache_write_usd + cost.output_usd
        )

    def test_missing_input_price_returns_none(self):
        cost = compute_cost(
            input_tokens=100,
            output_tokens=100,
            rates=PriceRates(output=15.0),
        )
        assert cost is None

    def test_missing_output_price_returns_none(self):
        cost = compute_cost(
            input_tokens=100,
            output_tokens=100,
            rates=PriceRates(input=3.0),
        )
        assert cost is None

    def test_missing_cache_prices_bill_cache_tokens_at_zero(self):
        # 未提供缓存单价时按 0 计（models.dev 未收录即视为不单独计费）
        rates = PriceRates(input=3.0, output=15.0)
        cost = compute_cost(
            input_tokens=100_000,
            output_tokens=0,
            cache_read_tokens=50_000,
            rates=rates,
        )
        assert cost is not None
        assert cost.cache_read_usd == 0.0
        assert cost.cache_write_usd == 0.0
        assert cost.input_usd == 50_000 * 3.0 / 1_000_000

    def test_negative_billable_input_clamped_to_zero(self):
        rates = PriceRates(input=3.0, output=15.0)
        cost = compute_cost(
            input_tokens=100,
            output_tokens=0,
            cache_read_tokens=80,
            cache_creation_tokens=80,
            rates=rates,
        )
        assert cost is not None
        assert cost.input_usd == 0.0

    def test_zero_tokens_zero_cost(self):
        rates = PriceRates(input=3.0, output=15.0)
        cost = compute_cost(input_tokens=0, output_tokens=0, rates=rates)
        assert cost is not None
        assert cost.total_usd == 0.0

    def test_free_model_all_zero_rates_is_priced(self):
        # 单价全为 0 是「免费模型」，可计价（总额 0），与无法计价区分
        cost = compute_cost(
            input_tokens=1_000,
            output_tokens=1_000,
            rates=PriceRates(input=0.0, output=0.0),
        )
        assert cost is not None
        assert cost.total_usd == 0.0


class TestCostBreakdown:
    def test_total_sums_components(self):
        breakdown = CostBreakdown(
            input_usd=0.1,
            output_usd=0.2,
            cache_read_usd=0.03,
            cache_write_usd=0.04,
        )
        assert breakdown.total_usd == 0.37

    def test_to_event_data_shape(self):
        breakdown = CostBreakdown(
            input_usd=0.1,
            output_usd=0.2,
            cache_read_usd=0.03,
            cache_write_usd=0.04,
        )
        data = breakdown.to_event_data()
        assert data == {
            "input": 0.1,
            "output": 0.2,
            "cache_read": 0.03,
            "cache_write": 0.04,
            "total": 0.37,
        }
