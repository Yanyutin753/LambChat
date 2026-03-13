"""
OpenViking 多租户用户管理

为每个 LambChat 用户自动创建对应的 OpenViking 账户和用户。
使用 LambChat user_id 作为 OpenViking account_id，确保数据隔离。

设计：
- 首次访问时自动创建账户（account_id = user_id）
- 账户创建时同时创建 admin 用户（user_id = user_id）
- 存储用户 API key 映射（MongoDB 持久化 + Redis 缓存 + 本地缓存）
- 每个用户使用自己的 API key 访问 OpenViking
"""

import logging
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel

from src.kernel.config import settings

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection

logger = logging.getLogger(__name__)

# 本地缓存（user_id -> api_key）
_API_KEY_CACHE: dict[str, str] = {}

# Redis keys
_REDIS_API_KEY_HASH = "openviking:user_api_keys"


class OpenVikingUser(BaseModel):
    """OpenViking 用户记录"""

    user_id: str
    account_id: str
    api_key: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OpenVikingUserStorage:
    """
    OpenViking 用户存储

    使用 MongoDB 持久化，Redis 作为缓存层。
    """

    def __init__(self, collection_name: str = "openviking_users"):
        self.collection_name = collection_name
        self._collection: Optional["AsyncIOMotorCollection[Any]"] = None

    @property
    def collection(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[self.collection_name]
        return self._collection

    async def _get_redis(self):
        """获取 Redis 客户端。"""
        try:
            from redis.asyncio import Redis

            from src.infra.storage.redis import get_redis_client

            client: Redis = get_redis_client()
            await client.ping()  # type: ignore[misc]
            return client
        except Exception:
            return None

    async def get_api_key(self, user_id: str) -> Optional[str]:
        """
        获取用户的 OpenViking API key。

        查询顺序：本地缓存 -> Redis -> MongoDB

        Args:
            user_id: LambChat 用户 ID

        Returns:
            OpenViking API key，如果不存在返回 None
        """
        # 1. 本地缓存快路径
        if user_id in _API_KEY_CACHE:
            return _API_KEY_CACHE[user_id]

        # 2. Redis 缓存
        redis = await self._get_redis()
        if redis:
            try:
                api_key = await redis.hget(_REDIS_API_KEY_HASH, user_id)
                if api_key:
                    _API_KEY_CACHE[user_id] = api_key
                    return api_key
            except Exception as e:
                logger.debug("[OpenViking] Redis hget failed: %s", e)

        # 3. MongoDB 持久化存储
        try:
            doc = await self.collection.find_one({"user_id": user_id})
            if doc:
                api_key = doc.get("api_key")
                if api_key:
                    # 回填缓存
                    _API_KEY_CACHE[user_id] = api_key
                    if redis:
                        try:
                            await redis.hset(_REDIS_API_KEY_HASH, user_id, api_key)
                        except Exception:
                            pass
                    return api_key
        except Exception as e:
            logger.warning("[OpenViking] MongoDB query failed: %s", e)

        return None

    async def store_api_key(self, user_id: str, account_id: str, api_key: str) -> bool:
        """
        存储用户的 OpenViking API key。

        同时写入 MongoDB（持久化）、Redis（缓存）、本地缓存。

        Args:
            user_id: LambChat 用户 ID
            account_id: OpenViking 账户 ID
            api_key: OpenViking API key

        Returns:
            是否存储成功
        """
        now = datetime.now()

        # 1. 写入 MongoDB（持久化）
        try:
            doc = {
                "user_id": user_id,
                "account_id": account_id,
                "api_key": api_key,
                "updated_at": now,
            }
            await self.collection.update_one(
                {"user_id": user_id},
                {
                    "$set": doc,
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        except Exception as e:
            logger.error("[OpenViking] MongoDB write failed: %s", e)
            return False

        # 2. 写入 Redis 缓存
        redis = await self._get_redis()
        if redis:
            try:
                await redis.hset(_REDIS_API_KEY_HASH, user_id, api_key)
            except Exception as e:
                logger.debug("[OpenViking] Redis hset failed: %s", e)

        # 3. 写入本地缓存
        _API_KEY_CACHE[user_id] = api_key

        return True


@lru_cache
def get_openviking_user_storage() -> OpenVikingUserStorage:
    """获取 OpenViking 用户存储实例（单例）"""
    return OpenVikingUserStorage()


async def get_user_api_key(user_id: str) -> Optional[str]:
    """
    获取用户的 OpenViking API key。

    Args:
        user_id: LambChat 用户 ID

    Returns:
        OpenViking API key，如果不存在返回 None
    """
    storage = get_openviking_user_storage()
    return await storage.get_api_key(user_id)


async def _store_user_api_key(user_id: str, account_id: str, api_key: str) -> bool:
    """存储用户的 OpenViking API key。"""
    storage = get_openviking_user_storage()
    return await storage.store_api_key(user_id, account_id, api_key)


async def ensure_user_account(user_id: str) -> tuple[bool, Optional[str]]:
    """
    确保用户的 OpenViking 账户存在，返回其 API key。

    如果账户不存在，自动创建：
    - account_id = user_id
    - admin_user_id = user_id

    Args:
        user_id: LambChat 用户 ID

    Returns:
        (success, api_key) - success 为 True 表示账户存在或创建成功，
        api_key 为用户的 OpenViking API key
    """
    if not settings.ENABLE_OPENVIKING:
        return False, None

    if not user_id:
        logger.warning("[OpenViking] user_id is empty, skipping account creation")
        return False, None

    # 检查是否已有 API key
    existing_key = await get_user_api_key(user_id)
    if existing_key:
        logger.debug("[OpenViking] Using cached API key for user: %s", user_id)
        return True, existing_key

    try:
        from src.infra.openviking.client import get_openviking_client

        # 使用 root client 创建账户
        root_client = await get_openviking_client()
        if root_client is None:
            logger.warning("[OpenViking] Root client unavailable, cannot create account")
            return False, None

        logger.info("[OpenViking] Creating account for user: %s", user_id)

        # 尝试创建账户（account_id = user_id, admin_user_id = user_id）
        result = await root_client.admin_create_account(
            account_id=user_id,
            admin_user_id=user_id,
        )

        logger.debug("[OpenViking] admin_create_account result: %s", result)

        if result:
            api_key = result.get("user_key")
            if api_key:
                success = await _store_user_api_key(user_id, user_id, api_key)
                if success:
                    logger.info("[OpenViking] Account created for user: %s", user_id)
                    return True, api_key
                else:
                    logger.warning("[OpenViking] Failed to store API key for user: %s", user_id)
            else:
                logger.warning("[OpenViking] No user_key in create_account result: %s", result)

    except Exception as e:
        error_msg = str(e)
        logger.warning(
            "[OpenViking] admin_create_account failed for user %s: %s", user_id, error_msg
        )

        # 账户已存在 - 尝试重新生成 API key
        lower_msg = error_msg.lower()
        is_duplicate = "already exists" in lower_msg or "duplicate" in lower_msg
        logger.info(
            "[OpenViking] Duplicate check: is_duplicate=%s, lower_msg='%s'", is_duplicate, lower_msg
        )

        if is_duplicate:
            try:
                logger.info("[OpenViking] Account exists, regenerating key for user: %s", user_id)
                if root_client is None:
                    logger.warning("[OpenViking] Root client is None, cannot regenerate key")
                    return False, None
                result = await root_client.admin_regenerate_key(user_id, user_id)
                logger.info("[OpenViking] admin_regenerate_key result: %s", result)
                api_key = result.get("api_key") or result.get("user_key")
                if api_key:
                    success = await _store_user_api_key(user_id, user_id, api_key)
                    if success:
                        logger.info("[OpenViking] API key regenerated for user: %s", user_id)
                        return True, api_key
                    else:
                        logger.warning(
                            "[OpenViking] Failed to store regenerated key for user: %s", user_id
                        )
                else:
                    logger.warning("[OpenViking] No api_key in regenerate result: %s", result)
            except Exception as regen_error:
                logger.warning("[OpenViking] Failed to regenerate key: %s", regen_error)

        logger.warning("[OpenViking] Failed to create account for user %s: %s", user_id, e)

    return False, None


def get_user_memory_uri(user_id: str) -> str:
    """
    获取用户记忆的 Viking URI。

    注意：
    - viking://user/{user_id}/memories/ 是 OpenViking 自动管理的用户记忆
    - viking://resources/users/{user_id}/memories/ 是手动保存的用户资源

    Args:
        user_id: LambChat 用户 ID（也是 OpenViking user_id）

    Returns:
        viking://user/{user_id}/memories/ (用于检索自动提取的记忆)
    """
    return f"viking://user/{user_id}/memories/"


def get_user_resource_uri(user_id: str) -> str:
    """
    获取用户资源的 Viking URI。

    用于手动保存资源（如 save_memory 工具）。

    Args:
        user_id: LambChat 用户 ID

    Returns:
        viking://resources/users/{user_id}/memories/
    """
    return f"viking://resources/users/{user_id}/memories/"


async def invalidate_user_cache(user_id: str) -> None:
    """
    清除用户的 API key 缓存（包括 MongoDB 持久化记录）。

    当检测到 API key 无效时调用，强制下次重新创建账户。

    Args:
        user_id: 用户 ID
    """
    global _API_KEY_CACHE

    # 1. 清除本地缓存
    if user_id in _API_KEY_CACHE:
        del _API_KEY_CACHE[user_id]

    # 2. 清除 Redis 缓存
    try:
        storage = get_openviking_user_storage()
        redis = await storage._get_redis()
        if redis:
            await redis.hdel(_REDIS_API_KEY_HASH, user_id)
    except Exception as e:
        logger.debug("[OpenViking] Failed to clear Redis cache: %s", e)

    # 3. 清除 MongoDB 持久化记录
    try:
        storage = get_openviking_user_storage()
        await storage.collection.delete_one({"user_id": user_id})
        logger.debug("[OpenViking] MongoDB record deleted for user: %s", user_id)
    except Exception as e:
        logger.debug("[OpenViking] Failed to delete MongoDB record: %s", e)

    # 4. 清除用户客户端缓存
    from src.infra.openviking.client import _invalidate_user_client

    await _invalidate_user_client(user_id)

    logger.info("[OpenViking] All caches invalidated for user: %s", user_id)
