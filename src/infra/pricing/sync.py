"""pricing 同步：models.dev 价格表 + USD 汇率表。

两者独立拉取、独立降级：一个失败不影响另一个，失败时沿用上次快照。
多副本部署下用 Redis 锁互斥，同一时刻只有一个实例真正发起网络同步；
写入成功后广播缓存失效（PricingPubSub），广播失败由各副本缓存 TTL 兜底。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from src.infra.logging import get_logger
from src.infra.pricing.locks import acquire_pricing_lock, release_pricing_lock
from src.infra.pricing.matching import build_price_index
from src.infra.pricing.storage import PricingStorage, get_pricing_storage
from src.kernel.config import settings

logger = get_logger(__name__)

FETCH_TIMEOUT_SECONDS = 30.0
SYNC_LOCK_KEY = "pricing:sync:lock"
SYNC_LOCK_TTL_SECONDS = 15 * 60


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


async def fetch_models_dev(client: httpx.AsyncClient) -> dict:
    """拉取 models.dev api.json 并转为价格快照（含官方归属表）；非 200 抛异常。"""
    response = await client.get(settings.PRICING_MODELS_DEV_URL)
    response.raise_for_status()
    return build_price_index(response.json()).to_snapshot()


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

    快照未过期且未 force 时跳过网络请求；被其他副本持锁时本副本跳过；
    单侧失败保留旧快照并记入 error；写入成功后清本副本缓存并广播失效。
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
        status["lock_contended"] = False
        return status

    # 多副本互斥：锁竞争 → 本副本跳过；Redis 故障 → 退化本地执行（写入幂等）
    lock_token: Optional[str] = None
    lock_ok = True
    try:
        lock_token = await acquire_pricing_lock(SYNC_LOCK_KEY, SYNC_LOCK_TTL_SECONDS)
    except Exception as e:
        logger.warning(f"Pricing: sync lock unavailable, proceeding locally: {e}")
        lock_ok = False

    if lock_ok and lock_token is None:
        logger.info("Pricing: sync lock held by another replica, skipping")
        status = await storage.get_status()
        status["refreshed"] = False
        status["error"] = None
        status["lock_contended"] = True
        return status

    errors: list[str] = []
    changed = False
    try:
        async with _build_http_client() as client:
            if price_stale:
                try:
                    snapshot = await fetch_models_dev(client)
                    entries = snapshot.get("entries") or []
                    await storage.save_price_snapshot(
                        entries,
                        source_url=settings.PRICING_MODELS_DEV_URL,
                        model_owners=snapshot.get("model_owners"),
                    )
                    changed = True
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
                    changed = True
                    logger.info(
                        f"Pricing: synced {len(parsed['rates'])} fx rates (base {parsed['base']})"
                    )
                except Exception as e:
                    errors.append(f"fx: {e}")
                    logger.warning(f"Pricing: fx rates sync failed: {e}")
    finally:
        if lock_token is not None:
            await release_pricing_lock(SYNC_LOCK_KEY, lock_token)

    if changed:
        from src.infra.pricing.pubsub import publish_pricing_cache_invalidate
        from src.infra.pricing.service import reset_runtime_cache

        reset_runtime_cache()
        await publish_pricing_cache_invalidate()

    status = await storage.get_status()
    status["refreshed"] = True
    status["error"] = "; ".join(errors) if errors else None
    status["lock_contended"] = False
    return status
