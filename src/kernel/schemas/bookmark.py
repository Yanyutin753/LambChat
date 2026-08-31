"""消息书签 Schema

用户对会话内某条消息（如一份大纲/总结）的收藏标记，
按 (user_id, session_id, message_id) 唯一。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BookmarkToggleRequest(BaseModel):
    """切换书签请求"""

    run_id: Optional[str] = Field(None, description="消息所属 run，用于跳转定位")
    label: Optional[str] = Field(None, max_length=200, description="消息摘要，列表展示用")


class Bookmark(BaseModel):
    """书签响应模型"""

    id: str
    user_id: str
    session_id: str
    message_id: str
    run_id: Optional[str] = None
    label: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookmarkWithSession(Bookmark):
    """带会话信息的书签（列表用）"""

    session_name: Optional[str] = None
    session_is_active: bool = True
