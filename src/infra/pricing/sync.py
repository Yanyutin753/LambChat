"""pricing 同步：models.dev 价格表 + USD 汇率表。

两者独立拉取、独立降级：一个失败不影响另一个，失败时沿用上次快照。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from src.infra.logging import get_logger
from src.infra.pricing.matching import build_price_index
from src.infra.pricing.storage import PricingStorage, get_pricing_storage
from src.kernel.config import settings

logger = get_logger(__name__)

FETCH_TIMEOUT_SECONDS = 30.0


def _build_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True)


def parse_fx_payload(payload: Any) -> Optional[dict]:
    """解析 exchangerate-api 响应；无效返回 None。"""
    if not isinstance(payload, dict):
        return None
    if payload.get("result") != "success":
        return None
    rates = payload.get("rates")
    if not isinstance(rates, dict) or not rates:
        return None
    return {
        "base": str(payload.get("base_code") or "USD"),
        "rates": {str(code): float(rate) for code, rate in rates.items()},
        "source_updated_at": payload.get("time_last_update_unix"),
    }


async def fetch_models_dev(client: httpx.AsyncClient) -> list[dict]:
    """拉取 models.dev api.json 并转为快照条目；非 200 抛异常。"""
    response = await client.get(settings.PRICING_MODELS_DEV_URL)
    response.raise_for_status()
    index = build_price_index(response.json())
    return index.to_snapshot_entries()


async def _fetch_fx_rates(client: httpx.AsyncClient) -> Optional[dict]:
    response = await client.get(settings.PRICING_FX_RATES_URL)
    response.raise_for_status()
    return parse_fx_payload(response.json())


def _is_stale(synced_at: Optional[str], interval_hours: int) -> bool:
    if not synced_at:
        return True
    try:
        synced = datetime.fromisoformat(synced_at)
    except ValueError:
        return True
    if synced.tzinfo is None:
        synced = synced.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - synced > timedelta(hours=interval_hours)


async def sync_pricing(*, force: bool = False, storage: Optional[PricingStorage] = None) -> dict:
    """同步价格与汇率。

    快照未过期且未 force 时跳过网络请求；单侧失败保留旧快照并记入 error。
    """
    storage = storage or get_pricing_storage()
    price_snapshot = await storage.load_price_snapshot() or {}
    fx_doc = await storage.load_fx_rates() or {}

    price_stale = force or _is_stale(
        price_snapshot.get("synced_at"), settings.PRICING_SYNC_INTERVAL_HOURS
    )
    fx_stale = force or _is_stale(fx_doc.get("synced_at"), settings.PRICING_SYNC_INTERVAL_HOURS)
    if not price_stale and not fx_stale:
        status = await storage.get_status()
        status["refreshed"] = False
        status["error"] = None
        return status

    errors: list[str] = []
    async with _build_http_client() as client:
        if price_stale:
            try:
                entries = await fetch_models_dev(client)
                await storage.save_price_snapshot(
                    entries, source_url=settings.PRICING_MODELS_DEV_URL
                )
                logger.info(f"Pricing: synced {len(entries)} model prices from models.dev")
            except Exception as e:
                errors.append(f"models.dev: {e}")
                logger.warning(f"Pricing: models.dev sync failed: {e}")
        if fx_stale:
            try:
                parsed = await _fetch_fx_rates(client)
                if parsed is None:
                    raise ValueError("invalid fx payload")
                await storage.save_fx_rates(parsed["rates"], base=parsed["base"])
                logger.info(
                    f"Pricing: synced {len(parsed['rates'])} fx rates (base {parsed['base']})"
                )
            except Exception as e:
                errors.append(f"fx: {e}")
                logger.warning(f"Pricing: fx rates sync failed: {e}")

    status = await storage.get_status()
    status["refreshed"] = True
    status["error"] = "; ".join(errors) if errors else None
    return status
