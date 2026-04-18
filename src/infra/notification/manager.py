"""通知管理器"""

from __future__ import annotations

from typing import Optional

from src.infra.logging import get_logger
from src.infra.notification.storage import NotificationStorage
from src.kernel.schemas.notification import (
    Notification,
    NotificationCreate,
    NotificationUpdate,
)

logger = get_logger(__name__)


class NotificationManager:
    def __init__(self):
        self.storage = NotificationStorage()

    async def create(self, data: NotificationCreate, user_id: str) -> Notification:
        return await self.storage.create(data, user_id)

    async def get_by_id(self, notification_id: str) -> Optional[Notification]:
        return await self.storage.get_by_id(notification_id)

    async def list(self, skip: int = 0, limit: int = 50) -> tuple[list[Notification], int]:
        return await self.storage.list(skip=skip, limit=limit)

    async def update(
        self, notification_id: str, data: NotificationUpdate
    ) -> Optional[Notification]:
        return await self.storage.update(notification_id, data)

    async def delete(self, notification_id: str) -> bool:
        return await self.storage.delete(notification_id)

    async def get_active_notification(self, user_id: str) -> Optional[Notification]:
        return await self.storage.get_active_notification(user_id)

    async def dismiss(self, notification_id: str, user_id: str) -> bool:
        return await self.storage.dismiss(notification_id, user_id)
