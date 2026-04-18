"""通知系统 Schema"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class I18nText(BaseModel):
    """多语言文本"""

    en: str
    zh: str
    ja: str
    ko: str
    ru: str


class NotificationCreate(BaseModel):
    """创建通知"""

    title_i18n: I18nText
    content_i18n: I18nText
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_active: bool = True


class NotificationUpdate(BaseModel):
    """更新通知"""

    title_i18n: Optional[I18nText] = None
    content_i18n: Optional[I18nText] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_active: Optional[bool] = None


class Notification(BaseModel):
    """通知响应"""

    id: str
    title_i18n: I18nText
    content_i18n: I18nText
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str

    model_config = ConfigDict(from_attributes=True)


class NotificationInDB(Notification):
    """数据库中的通知（完整字段）"""

    pass


class NotificationListResponse(BaseModel):
    """通知列表响应"""

    items: list[Notification]
    total: int
