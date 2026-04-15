"""
MongoDB 存储实现
"""

import asyncio
from datetime import datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import BaseModel

from src.infra.logging import get_logger
from src.infra.storage.base import StorageBase
from src.kernel.config import settings

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

logger = get_logger(__name__)


@lru_cache
def get_mongo_client() -> "AsyncIOMotorClient":
    """获取 MongoDB 客户端（单例）- 使用 Motor 异步客户端"""
    try:
        from urllib.parse import quote_plus

        from motor.motor_asyncio import AsyncIOMotorClient

        base_url = settings.MONGODB_URL
        username = settings.MONGODB_USERNAME
        password = settings.MONGODB_PASSWORD
        auth_source = settings.MONGODB_AUTH_SOURCE

        if username and password:
            if base_url.startswith("mongodb://"):
                rest = base_url[len("mongodb://") :]
                encoded_user = quote_plus(username)
                encoded_pass = quote_plus(password)
                connection_string = (
                    f"mongodb://{encoded_user}:{encoded_pass}@{rest}?authSource={auth_source}"
                )
            elif base_url.startswith("mongodb+srv://"):
                rest = base_url[len("mongodb+srv://") :]
                encoded_user = quote_plus(username)
                encoded_pass = quote_plus(password)
                connection_string = (
                    f"mongodb+srv://{encoded_user}:{encoded_pass}@{rest}?authSource={auth_source}"
                )
            else:
                connection_string = base_url
        else:
            connection_string = base_url

        client: AsyncIOMotorClient = AsyncIOMotorClient(
            connection_string,
            maxPoolSize=20,
            minPoolSize=2,
            connectTimeoutMS=5000,
            serverSelectionTimeoutMS=10000,
        )
        return client
    except ImportError:
        raise ImportError("请安装 motor: pip install motor")


async def close_mongo_client() -> None:
    """关闭 MongoDB 连接池"""
    try:
        client = get_mongo_client()
        client.close()
        get_mongo_client.cache_clear()
        logger.info("MongoDB client closed")
    except Exception as e:
        logger.warning(f"Error closing MongoDB client: {e}")


class MongoDBStorage(StorageBase):
    """
    MongoDB 存储实现
    """

    def __init__(self, collection_name: str = "storage"):
        self.collection_name = collection_name
        self._collection: "AsyncIOMotorCollection[Any] | None" = None

    @property
    def collection(self):
        """延迟加载集合"""
        if self._collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[self.collection_name]
        return self._collection

    async def get(self, key: str) -> Optional[Any]:
        """获取数据"""
        result = await self.collection.find_one({"_id": key})
        if result:
            return result.get("value")
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置数据"""
        doc = {"_id": key, "value": value}
        if ttl:
            from datetime import datetime, timedelta

            doc["expires_at"] = datetime.now() + timedelta(seconds=ttl)
        await self.collection.update_one(
            {"_id": key},
            {"$set": doc},
            upsert=True,
        )

    async def delete(self, key: str) -> bool:
        """删除数据"""
        result = await self.collection.delete_one({"_id": key})
        return result.deleted_count > 0

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        result = await self.collection.find_one({"_id": key})
        return result is not None

    async def keys(self, pattern: str) -> list[str]:
        """获取匹配的键列表"""
        regex = pattern.replace("*", ".*")
        cursor = self.collection.find({"_id": {"$regex": regex}})
        return [doc["_id"] async for doc in cursor]


# ============================================================================
# 审批存储 (Human-in-the-Loop)
# ============================================================================

# 默认过期时间 (秒)
APPROVAL_TTL = 3600  # 1 hour


class PendingApproval(BaseModel):
    """待处理的审批请求"""

    id: str
    message: str
    type: str = "form"  # form-based approval
    fields: List[dict] = []  # 表单字段列表
    status: str = "pending"
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    extensions: int = 0


class ApprovalResponse(BaseModel):
    """审批响应"""

    approved: bool
    response: dict = {}  # 改为 dict 类型


class ApprovalStorage:
    """
    审批存储类

    使用 MongoDB 存储审批数据，支持分布式部署。
    """

    def __init__(self, collection_name: str = "approvals"):
        self.collection_name = collection_name
        self._collection: "AsyncIOMotorCollection[Any] | None" = None
        self._indexes_created = False

    @property
    def collection(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[self.collection_name]
        return self._collection

    async def ensure_indexes(self) -> None:
        """确保索引存在（幂等，可重复调用）"""
        if self._indexes_created:
            return
        coll = self.collection
        await coll.create_index("_id", unique=True, background=True)
        await coll.create_index(
            [("status", 1), ("expires_at", 1), ("user_id", 1)],
            background=True,
        )
        await coll.create_index(
            [("session_id", 1), ("status", 1)],
            background=True,
        )
        # TTL index: MongoDB 自动删除过期文档（兜底清理）
        await coll.create_index(
            "expires_at",
            expireAfterSeconds=0,
            background=True,
        )
        self._indexes_created = True

    async def create(self, approval: PendingApproval, ttl: int = APPROVAL_TTL) -> PendingApproval:
        """创建审批记录"""
        await self.ensure_indexes()
        now = datetime.now()
        doc = approval.model_dump()
        doc["_id"] = approval.id
        doc["created_at"] = now
        doc["expires_at"] = now + timedelta(seconds=ttl)

        await self.collection.insert_one(doc)
        return approval

    async def get(self, approval_id: str) -> Optional[PendingApproval]:
        """获取审批记录（排除 response 子文档，减少传输量）"""
        doc = await self.collection.find_one(
            {"_id": approval_id, "expires_at": {"$gt": datetime.now()}},
            {"response": 0},
        )
        if not doc:
            return None
        doc.pop("_id", None)
        return PendingApproval(**doc)

    async def update_status(
        self,
        approval_id: str,
        status: str,
        response: Optional[ApprovalResponse] = None,
    ) -> bool:
        """更新审批状态"""
        update_doc = {"status": status, "updated_at": datetime.now()}
        if response:
            update_doc["response"] = response.model_dump()

        result = await self.collection.update_one({"_id": approval_id}, {"$set": update_doc})
        return result.modified_count > 0

    async def extend_expires_at(
        self,
        approval_id: str,
        extra_seconds: int = 60,
        max_extensions: int = 10,
        max_total_seconds: int = 3600,
    ) -> Optional[datetime]:
        """
        延长审批过期时间（支持分布式）

        Args:
            approval_id: 审批 ID
            extra_seconds: 每次延长的秒数
            max_extensions: 最大延长次数
            max_total_seconds: 从创建时间起最大总有效时长

        Returns:
            新的 expires_at，或 None（已达上限）
        """
        doc = await self.collection.find_one({"_id": approval_id})
        if not doc:
            return None

        extensions = doc.get("extensions", 0)
        created_at = doc.get("created_at", datetime.now())
        current_expires = doc.get("expires_at", datetime.now())

        if extensions >= max_extensions:
            return None

        max_expires = created_at + timedelta(seconds=max_total_seconds)
        new_expires = min(current_expires + timedelta(seconds=extra_seconds), max_expires)

        if new_expires <= current_expires:
            return None

        await self.collection.update_one(
            {"_id": approval_id},
            {"$set": {"expires_at": new_expires, "extensions": extensions + 1}},
        )
        return new_expires

    async def delete(self, approval_id: str) -> bool:
        """删除审批记录"""
        result = await self.collection.delete_one({"_id": approval_id})
        return result.deleted_count > 0

    async def list_pending(
        self, session_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> List[PendingApproval]:
        """获取待处理审批列表"""
        query = {"status": "pending", "expires_at": {"$gt": datetime.now()}}
        if session_id:
            query["session_id"] = session_id
        if user_id:
            query["user_id"] = user_id

        cursor = self.collection.find(query).sort("created_at", -1)
        approvals = []
        async for doc in cursor:
            doc.pop("_id", None)
            approvals.append(PendingApproval(**doc))
        return approvals

    async def has_response(self, approval_id: str) -> bool:
        """检查是否已有响应（轻量投影，用于轮询）"""
        doc = await self.collection.find_one(
            {"_id": approval_id, "response": {"$exists": True}},
            {"response": 1},
        )
        return doc is not None

    async def get_response(self, approval_id: str) -> Optional[ApprovalResponse]:
        """获取审批响应（仅返回 response 子文档）"""
        doc = await self.collection.find_one(
            {"_id": approval_id},
            {"response": 1},
        )
        if not doc or "response" not in doc:
            return None
        response_data = doc["response"]
        if not isinstance(response_data, dict):
            return None
        return ApprovalResponse(**response_data)


@lru_cache
def get_approval_storage() -> ApprovalStorage:
    """获取审批存储实例（单例）"""
    return ApprovalStorage()


# ============================================================================
# 分布式通知 (仅使用 MongoDB 轮询)
# ============================================================================


async def notify_approval_response(approval_id: str, response: ApprovalResponse) -> None:
    """
    通知等待的 Agent 审批已响应

    仅使用 MongoDB 存储响应，wait_for_response 通过轮询检测变化。
    """
    # MongoDB 存储响应在 update_status 时已完成
    # 这里保留空实现以保持接口兼容性
    pass


async def wait_for_response_distributed(
    approval_id: str,
    timeout: float = 300,
) -> Optional[ApprovalResponse]:
    """
    等待审批响应 (仅使用 MongoDB 轮询，指数退避)

    Args:
        approval_id: 审批 ID
        timeout: 超时时间（秒）

    Returns:
        ApprovalResponse 或 None (超时)
    """
    storage = get_approval_storage()
    start_time = asyncio.get_event_loop().time()
    min_interval = 0.5
    max_interval = 3.0
    current_interval = min_interval

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout:
            return None

        # 轻量检查：只查 response 字段是否存在
        if await storage.has_response(approval_id):
            return await storage.get_response(approval_id)

        # 指数退避，上限 3 秒
        await asyncio.sleep(current_interval)
        current_interval = min(current_interval * 1.5, max_interval)
