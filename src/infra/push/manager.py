"""Push 通知管理器"""

from __future__ import annotations

from functools import lru_cache
from http import HTTPStatus

from src.infra.logging import get_logger
from src.infra.push.storage import PushSubscriptionStorage
from src.kernel.config import settings

logger = get_logger(__name__)


class PushManager:
    def __init__(self):
        self.storage = PushSubscriptionStorage()

    async def save_subscription(self, user_id: str, data: dict, user_agent: str = "") -> dict:
        subscription = await self.storage.create(user_id, data, user_agent)
        return subscription.model_dump()

    async def remove_subscription(self, endpoint: str) -> bool:
        return await self.storage.delete_by_endpoint(endpoint)

    async def remove_all_for_user(self, user_id: str) -> int:
        return await self.storage.delete_by_user(user_id)

    async def has_subscription(self, user_id: str, endpoint: str) -> bool:
        return await self.storage.has_subscription(user_id, endpoint)

    async def send_push_to_user(self, user_id: str, payload: dict) -> int:
        """Send Web Push notification to all of user's subscriptions. Returns delivered count."""
        if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
            return 0

        subscriptions = await self.storage.get_by_user(user_id)
        if not subscriptions:
            return 0

        import asyncio
        import json

        from pywebpush import webpush

        delivered = 0
        for sub in subscriptions:
            try:
                subscription_info = {
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.keys.p256dh,
                        "auth": sub.keys.auth,
                    },
                }
                data = json.dumps(payload)
                # pywebpush is synchronous; run in thread to avoid blocking event loop
                await asyncio.to_thread(
                    webpush,
                    subscription_info=subscription_info,
                    data=data,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": settings.VAPID_SUBJECT},
                )
                await self.storage.touch_last_used(sub.endpoint)
                delivered += 1
            except Exception as e:
                response = getattr(e, "response", None)
                status_code = getattr(e, "status_code", None) or getattr(
                    response, "status_code", None
                )
                if status_code == 400:
                    removed = await self.storage.record_bad_request(sub)
                    logger.info(
                        "Push subscription rejected (HTTP 400), retired_after_repeated_rejection=%s",
                        removed,
                    )
                elif status_code in (404, 410):
                    # Subscription expired or revoked
                    logger.info(
                        "Push subscription gone (HTTP %s), removing stored subscription",
                        status_code,
                    )
                    await self.storage.delete_by_endpoint(sub.endpoint)
                else:
                    # Use canonical reasons; provider text can contain subscription credentials.
                    try:
                        reason = (
                            HTTPStatus(status_code).phrase if status_code is not None else "Unknown"
                        )
                    except ValueError:
                        reason = "Unknown"
                    logger.warning(
                        "Failed to send push notification: error_type=%s status_code=%s reason=%s",
                        type(e).__name__,
                        status_code,
                        reason,
                    )
        return delivered

    async def close(self) -> None:
        await self.storage.close()


@lru_cache
def get_push_manager() -> PushManager:
    return PushManager()


async def close_push_manager() -> None:
    if get_push_manager.cache_info().currsize == 0:
        return
    try:
        await get_push_manager().close()
    finally:
        get_push_manager.cache_clear()
