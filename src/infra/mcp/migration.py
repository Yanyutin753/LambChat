"""旧 SHA256 加密数据迁移到 PBKDF2。

扫描 MCP 服务器集合（system_mcp_servers / user_mcp_servers）的敏感字段
（env / headers），把仍用旧版 SHA256 密钥加密的记录用新 PBKDF2 密钥重写。

设计要点：
- 不动解密热路径（decrypt_value 仍支持旧密钥回退），仅在启动时后台批量重写。
- 通过 is_legacy_encrypted 精确识别旧密钥记录，避免对已迁移或明文数据做无谓重写。
- 硬过期开关由 MCP_ENCRYPTION_DISABLE_LEGACY 控制（默认 False=仅警告，True=禁用回退），
  管理员确认迁移完成后手动开启，此后旧密钥数据将被拒绝解密。
- 并发前提：本迁移设计为单实例运行。多副本部署时迁移幂等（旧密钥→新密钥，
  重写后 is_legacy_encrypted 返回 False 自动跳过），最坏情况仅重复重写、不损坏数据；
  若需强一致可在外层加分布式锁（Redis SET NX EX）。
"""

from __future__ import annotations

import time
from typing import Any

from src.infra.logging import get_logger
from src.infra.mcp.encryption import (
    decrypt_value,
    encrypt_value,
    is_legacy_encrypted,
)
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)

# 迁移目标：(集合名, 加密字段列表)
# 当前覆盖 MCP 服务器（审计核心）。其他用 encryption 的集合
# （channels / models / envvars / feishu）后续按需追加同样的 (collection, fields) 条目。
MIGRATION_TARGETS: list[tuple[str, list[str]]] = [
    ("system_mcp_servers", ["env", "headers"]),
    ("user_mcp_servers", ["env", "headers"]),
]


async def migrate_legacy_encryption() -> dict[str, int]:
    """扫描所有迁移目标，把旧密钥加密字段重写为新密钥。返回统计。"""
    start = time.monotonic()
    stats = {"scanned": 0, "migrated": 0, "errors": 0}
    try:
        client = get_mongo_client()
        db = client[settings.MONGODB_DB]
    except Exception as e:
        logger.error("[encryption-migration] 无法连接 MongoDB: %s", e)
        return stats

    for collection_name, fields in MIGRATION_TARGETS:
        collection = db[collection_name]
        try:
            cursor = collection.find({})
            async for doc in cursor:
                stats["scanned"] += 1
                updates: dict[str, Any] = {}
                for field in fields:
                    value = doc.get(field)
                    if is_legacy_encrypted(value):
                        try:
                            plaintext = decrypt_value(value)
                            reencrypted = encrypt_value(plaintext)
                            if reencrypted is not None:
                                updates[field] = reencrypted
                        except Exception as e:
                            stats["errors"] += 1
                            logger.warning(
                                "[encryption-migration] %s/%s 字段 %s 解密重写失败: %s",
                                collection_name,
                                doc.get("_id"),
                                field,
                                e,
                            )
                if updates:
                    try:
                        await collection.update_one({"_id": doc["_id"]}, {"$set": updates})
                        stats["migrated"] += 1
                    except Exception as e:
                        stats["errors"] += 1
                        logger.warning(
                            "[encryption-migration] 更新 %s/%s 失败: %s",
                            collection_name,
                            doc.get("_id"),
                            e,
                        )
        except Exception as e:
            logger.error("[encryption-migration] 扫描集合 %s 失败: %s", collection_name, e)

    elapsed = time.monotonic() - start
    logger.info("[encryption-migration] 迁移完成: %s（耗时 %.2fs）", stats, elapsed)
    return stats
