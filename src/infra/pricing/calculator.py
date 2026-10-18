"""Token 成本计算纯函数。

单价口径与 models.dev 一致：USD / 每百万 token。
token 口径与 LangChain usage_metadata 一致：input_tokens 包含 cache_read
与 cache_creation，需要先剔除再按各档单价计费。
"""

import math
from dataclasses import dataclass
from typing import TypeGuard

TOKENS_PER_UNIT = 1_000_000


def _valid_tokens(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_rate(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _included_cache_write(rates: "PriceRates") -> bool:
    return rates.cache_write_included is True and (
        rates.cache_write is None or _valid_rate(rates.cache_write) and rates.cache_write == 0
    )


@dataclass(frozen=True)
class PriceRates:
    """模型单价（USD / 每百万 token）。None 表示未知，明确免费使用 0。"""

    input: float | None = None
    output: float | None = None
    cache_read: float | None = None
    cache_write: float | None = None
    # Certified provider/model policies charge newly cached content as ordinary input.
    cache_write_included: bool = False

    def is_priced(self) -> bool:
        """是否具备可计价条件（至少 input 与 output 单价齐备）。"""
        return self.input is not None and self.output is not None

    def merge_override(self, override: "PriceRates") -> "PriceRates":
        """字段级合并：override 中非 None 的字段覆盖本地值。"""
        return PriceRates(
            input=override.input if override.input is not None else self.input,
            output=override.output if override.output is not None else self.output,
            cache_read=override.cache_read if override.cache_read is not None else self.cache_read,
            cache_write=override.cache_write
            if override.cache_write is not None
            else self.cache_write,
            cache_write_included=self.cache_write_included is True and override.cache_write is None,
        )


@dataclass(frozen=True)
class CostBreakdown:
    """一次调用的 USD 成本分解。"""

    input_usd: float = 0.0
    output_usd: float = 0.0
    cache_read_usd: float = 0.0
    cache_write_usd: float = 0.0

    @property
    def total_usd(self) -> float:
        # 金额求和消除浮点噪声（1e-12 远小于展示精度）
        return round(
            self.input_usd + self.output_usd + self.cache_read_usd + self.cache_write_usd,
            12,
        )

    def to_event_data(self) -> dict[str, float]:
        return {
            "input": self.input_usd,
            "output": self.output_usd,
            "cache_read": self.cache_read_usd,
            "cache_write": self.cache_write_usd,
            "total": self.total_usd,
        }


@dataclass(frozen=True)
class PartialCostBreakdown:
    """Independently calculable components; their sum is not a complete bill."""

    components: dict[str, float]

    @property
    def total_usd(self) -> float:
        return round(sum(self.components.values()), 12)


def compute_partial_cost(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None,
    cache_creation_tokens: int | None,
    rates: PriceRates,
    input_includes_cache: bool,
) -> PartialCostBreakdown:
    components: dict[str, float] = {}
    if input_includes_cache is not True:
        return PartialCostBreakdown(components)

    def add(name, count, rate):
        if not _valid_tokens(count):
            return
        if count == 0:
            components[name] = 0.0
        elif _valid_rate(rate):
            amount = count * rate / TOKENS_PER_UNIT
            if math.isfinite(amount):
                components[name] = amount

    contradictory = _valid_tokens(input_tokens) and (
        _valid_tokens(cache_read_tokens)
        and cache_read_tokens > input_tokens
        or _valid_tokens(cache_creation_tokens)
        and cache_creation_tokens > input_tokens
        or _valid_tokens(cache_read_tokens)
        and _valid_tokens(cache_creation_tokens)
        and cache_read_tokens + cache_creation_tokens > input_tokens
    )
    included_write = _included_cache_write(rates)
    invalid_policy = rates.cache_write_included is True and not included_write
    if (
        not contradictory
        and included_write
        and _valid_tokens(input_tokens)
        and _valid_tokens(cache_read_tokens)
    ):
        add("input", input_tokens - cache_read_tokens, rates.input)
    elif (
        not contradictory
        and not invalid_policy
        and all(_valid_tokens(v) for v in (input_tokens, cache_read_tokens, cache_creation_tokens))
    ):
        assert input_tokens is not None and cache_read_tokens is not None
        assert cache_creation_tokens is not None
        if cache_read_tokens + cache_creation_tokens <= input_tokens:
            add("input", input_tokens - cache_read_tokens - cache_creation_tokens, rates.input)
    add("output", output_tokens, rates.output)
    if not contradictory:
        add("cache_read", cache_read_tokens, rates.cache_read)
        if not included_write and not invalid_policy:
            add("cache_write", cache_creation_tokens, rates.cache_write)
    if not math.isfinite(sum(components.values())):
        components.clear()
    return PartialCostBreakdown(components)


def _per_million(tokens: int, price: float | None) -> float:
    if price is None:
        return 0.0
    return tokens * price / TOKENS_PER_UNIT


def compute_cost(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None = 0,
    cache_creation_tokens: int | None = 0,
    rates: PriceRates,
) -> CostBreakdown | None:
    """按单价计算 USD 成本；无法计价（缺 input 或 output 单价）返回 None。"""
    if not rates.is_priced():
        return None
    included_write = _included_cache_write(rates)
    if rates.cache_write_included is True and not included_write:
        return None
    if any(not _valid_tokens(v) for v in (input_tokens, output_tokens, cache_read_tokens)):
        return None
    if not _valid_tokens(cache_creation_tokens) and not (
        included_write and cache_creation_tokens is None
    ):
        return None
    if any(
        rate is not None and not _valid_rate(rate)
        for rate in (rates.input, rates.output, rates.cache_read, rates.cache_write)
    ):
        return None
    if (
        input_tokens is None
        or output_tokens is None
        or cache_read_tokens is None
        or (cache_creation_tokens is None and not included_write)
    ):
        return None
    if cache_read_tokens + (cache_creation_tokens or 0) > input_tokens:
        return None
    if (
        cache_read_tokens > 0
        and rates.cache_read is None
        or not included_write
        and (cache_creation_tokens or 0) > 0
        and rates.cache_write is None
    ):
        return None

    billable_input = input_tokens - cache_read_tokens
    if not included_write:
        billable_input -= cache_creation_tokens or 0
    result = CostBreakdown(
        input_usd=_per_million(billable_input, rates.input),
        output_usd=_per_million(output_tokens, rates.output),
        cache_read_usd=_per_million(cache_read_tokens, rates.cache_read),
        cache_write_usd=0.0
        if included_write
        else _per_million(cache_creation_tokens or 0, rates.cache_write),
    )
    return result if math.isfinite(result.total_usd) else None
