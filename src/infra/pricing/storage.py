"""Pricing storage layer.

独立的 model_prices 集合，保存两类单文档快照：
- 价格快照（models.dev 同步结果）
- USD 汇率表（exchangerate-api 同步结果）
"""

from datetime import datetime, timezone
from typing import Any, Optional

from src.infra.logging import get_logger
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)

PRICE_SNAPSHOT_DOC_ID = "models_dev_snapshot"
FX_RATES_DOC_ID = "fx_rates"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PricingStorage:
    """价格/汇率持久化 — model_prices 集合内的固定 _id 文档"""

    def __init__(self, collection: Optional[Any] = None):
        # 测试可直接注入假集合；生产环境延迟加载真实集合
        self._injected: Optional[Any] = collection
        self._lazy_collection: Optional[Any] = None

    @property
    def collection(self):
        if self._injected is not None:
            return self._injected
        if self._lazy_collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._lazy_collection = db[settings.MONGODB_MODEL_PRICES_COLLECTION]
        return self._lazy_collection

    async def ensure_indexes(self) -> None:
        try:
            await self.collection.create_index("_id")
        except Exception as e:
            logger.error(f"Failed to ensure pricing indexes: {e}")

    async def save_price_snapshot(self, entries: list[dict], *, source_url: str = "") -> bool:
        """保存 models.dev 价格快照（整体覆盖）。"""
        try:
            await self.collection.update_one(
                {"_id": PRICE_SNAPSHOT_DOC_ID},
                {
                    "$set": {
                        "entries": entries,
                        "entry_count": len(entries),
                        "source_url": source_url,
                        "synced_at": _utc_now_iso(),
                    }
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save price snapshot: {e}")
            return False

    async def load_price_snapshot(self) -> Optional[dict]:
        try:
            return await self.collection.find_one({"_id": PRICE_SNAPSHOT_DOC_ID})
        except Exception as e:
            logger.error(f"Failed to load price snapshot: {e}")
            return None

    async def save_fx_rates(self, rates: dict[str, float], *, base: str = "USD") -> bool:
        """保存 USD 汇率表（整体覆盖）。"""
        try:
            await self.collection.update_one(
                {"_id": FX_RATES_DOC_ID},
                {
                    "$set": {
                        "base": base,
                        "rates": rates,
                        "rate_count": len(rates),
                        "synced_at": _utc_now_iso(),
                    }
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save fx rates: {e}")
            return False

    async def load_fx_rates(self) -> Optional[dict]:
        try:
            return await self.collection.find_one({"_id": FX_RATES_DOC_ID})
        except Exception as e:
            logger.error(f"Failed to load fx rates: {e}")
            return None

    async def get_status(self) -> dict[str, Any]:
        prices = await self.load_price_snapshot() or {}
        fx = await self.load_fx_rates() or {}
        return {
            "prices": {
                "entry_count": prices.get("entry_count", 0),
                "source_url": prices.get("source_url", ""),
                "synced_at": prices.get("synced_at"),
            },
            "fx": {
                "base": fx.get("base", "USD"),
                "rate_count": fx.get("rate_count", 0),
                "synced_at": fx.get("synced_at"),
            },
        }


def get_pricing_storage() -> PricingStorage:
    """获取 PricingStorage 实例"""
    return PricingStorage()
