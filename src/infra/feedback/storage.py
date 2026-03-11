"""
用户反馈存储层

处理用户反馈的数据库操作。
每个用户对每个 run 只能提交一次反馈。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from src.infra.logging import get_logger
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings
from src.kernel.schemas.feedback import (
    Feedback,
    FeedbackCreate,
    FeedbackStats,
    RatingValue,
)

logger = get_logger(__name__)


class FeedbackStorage:
    """用户反馈存储"""

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db["feedback"]
        return self._collection

    async def create_indexes(self) -> None:
        """创建索引"""
        # 唯一索引：每个用户对每个 run 只能有一条反馈
        await self.collection.create_index(
            [("user_id", 1), ("session_id", 1), ("run_id", 1)], unique=True, name="user_run_unique"
        )
        # 查询索引
        await self.collection.create_index([("session_id", 1), ("run_id", 1)])
        await self.collection.create_index([("rating", 1)])
        await self.collection.create_index([("created_at", -1)])
        logger.info("Feedback indexes created")

    async def create(
        self,
        feedback_data: FeedbackCreate,
        user_id: str,
        username: str,
    ) -> Feedback:
        """
        创建反馈

        Args:
            feedback_data: 反馈数据
            user_id: 用户ID
            username: 用户名

        Returns:
            创建的反馈

        Raises:
            ValueError: 如果用户已对该 run 提交过反馈
        """
        # 检查是否已存在
        existing = await self.get_user_feedback_for_run(
            user_id, feedback_data.session_id, feedback_data.run_id
        )
        if existing:
            raise ValueError("您已经对该对话提交过反馈")

        now = datetime.now(timezone.utc)
        feedback_dict: dict[str, Any] = {
            "user_id": user_id,
            "username": username,
            "session_id": feedback_data.session_id,
            "run_id": feedback_data.run_id,
            "rating": feedback_data.rating,
            "comment": feedback_data.comment,
            "created_at": now,
        }
        result = await self.collection.insert_one(feedback_dict)
        feedback_dict["id"] = str(result.inserted_id)
        return Feedback.model_validate(feedback_dict)

    async def get_by_id(self, feedback_id: str) -> Optional[Feedback]:
        """
        根据ID获取反馈

        Args:
            feedback_id: 反馈ID

        Returns:
            反馈对象，如果不存在则返回None
        """
        try:
            doc = await self.collection.find_one({"_id": ObjectId(feedback_id)})
            if doc:
                doc["id"] = str(doc.pop("_id"))
                return Feedback.model_validate(doc)
            return None
        except Exception as e:
            logger.error(f"Error getting feedback {feedback_id}: {e}")
            return None

    async def get_user_feedback_for_run(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
    ) -> Optional[Feedback]:
        """
        获取用户对某个 run 的反馈

        Args:
            user_id: 用户ID
            session_id: 会话ID
            run_id: 运行ID

        Returns:
            反馈对象，如果不存在则返回None
        """
        doc = await self.collection.find_one(
            {
                "user_id": user_id,
                "session_id": session_id,
                "run_id": run_id,
            }
        )
        if doc:
            doc["id"] = str(doc.pop("_id"))
            return Feedback.model_validate(doc)
        return None

    async def get_by_run(
        self,
        session_id: str,
        run_id: str,
    ) -> list[Feedback]:
        """
        获取某个 run 的所有反馈

        Args:
            session_id: 会话ID
            run_id: 运行ID

        Returns:
            反馈列表
        """
        cursor = self.collection.find(
            {
                "session_id": session_id,
                "run_id": run_id,
            }
        ).sort("created_at", -1)
        feedbacks: list[Feedback] = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            feedbacks.append(Feedback.model_validate(doc))
        return feedbacks

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
        rating: Optional[RatingValue] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[Feedback]:
        """
        获取反馈列表

        Args:
            skip: 跳过数量
            limit: 限制数量
            rating: 评分过滤
            user_id: 用户ID过滤
            session_id: 会话ID过滤

        Returns:
            反馈列表
        """
        query: dict[str, Any] = {}
        if rating is not None:
            query["rating"] = rating
        if user_id is not None:
            query["user_id"] = user_id
        if session_id is not None:
            query["session_id"] = session_id

        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        feedbacks: list[Feedback] = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            feedbacks.append(Feedback.model_validate(doc))
        return feedbacks

    async def count(
        self,
        rating: Optional[RatingValue] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> int:
        """
        统计反馈数量

        Args:
            rating: 评分过滤
            user_id: 用户ID过滤
            session_id: 会话ID过滤

        Returns:
            数量
        """
        query: dict[str, Any] = {}
        if rating is not None:
            query["rating"] = rating
        if user_id is not None:
            query["user_id"] = user_id
        if session_id is not None:
            query["session_id"] = session_id
        return await self.collection.count_documents(query)

    async def delete(self, feedback_id: str) -> bool:
        """
        删除反馈

        Args:
            feedback_id: 反馈ID

        Returns:
            是否删除成功
        """
        try:
            result = await self.collection.delete_one({"_id": ObjectId(feedback_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting feedback {feedback_id}: {e}")
            return False

    async def get_stats(
        self,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> FeedbackStats:
        """
        获取反馈统计信息

        Args:
            session_id: 可选的会话ID过滤
            run_id: 可选的运行ID过滤

        Returns:
            统计信息
        """
        query: dict[str, Any] = {}
        if session_id is not None:
            query["session_id"] = session_id
        if run_id is not None:
            query["run_id"] = run_id

        # Use aggregation to get all counts in a single query
        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "up_count": {"$sum": {"$cond": [{"$eq": ["$rating", "up"]}, 1, 0]}},
                    "down_count": {"$sum": {"$cond": [{"$eq": ["$rating", "down"]}, 1, 0]}},
                }
            },
        ]

        result = await self.collection.aggregate(pipeline).to_list(length=1)

        if not result:
            return FeedbackStats(total_count=0, up_count=0, down_count=0, up_percentage=0.0)

        stats = result[0]
        total = stats["total"]
        up_count = stats["up_count"]
        down_count = stats["down_count"]
        up_percentage = round((up_count / total) * 100, 1) if total > 0 else 0.0

        return FeedbackStats(
            total_count=total,
            up_count=up_count,
            down_count=down_count,
            up_percentage=up_percentage,
        )
