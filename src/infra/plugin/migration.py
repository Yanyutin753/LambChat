"""旧技能商店 → 插件中心 幂等迁移。

skill_marketplace 中的每个技能在 plugins 中无同名文档时，创建一个
单技能插件（状态对齐 is_active，保留 created_by，标记 migrated_from），
并把 skill_marketplace_files 复制到 plugin_files。原集合只读保留，
旧 API 与已安装技能不受影响。
"""

from src.infra.logging import get_logger
from src.infra.plugin.constants import (
    PLUGIN_FILES_COLLECTION,
    PLUGIN_MIGRATION_SCAN_LIMIT,
)
from src.infra.plugin.types import PluginStatus
from src.infra.skill.constants import (
    SKILL_MARKETPLACE_COLLECTION,
    SKILL_MARKETPLACE_FILES_COLLECTION,
)

logger = get_logger(__name__)

_FILE_COPY_BATCH = 100


async def migrate_skill_marketplace_to_plugins(
    *,
    plugins_collection,
    marketplace_collection,
    marketplace_files_collection,
    plugin_files_collection,
) -> int:
    """执行迁移，返回新迁移的插件数（已存在同名的跳过，幂等）。"""
    migrated = 0
    cursor = marketplace_collection.find(
        {}, {"skill_name": 1, "description": 1, "tags": 1, "is_active": 1, "created_by": 1}
    ).limit(PLUGIN_MIGRATION_SCAN_LIMIT)
    async for doc in cursor:
        skill_name = doc.get("skill_name")
        if not skill_name:
            continue
        existing = await plugins_collection.find_one({"name": skill_name}, {"_id": 1})
        if existing:
            continue

        plugin_doc = {
            "name": skill_name,
            "display_name": "",
            "description": doc.get("description", ""),
            "version": "1.0.0",
            "author_name": "",
            "tags": doc.get("tags", []),
            "skills": [
                {
                    "skill_name": skill_name,
                    "description": doc.get("description", ""),
                    "tags": doc.get("tags", []),
                }
            ],
            "mcp_servers": [],
            "persona": None,
            "status": PluginStatus.ACTIVE.value
            if doc.get("is_active", True)
            else PluginStatus.DEACTIVATED.value,
            "created_by": doc.get("created_by"),
            "install_count": 0,
            "migrated_from": "skill_marketplace",
        }
        try:
            await plugins_collection.insert_one(plugin_doc)
        except Exception as e:  # 并发启动的重复插入：跳过即可
            logger.warning("[Plugin] Migration race on %s skipped: %s", skill_name, e)
            continue

        file_cursor = marketplace_files_collection.find({"skill_name": skill_name}).batch_size(
            _FILE_COPY_BATCH
        )
        async for file_doc in file_cursor:
            await plugin_files_collection.update_one(
                {
                    "plugin_name": skill_name,
                    "skill_name": skill_name,
                    "file_path": file_doc["file_path"],
                },
                {"$setOnInsert": {"content": file_doc.get("content", "")}},
                upsert=True,
            )
        migrated += 1

    if migrated:
        logger.info("[Plugin] Migrated %d marketplace skill(s) to plugins", migrated)
    return migrated


async def _run_migration_with_collections(plugins_collection) -> int:
    from src.infra.storage.mongodb import get_mongo_client
    from src.kernel.config import settings

    client = get_mongo_client()
    db = client[settings.MONGODB_DB]
    return await migrate_skill_marketplace_to_plugins(
        plugins_collection=plugins_collection,
        marketplace_collection=db[SKILL_MARKETPLACE_COLLECTION],
        marketplace_files_collection=db[SKILL_MARKETPLACE_FILES_COLLECTION],
        plugin_files_collection=db[PLUGIN_FILES_COLLECTION],
    )
