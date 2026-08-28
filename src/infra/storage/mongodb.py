"""
MongoDB 存储实现
"""

import asyncio
import fnmatch
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import BaseModel
from pymongo import ReturnDocument

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.pubsub_hub import get_pubsub_hub
from src.infra.storage.base import StorageBase
from src.infra.storage.redis import get_redis_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

logger = get_logger(__name__)
MONGODB_STORAGE_KEYS_LIMIT = 1000
APPROVAL_RESPONSE_CHANNEL = "approval:response"


def build_mongo_connection_string() -> str:
    """Construct a MongoDB connection string from current settings.

    Shared by the motor async client and the synchronous checkpointer client so
    both resolve identical credentials / ``authSource`` / scheme handling. Pure
    function over ``settings`` — no IO — so it composes with any caller.
    """
    from urllib.parse import quote_plus

    base_url = settings.MONGODB_URL
    username = settings.MONGODB_USERNAME
    password = settings.MONGODB_PASSWORD
    auth_source = settings.MONGODB_AUTH_SOURCE

    if not (username and password):
        return base_url

    if base_url.startswith("mongodb://"):
        scheme, rest = "mongodb://", base_url[len("mongodb://") :]
    elif base_url.startswith("mongodb+srv://"):
        scheme, rest = "mongodb+srv://", base_url[len("mongodb+srv://") :]
    else:
        # Unknown scheme: don't risk injecting creds into a string we don't understand.
        return base_url

    encoded_user = quote_plus(username)
    encoded_pass = quote_plus(password)
    return f"{scheme}{encoded_user}:{encoded_pass}@{rest}?authSource={auth_source}"


@lru_cache
def get_mongo_client() -> "AsyncIOMotorClient":
    """获取 MongoDB 客户端（单例）- 使用 Motor 异步客户端"""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        connection_string = build_mongo_connection_string()

        client: AsyncIOMotorClient = AsyncIOMotorClient(
            connection_string,
            maxPoolSize=settings.MONGODB_POOL_MAX_SIZE,
            minPoolSize=settings.MONGODB_POOL_MIN_SIZE,
            connectTimeoutMS=5000,
            serverSelectionTimeoutMS=10000,
            tz_aware=True,
            tzinfo=timezone.utc,
        )
        return client
    except ImportError:
        raise ImportError("请安装 motor: pip install motor")


async def close_mongo_client() -> None:
    """关闭 MongoDB 连接池"""
    try:
        if get_mongo_client.cache_info().currsize == 0:
            return
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
            from datetime import timedelta

            doc["expires_at"] = utc_now() + timedelta(seconds=ttl)
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
        """获取匹配的键列表，默认限制数量避免误扫全库。"""
        regex = fnmatch.translate(pattern)
        cursor = self.collection.find({"_id": {"$regex": regex}}, {"_id": 1}).limit(
            MONGODB_STORAGE_KEYS_LIMIT
        )
        return [doc["_id"] async for doc in cursor]


# ============================================================================
# 审批存储 (Human-in-the-Loop)
# ============================================================================

# 默认过期时间 (秒)
APPROVAL_TTL = 3600  # 1 hour


def _not_expired_query() -> dict:
    """未过期判定：expires_at 大于当前时间，或未设置（interrupt 模式审批无超时）。"""
    return {"$or": [{"expires_at": {"$gt": utc_now()}}, {"expires_at": None}]}


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
    metadata: Optional[dict] = None  # structured data for specialized rendering


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
        # _id already has a unique index by default, no need to recreate

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

    async def create(
        self, approval: PendingApproval, ttl: int | None = APPROVAL_TTL
    ) -> PendingApproval:
        """创建审批记录

        Args:
            approval: 审批对象
            ttl: 过期秒数；None 表示不过期（interrupt 模式无超时，
                响应后由 expire_after 设置 GC 时间）
        """
        await self.ensure_indexes()
        now = utc_now()
        doc = approval.model_dump()
        doc["_id"] = approval.id
        doc["created_at"] = now
        doc["expires_at"] = now + timedelta(seconds=ttl) if ttl is not None else None

        await self.collection.insert_one(doc)
        return approval

    async def get(self, approval_id: str) -> Optional[PendingApproval]:
        """获取审批记录（排除 response 子文档，减少传输量）"""
        doc = await self.collection.find_one(
            {"_id": approval_id, **_not_expired_query()},
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
        update_doc = {"status": status, "updated_at": utc_now()}
        if response:
            update_doc["response"] = response.model_dump()

        result = await self.collection.update_one({"_id": approval_id}, {"$set": update_doc})
        return result.modified_count > 0

    async def respond_if_pending(
        self,
        approval_id: str,
        status: str,
        response: ApprovalResponse,
    ) -> Optional[PendingApproval]:
        """Atomically mark a pending approval as responded."""
        update_doc = {
            "status": status,
            "updated_at": utc_now(),
            "response": response.model_dump(),
        }
        doc = await self.collection.find_one_and_update(
            {
                "_id": approval_id,
                "status": "pending",
                **_not_expired_query(),
            },
            {"$set": update_doc},
            projection={"response": 0},
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return None
        doc.pop("_id", None)
        return PendingApproval(**doc)

    async def respond_if_pending_with_metadata(
        self,
        approval_id: str,
        status: str,
        response: ApprovalResponse,
        metadata_updates: dict[str, Any],
    ) -> Optional[PendingApproval]:
        """Atomically respond and bind a prepared distributed resume attempt."""
        update_doc: dict[str, Any] = {
            "status": status,
            "updated_at": utc_now(),
            "response": response.model_dump(),
        }
        for key, value in metadata_updates.items():
            update_doc[f"metadata.{key}"] = value
        doc = await self.collection.find_one_and_update(
            {
                "_id": approval_id,
                "status": "pending",
                **_not_expired_query(),
            },
            {"$set": update_doc},
            projection={"response": 0},
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return None
        doc.pop("_id", None)
        return PendingApproval(**doc)

    async def restore_pending_if_status(self, approval_id: str, status: str) -> bool:
        """Restore a claimed interrupt approval when resume submission fails."""
        doc = await self.collection.find_one_and_update(
            {"_id": approval_id, "status": status},
            {
                "$set": {"status": "pending"},
                "$unset": {"response": "", "updated_at": ""},
            },
        )
        return doc is not None

    async def expire_after(self, approval_id: str, seconds: int = 3600) -> bool:
        """响应/取消后设置 GC 过期时间（interrupt 审批创建时不过期）。"""
        result = await self.collection.update_one(
            {"_id": approval_id},
            {
                "$set": {
                    "expires_at": utc_now() + timedelta(seconds=seconds),
                }
            },
        )
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
        created_at = doc.get("created_at", utc_now())
        current_expires = doc.get("expires_at", utc_now())

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
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[PendingApproval]:
        """获取待处理审批列表"""
        query = {"status": "pending", **_not_expired_query()}
        if session_id:
            query["session_id"] = session_id
        if user_id:
            query["user_id"] = user_id

        bounded_limit = max(1, min(int(limit), 100))
        cursor = self.collection.find(query).sort("created_at", -1).limit(bounded_limit)
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


def close_approval_storage() -> None:
    """Release cached approval storage without creating it during shutdown."""
    get_approval_storage.cache_clear()


# ============================================================================
# 分布式通知 (Redis Pub/Sub + MongoDB 轮询兜底)
# ============================================================================


async def notify_approval_response(approval_id: str, response: ApprovalResponse) -> None:
    """
    通知等待的 Agent 审批已响应

    响应主体仍以 MongoDB 为准；Redis Pub/Sub 只负责唤醒跨实例等待者。
    """
    try:
        redis_client = get_redis_client()
        payload = await run_blocking_io(json.dumps, {"approval_id": approval_id})
        await redis_client.publish(
            APPROVAL_RESPONSE_CHANNEL,
            payload,
        )
    except Exception as e:
        logger.warning("Failed to publish approval response notification: %s", e)


# 静态订阅的等待者注册表：approval_id -> 等待事件集合。
# 订阅/退订频道会让共享 pubsub hub 重启整条连接（窗口内所有频道消息丢失），
# 因此频道只订阅一次，由 handler 按 approval_id 分发唤醒。
_approval_waiters_lock = asyncio.Lock()
_approval_waiters: dict[str, set[asyncio.Event]] = {}
_approval_channel_subscribed = False


async def _reset_approval_notification_state() -> None:
    """测试辅助：清空静态订阅状态与等待者。"""
    global _approval_channel_subscribed
    async with _approval_waiters_lock:
        _approval_waiters.clear()
        _approval_channel_subscribed = False


async def _on_approval_response_message(message: dict[str, Any]) -> None:
    try:
        data = await run_blocking_io(json.loads, message.get("data") or "{}")
    except json.JSONDecodeError:
        logger.warning("Invalid approval response notification: %s", message.get("data"))
        return
    approval_id = data.get("approval_id")
    if not approval_id:
        return
    async with _approval_waiters_lock:
        events = list(_approval_waiters.get(approval_id, ()))
    for event in events:
        event.set()


async def _ensure_approval_channel_subscribed() -> bool:
    """确保审批频道已静态订阅；失败时返回 False（等待方退化为 Mongo 轮询兜底）。"""
    global _approval_channel_subscribed
    async with _approval_waiters_lock:
        if _approval_channel_subscribed:
            return True
    try:
        hub = get_pubsub_hub()
        hub.subscribe(APPROVAL_RESPONSE_CHANNEL, _on_approval_response_message)
        await hub.start()
    except Exception as e:
        logger.warning("Failed to subscribe approval response notifications: %s", e)
        return False
    async with _approval_waiters_lock:
        _approval_channel_subscribed = True
    return True


async def wait_for_response_distributed(
    approval_id: str,
    timeout: float = 300,
) -> Optional[ApprovalResponse]:
    """
    等待审批响应 (Redis Pub/Sub 唤醒 + MongoDB 轮询兜底)

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
    notification_event = asyncio.Event()

    # 先注册等待者再订阅：hub.start() 可能在订阅完成前即投递消息。
    async with _approval_waiters_lock:
        _approval_waiters.setdefault(approval_id, set()).add(notification_event)
    await _ensure_approval_channel_subscribed()

    try:
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                return None

            # 轻量检查：只查 response 字段是否存在
            if await storage.has_response(approval_id):
                return await storage.get_response(approval_id)

            remaining = timeout - elapsed
            wait_interval = min(current_interval, remaining)
            if wait_interval <= 0:
                return None

            try:
                await asyncio.wait_for(notification_event.wait(), timeout=wait_interval)
            except asyncio.TimeoutError:
                current_interval = min(current_interval * 1.5, max_interval)
                continue

            notification_event.clear()
            response = await storage.get_response(approval_id)
            if response:
                return response
    finally:
        async with _approval_waiters_lock:
            events = _approval_waiters.get(approval_id)
            if events is not None:
                events.discard(notification_event)
                if not events:
                    _approval_waiters.pop(approval_id, None)
