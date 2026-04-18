"""通知路由"""

from functools import lru_cache

from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_current_user_required, require_permissions
from src.infra.notification.manager import NotificationManager
from src.kernel.schemas.notification import (
    Notification,
    NotificationCreate,
    NotificationListResponse,
    NotificationUpdate,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


@lru_cache
def get_notification_manager() -> NotificationManager:
    return NotificationManager()


@router.get("/active")
async def get_active_notification(
    user: TokenPayload = Depends(get_current_user_required),
    manager: NotificationManager = Depends(get_notification_manager),
) -> Notification | None:
    return await manager.get_active_notification(user.sub)


@router.get("/admin", response_model=NotificationListResponse)
async def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    _: None = Depends(require_permissions("notification:manage")),
    manager: NotificationManager = Depends(get_notification_manager),
) -> NotificationListResponse:
    items, total = await manager.list(skip=skip, limit=limit)
    return NotificationListResponse(items=items, total=total)


@router.post("/", response_model=Notification)
async def create_notification(
    data: NotificationCreate,
    user: TokenPayload = Depends(get_current_user_required),
    _: None = Depends(require_permissions("notification:manage")),
    manager: NotificationManager = Depends(get_notification_manager),
) -> Notification:
    return await manager.create(data, user.sub)


@router.put("/{notification_id}", response_model=Notification)
async def update_notification(
    notification_id: str,
    data: NotificationUpdate,
    _: None = Depends(require_permissions("notification:manage")),
    manager: NotificationManager = Depends(get_notification_manager),
) -> Notification:
    try:
        result = await manager.update(notification_id, data)
    except (InvalidId, ValueError):
        result = None
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return result


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    _: None = Depends(require_permissions("notification:manage")),
    manager: NotificationManager = Depends(get_notification_manager),
) -> dict:
    success = await manager.delete(notification_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return {"status": "deleted"}


@router.post("/{notification_id}/dismiss")
async def dismiss_notification(
    notification_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    manager: NotificationManager = Depends(get_notification_manager),
) -> dict:
    await manager.dismiss(notification_id, user.sub)
    return {"status": "dismissed"}
