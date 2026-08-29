"""pricing 运行时服务：价格解析（覆盖 > models.dev）、汇率读取、成本计算入口。

进程内缓存价格索引与汇率；所有查询 best-effort，失败不阻塞调用方。
"""

from dataclasses import dataclass
from typing import Optional

from src.infra.logging import get_logger
from src.infra.pricing.calculator import CostBreakdown, PriceRates, compute_cost
from src.infra.pricing.matching import PriceEntry, PriceIndex, restore_price_index
from src.infra.pricing.storage import get_pricing_storage

logger = get_logger(__name__)


@dataclass(frozen=True)
class ResolvedPrice:
    """解析结果：单价 + 来源信息。"""

    rates: PriceRates
    source: str  # "override" | "models_dev"
    matched_provider: str = ""
    matched_model_id: str = ""


# ── 进程内运行时缓存 ──────────────────────────────────────────────

_runtime_index: Optional[PriceIndex] = None
_runtime_fx: Optional[dict] = None


def reset_runtime_cache() -> None:
    """清空进程内缓存（测试与手动同步后使用）。"""
    global _runtime_index, _runtime_fx
    _runtime_index = None
    _runtime_fx = None


async def get_price_index() -> PriceIndex:
    """获取价格索引；首次访问从持久化快照加载。"""
    global _runtime_index
    if _runtime_index is None:
        snapshot = await get_pricing_storage().load_price_snapshot() or {}
        _runtime_index = restore_price_index(snapshot)
    return _runtime_index


async def get_fx_rates() -> Optional[dict]:
    """获取汇率文档 {base, rates, synced_at}；无数据返回 None。"""
    global _runtime_fx
    if _runtime_fx is None:
        _runtime_fx = await get_pricing_storage().load_fx_rates()
    return _runtime_fx


async def _load_model_override(model_config_id: str | None) -> Optional[PriceRates]:
    """读取模型配置上的价格覆盖；无配置或无覆盖返回 None。"""
    if not model_config_id:
        return None
    try:
        from src.infra.agent.model_storage import get_model_storage

        model = await get_model_storage().get(model_config_id)
        pricing = getattr(model, "pricing", None) if model else None
        if pricing is None:
            return None
        return PriceRates(
            input=pricing.input,
            output=pricing.output,
            cache_read=pricing.cache_read,
            cache_write=pricing.cache_write,
        )
    except Exception as e:
        logger.debug(f"Pricing: failed to load model override for {model_config_id}: {e}")
        return None


async def resolve_price(
    *,
    value: Optional[str],
    provider: Optional[str] = None,
    model_config_id: Optional[str] = None,
) -> Optional[ResolvedPrice]:
    """解析模型单价：模型配置覆盖（字段级合并）优先，其次 models.dev 匹配。"""
    override = await _load_model_override(model_config_id)

    entry: Optional[PriceEntry] = None
    if value:
        try:
            entry = (await get_price_index()).match(value, provider=provider)
        except Exception as e:
            logger.debug(f"Pricing: index match failed for {value!r}: {e}")

    if override is not None:
        base = entry.rates if entry is not None else PriceRates()
        merged = base.merge_override(override)
        if merged.is_priced():
            return ResolvedPrice(
                rates=merged,
                source="override",
                matched_provider=entry.provider if entry else "",
                matched_model_id=entry.model_id if entry else "",
            )
        return None

    if entry is not None and entry.rates.is_priced():
        return ResolvedPrice(
            rates=entry.rates,
            source="models_dev",
            matched_provider=entry.provider,
            matched_model_id=entry.model_id,
        )
    return None


async def compute_usage_cost(
    *,
    model_value: Optional[str],
    model_provider: Optional[str] = None,
    model_config_id: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> Optional[tuple[CostBreakdown, PriceRates, str]]:
    """对话结束时的成本计算入口。

    Returns:
        (成本分解, 单价, 来源) 或 None（无法计价）
    """
    resolved = await resolve_price(
        value=model_value,
        provider=model_provider,
        model_config_id=model_config_id,
    )
    if resolved is None:
        return None
    breakdown = compute_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        rates=resolved.rates,
    )
    if breakdown is None:
        return None
    return breakdown, resolved.rates, resolved.source
