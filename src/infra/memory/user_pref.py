"""用户级记忆开关（默认开启）。

存 users.metadata.memoryEnabled（个人设置 → ProfilePreferencesTab）。
语义：关闭 = 不自动捕获、不注入索引/查询上下文、记忆工具不可用；
面板的手动管理（查看/编辑/删除/导出）不受影响，数据保留，随时可再开。
总开关 ENABLE_MEMORY（管理员）优先：服务器关闭时对所有人关闭。
查找失败 fail-open（默认开启），TTL 缓存 30s 使开关≤30s 生效。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.kernel.config import settings

logger = logging.getLogger(__name__)

PREF_CACHE_TTL_SECONDS = 30
_pref_cache: dict[str, tuple[datetime, bool]] = {}


def _get_users_collection():
    from src.infra.storage.mongodb import get_mongo_client

    client = get_mongo_client()
    return client[settings.MONGODB_DB]["users"]


async def user_memory_enabled(user_id: str) -> bool:
    """该用户的记忆功能是否开启（缺省/异常=开启）。"""
    if not user_id:
        return True
    now = datetime.now(timezone.utc)
    cached = _pref_cache.get(user_id)
    if cached and (now - cached[0]).total_seconds() < PREF_CACHE_TTL_SECONDS:
        return cached[1]
    enabled = True
    try:
        from bson import ObjectId
        from bson.errors import InvalidId

        try:
            query: dict = {"_id": ObjectId(user_id)}
        except InvalidId:
            query = {"_id": user_id}
        doc = await _get_users_collection().find_one(query, {"metadata.memoryEnabled": 1})
        if doc is not None:
            metadata = doc.get("metadata") or {}
            value = metadata.get("memoryEnabled")
            if isinstance(value, bool):
                enabled = value
    except Exception as e:
        logger.debug("[MemoryUserPref] lookup failed, defaulting enabled: %s", e)
        enabled = True
    _pref_cache[user_id] = (now, enabled)
    return enabled
