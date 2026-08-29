"""Token 成本计算纯函数。

单价口径与 models.dev 一致：USD / 每百万 token。
token 口径与 LangChain usage_metadata 一致：input_tokens 包含 cache_read
与 cache_creation，需要先剔除再按各档单价计费。
"""

from dataclasses import dataclass

TOKENS_PER_UNIT = 1_000_000


@dataclass(frozen=True)
class PriceRates:
    """模型单价（USD / 每百万 token）。None 表示未收录/不单独计费。"""

    input: float | None = None
    output: float | None = None
    cache_read: float | None = None
    cache_write: float | None = None

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


def _per_million(tokens: int, price: float | None) -> float:
    if price is None:
        return 0.0
    return tokens * price / TOKENS_PER_UNIT


def compute_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    rates: PriceRates,
) -> CostBreakdown | None:
    """按单价计算 USD 成本；无法计价（缺 input 或 output 单价）返回 None。"""
    if not rates.is_priced():
        return None

    billable_input = max(input_tokens - cache_read_tokens - cache_creation_tokens, 0)
    return CostBreakdown(
        input_usd=_per_million(billable_input, rates.input),
        output_usd=_per_million(output_tokens, rates.output),
        cache_read_usd=_per_million(cache_read_tokens, rates.cache_read),
        cache_write_usd=_per_million(cache_creation_tokens, rates.cache_write),
    )
