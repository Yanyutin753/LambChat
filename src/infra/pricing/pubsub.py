"""Pricing Pub/Sub — 价格/汇率快照变更的跨副本缓存失效广播。

任一副本完成价格同步后向 Redis 发布失效消息，其他副本收到后清空本地
运行时缓存（下一次访问重新从 Mongo 加载）。广播是 best-effort：丢了
也由 service 层的缓存 TTL 兜底自愈。
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.pricing.service import reset_runtime_cache
from src.infra.pubsub_hub import get_pubsub_hub
from src.infra.storage.redis import get_redis_client
from src.infra.task.constants import PRICING_CACHE_CHANNEL

logger = get_logger(__name__)


class PricingPubSub:
    """Redis Pub/Sub listener for pricing snapshot changes."""

    def __init__(self):
        self._subscription_token: Optional[str] = None
        self._running = False
        # 唯一实例 ID —— 用于跳过自己发布的消息
        self._instance_id = uuid.uuid4().hex[:8]

    @property
    def instance_id(self) -> str:
        return self._instance_id

    async def start_listener(self) -> None:
        """应用启动时开始监听价格失效广播。"""
        if self._running:
            return

        hub = get_pubsub_hub()
        self._subscription_token = hub.subscribe(
            PRICING_CACHE_CHANNEL,
            self._handle_message,
        )
        await hub.start()
        self._running = True
        logger.info(
            f"Pricing pub/sub listening on channel: {PRICING_CACHE_CHANNEL} "
            f"(instance={self._instance_id})"
        )

    async def stop_listener(self) -> None:
        if not self._running:
            return
        hub = get_pubsub_hub()
        if self._subscription_token:
            hub.unsubscribe(self._subscription_token)
        self._running = False

    async def _handle_message(self, message: dict[str, Any]) -> None:
        try:
            data = await run_blocking_io(json.loads, message["data"])
            if data.get("instance_id") == self._instance_id:
                return
            logger.info("[PricingPubSub] 收到价格快照变更，清空本地缓存")
            reset_runtime_cache()
        except Exception as e:
            logger.warning(f"[PricingPubSub] 处理消息失败: {e}")


_pricing_pubsub: Optional[PricingPubSub] = None


def get_pricing_pubsub() -> PricingPubSub:
    global _pricing_pubsub
    if _pricing_pubsub is None:
        _pricing_pubsub = PricingPubSub()
    return _pricing_pubsub


async def publish_pricing_cache_invalidate() -> None:
    """价格/汇率快照写入成功后调用，通知其他副本失效缓存（best-effort）。"""
    try:
        redis_client = get_redis_client()
        pubsub = get_pricing_pubsub()
        message = await run_blocking_io(json.dumps, {"instance_id": pubsub.instance_id})
        await redis_client.publish(PRICING_CACHE_CHANNEL, message)
        logger.debug(f"[PricingPubSub] published cache invalidate: {message}")
    except Exception as e:
        logger.warning(f"[PricingPubSub] 发布失效广播失败: {e}")
