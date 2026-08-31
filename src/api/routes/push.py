"""Push 订阅路由"""

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user_required
from src.infra.logging import get_logger
from src.infra.push.manager import get_push_manager
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.push_subscription import (
    PushSubscription,
    PushSubscriptionCreate,
    UnsubscribeRequest,
    VapidPublicKeyResponse,
)
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

router = APIRouter()


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
async def get_vapid_public_key() -> VapidPublicKeyResponse:
    """Get VAPID public key for push subscription (no auth required)."""
    if not settings.VAPID_PUBLIC_KEY:
        raise AppError(ErrorCode.PUSH_UNAVAILABLE)
    return VapidPublicKeyResponse(public_key=settings.VAPID_PUBLIC_KEY)


@router.post("/subscribe", response_model=PushSubscription)
async def subscribe_push(
    data: PushSubscriptionCreate,
    user: TokenPayload = Depends(get_current_user_required),
    manager=Depends(get_push_manager),
) -> PushSubscription:
    """Save a push subscription from the browser."""
    if not data.endpoint.startswith("https://"):
        raise AppError(ErrorCode.PUSH_ENDPOINT_HTTPS_REQUIRED)
    if not data.keys.p256dh or not data.keys.auth:
        raise AppError(ErrorCode.PUSH_SUBSCRIPTION_KEYS_REQUIRED)
    subscription = await manager.save_subscription(
        user_id=user.sub,
        data=data.model_dump(),
        user_agent=data.user_agent,
    )
    logger.info("Push subscription saved: user_id=%s", user.sub)
    return PushSubscription.model_validate(subscription)


@router.post("/unsubscribe")
async def unsubscribe_push(
    data: UnsubscribeRequest,
    user: TokenPayload = Depends(get_current_user_required),
    manager=Depends(get_push_manager),
) -> dict:
    """Remove a push subscription."""
    deleted = await manager.remove_subscription(data.endpoint)
    return {"status": "unsubscribed", "deleted": deleted}


@router.delete("/subscriptions")
async def delete_all_subscriptions(
    user: TokenPayload = Depends(get_current_user_required),
    manager=Depends(get_push_manager),
) -> dict:
    """Remove all push subscriptions for the current user."""
    deleted = await manager.remove_all_for_user(user.sub)
    return {"status": "deleted", "count": deleted}
