"""
用户反馈 Schema

定义用户反馈的数据模型。
反馈关联到每个 run_id，用户对每个 run 只能提交一次反馈。
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# 评分值类型：up（好评）或 down（差评）
RatingValue = Literal["up", "down"]


class FeedbackBase(BaseModel):
    """反馈基础模型"""

    rating: RatingValue = Field(..., description="评分：up（好评）或 down（差评）")
    comment: Optional[str] = Field(None, max_length=1000, description="可选评论")


class FeedbackCreate(FeedbackBase):
    """创建反馈请求"""

    session_id: str = Field(..., description="会话ID")
    run_id: str = Field(..., description="运行ID")


class Feedback(FeedbackBase):
    """反馈响应模型"""

    id: str
    user_id: str
    username: str
    session_id: str
    run_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackInDB(Feedback):
    """数据库中的反馈文档（包含敏感字段)"""

    pass


class FeedbackStats(BaseModel):
    """反馈统计信息"""

    total_count: int = 0
    up_count: int = 0
    down_count: int = 0
    up_percentage: float = 0.0


class FeedbackListResponse(BaseModel):
    """反馈列表响应"""

    items: list[Feedback]
    total: int
    stats: FeedbackStats
