"""
用户环境变量存储

存储用户的环境变量（加密），用于注入到沙箱中。
- MongoDB 集合: user_env_vars
- 每条记录: {user_id, key, value(加密), created_at, updated_at}
- 唯一索引: (user_id, key)
- 复用 MCP 加密模块 encrypt_value / decrypt_value
"""

import asyncio
from typing import Any, Optional

from pymongo import UpdateOne

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.infra.utils.datetime import utc_now_iso
from src.kernel.config import settings
from src.kernel.schemas.envvar import EnvVarResponse

logger = get_logger(__name__)

# MongoDB 集合名
COLLECTION_NAME = "user_env_vars"

# 每用户最大环境变量数量
MAX_ENV_VARS_PER_USER = 50
ENV_VAR_MAX_VALUE_CHARS = 16_000
ENV_VAR_MAX_TOTAL_VALUE_CHARS = 64_000


def _validate_env_var_value_size(value: str) -> None:
    if len(str(value)) > ENV_VAR_MAX_VALUE_CHARS:
        raise ValueError(f"Environment variable value too large (max {ENV_VAR_MAX_VALUE_CHARS})")


def _validate_env_var_bulk_value_size(variables: dict[str, str]) -> None:
    total_chars = 0
    for value in variables.values():
        text = str(value)
        if len(text) > ENV_VAR_MAX_VALUE_CHARS:
            raise ValueError(
                f"Environment variable value too large (max {ENV_VAR_MAX_VALUE_CHARS})"
            )
        total_chars += len(text)
        if total_chars > ENV_VAR_MAX_TOTAL_VALUE_CHARS:
            raise ValueError(
                "Environment variable values too large "
                f"(max {ENV_VAR_MAX_TOTAL_VALUE_CHARS} total characters)"
            )


class EnvVarStorage:
    """用户环境变量存储（加密）"""

    _index_task: asyncio.Task[None] | None = None
    _index_ensured = False

    def __init__(self):
        self._collection: Any = None

    @property
    def _coll(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[COLLECTION_NAME]
            self._schedule_index()
        return self._collection

    def _schedule_index(self) -> None:
        cls = type(self)
        if cls._index_ensured:
            return
        task = cls._index_task
        if task is not None and not task.done():
            return
        try:
            task = asyncio.create_task(self._ensure_index())
        except RuntimeError:
            return
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        cls._index_task = task
        cls._index_ensured = True

    async def _ensure_index(self):
        """创建唯一索引 (user_id + key)"""
        try:
            await self._coll.create_index(
                [("user_id", 1), ("key", 1)],
                unique=True,
                name="user_id_key_unique_idx",
                background=True,
            )
        except Exception as e:
            logger.warning(f"Failed to create index on {COLLECTION_NAME}: {e}")

    # ── 加密辅助 ──────────────────────────────────────────────────

    @staticmethod
    async def _encrypt_value(value: str) -> dict:
        """加密单个值（包装为 dict 后加密）"""
        return await run_blocking_io(encrypt_value, {"v": value})

    @staticmethod
    async def _decrypt_value(encrypted: Any) -> str:
        """解密单个值"""
        result = await run_blocking_io(decrypt_value, encrypted)
        if isinstance(result, dict):
            return result.get("v", "")
        return str(result) if result else ""

    # ── CRUD ──────────────────────────────────────────────────────

    async def list_vars(self, user_id: str) -> list[EnvVarResponse]:
        """列出用户所有环境变量（value 掩码）"""
        cursor = (
            self._coll.find(
                {"user_id": user_id},
                {"_id": 0, "user_id": 0},
            )
            .sort("key", 1)
            .limit(MAX_ENV_VARS_PER_USER)
        )
        results = []
        async for doc in cursor:
            results.append(
                EnvVarResponse(
                    key=doc["key"],
                    value="***",  # 掩码
                    created_at=doc.get("created_at"),
                    updated_at=doc.get("updated_at"),
                )
            )
        return results

    async def get_var(self, user_id: str, key: str) -> Optional[EnvVarResponse]:
        """获取单个环境变量（明文）"""
        doc = await self._coll.find_one(
            {"user_id": user_id, "key": key},
            {"_id": 0, "user_id": 0},
        )
        if not doc:
            return None
        return EnvVarResponse(
            key=doc["key"],
            value=await self._decrypt_value(doc.get("value")),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )

    async def get_decrypted_vars(self, user_id: str) -> dict[str, str]:
        """获取用户所有环境变量的明文 dict（供沙箱注入）"""
        cursor = self._coll.find(
            {"user_id": user_id},
            {"_id": 0, "key": 1, "value": 1},
        ).limit(MAX_ENV_VARS_PER_USER)
        result = {}
        async for doc in cursor:
            try:
                result[doc["key"]] = await self._decrypt_value(doc.get("value"))
            except Exception as e:
                logger.warning(f"Failed to decrypt env var '{doc['key']}' for user {user_id}: {e}")
        return result

    async def set_var(self, user_id: str, key: str, value: str) -> EnvVarResponse:
        """设置（upsert）单个环境变量"""
        _validate_env_var_value_size(value)
        now = utc_now_iso()

        # 检查数量上限（仅 insert 时）
        existing = await self._coll.find_one({"user_id": user_id, "key": key})
        if not existing:
            count = await self._coll.count_documents({"user_id": user_id})
            if count >= MAX_ENV_VARS_PER_USER:
                raise ValueError(f"Maximum {MAX_ENV_VARS_PER_USER} environment variables per user")

        encrypted = await self._encrypt_value(value)
        await self._coll.update_one(
            {"user_id": user_id, "key": key},
            {
                "$set": {
                    "value": encrypted,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

        return EnvVarResponse(
            key=key,
            value="***",
            created_at=existing.get("created_at") if existing else now,
            updated_at=now,
        )

    async def set_vars_bulk(self, user_id: str, variables: dict[str, str]) -> int:
        """批量设置环境变量"""
        if len({key for key in variables if key}) > MAX_ENV_VARS_PER_USER:
            raise ValueError(
                f"Would exceed maximum {MAX_ENV_VARS_PER_USER} environment variables per user"
            )
        _validate_env_var_bulk_value_size(variables)

        now = utc_now_iso()

        # 检查数量上限
        current_count = await self._coll.count_documents({"user_id": user_id})
        existing_keys = set()
        existing_cursor = self._coll.find({"user_id": user_id}, {"key": 1}).limit(
            MAX_ENV_VARS_PER_USER
        )
        async for doc in existing_cursor:
            existing_keys.add(doc["key"])

        new_keys = set(variables.keys()) - existing_keys
        if current_count + len(new_keys) > MAX_ENV_VARS_PER_USER:
            raise ValueError(
                f"Would exceed maximum {MAX_ENV_VARS_PER_USER} environment variables per user"
            )

        items = list(variables.items())
        # Encrypt sequentially (do NOT gather) to preserve ordering with the
        # original per-key loop and keep the encryption offload points stable.
        encrypted_values = [await self._encrypt_value(value) for _, value in items]

        operations = [
            UpdateOne(
                {"user_id": user_id, "key": key},
                {
                    "$set": {
                        "value": encrypted,
                        "updated_at": now,
                    },
                    "$setOnInsert": {
                        "created_at": now,
                    },
                },
                upsert=True,
            )
            for (key, _), encrypted in zip(items, encrypted_values)
        ]

        if operations:
            await self._coll.bulk_write(operations, ordered=True)

        return len(operations)

    async def delete_var(self, user_id: str, key: str) -> bool:
        """删除单个环境变量"""
        result = await self._coll.delete_one({"user_id": user_id, "key": key})
        return result.deleted_count > 0

    async def delete_all_vars(self, user_id: str) -> int:
        """删除用户所有环境变量"""
        result = await self._coll.delete_many({"user_id": user_id})
        return result.deleted_count

    async def close(self) -> None:
        cls = type(self)
        task = cls._index_task
        cls._index_task = None
        cls._index_ensured = False
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._collection = None
