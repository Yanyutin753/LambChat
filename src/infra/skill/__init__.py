"""
Skills 管理模块 - 简化架构
"""

from src.infra.skill.loader import load_skill_files
from src.infra.skill.manager import SkillManager
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.middleware import SkillsMiddleware
from src.infra.skill.storage import SkillStorage

__all__ = [
    "SkillManager",
    "SkillsMiddleware",
    "SkillStorage",
    "MarketplaceStorage",
    "load_skill_files",
]


async def init_skill_indexes() -> None:
    """初始化索引 + 旧版数据迁移（应用启动时调用一次，幂等）"""
    from src.infra.logging import get_logger
    from src.infra.storage.mongodb import get_mongo_client
    from src.kernel.config import settings

    logger = get_logger(__name__)

    storage = SkillStorage()
    marketplace = MarketplaceStorage()

    await storage.ensure_indexes()
    await marketplace.ensure_indexes()

    await storage.close()
    await marketplace.close()

    # 旧版数据迁移（幂等，旧集合为空时直接跳过）
    try:
        await _migrate_legacy_skills(logger)
    except Exception as e:
        logger.warning(f"Legacy skill migration failed (non-fatal): {e}")


async def _migrate_legacy_skills(logger) -> None:
    """将旧版 system_skills / user_skills / user_skill_preferences 迁移到新架构"""
    from src.infra.storage.mongodb import get_mongo_client
    from src.kernel.config import settings

    client = get_mongo_client()
    db = client[settings.MONGODB_DB]

    old_system = db["system_skills"]
    old_user = db["user_skills"]
    old_files = db["skill_files"]
    old_prefs = db["user_skill_preferences"]

    new_marketplace = db["skill_marketplace"]
    new_marketplace_files = db["skill_marketplace_files"]
    new_toggles = db["skill_toggles"]

    # 检查是否有旧数据需要迁移
    old_system_count = await old_system.count_documents({})
    old_prefs_count = await old_prefs.count_documents({})
    old_user_count = await old_user.count_documents({})

    if old_system_count == 0 and old_prefs_count == 0 and old_user_count == 0:
        return

    logger.info(
        f"Legacy skill data found: system_skills={old_system_count}, "
        f"user_skill_preferences={old_prefs_count}, user_skills={old_user_count}. "
        f"Starting migration..."
    )

    # 收集所有旧 system_skills 的名称
    system_skill_names: set[str] = set()
    async for doc in old_system.find({}, {"name": 1}):
        system_skill_names.add(doc["name"])

    # 1. system_skills -> skill_marketplace + skill_marketplace_files
    migrated_count = 0
    async for doc in old_system.find({}):
        skill_name = doc["name"]

        existing = await new_marketplace.find_one({"skill_name": skill_name})
        if existing:
            # 已存在则仅确保文件同步
            async for file_doc in old_files.find(
                {"skill_name": skill_name, "user_id": "system"}
            ):
                await new_marketplace_files.update_one(
                    {"skill_name": skill_name, "file_path": file_doc["file_path"]},
                    {
                        "$setOnInsert": {
                            "content": file_doc["content"],
                            "created_at": file_doc.get("created_at"),
                            "updated_at": file_doc.get("updated_at"),
                        },
                    },
                    upsert=True,
                )
            continue

        now = doc.get("updated_at") or doc.get("created_at")
        await new_marketplace.insert_one({
            "skill_name": skill_name,
            "description": doc.get("description", ""),
            "tags": doc.get("tags", []),
            "version": doc.get("version", "1.0.0"),
            "created_at": doc.get("created_at"),
            "updated_at": now,
            "created_by": "system",
            "is_active": True,
        })

        async for file_doc in old_files.find(
            {"skill_name": skill_name, "user_id": "system"}
        ):
            await new_marketplace_files.update_one(
                {"skill_name": skill_name, "file_path": file_doc["file_path"]},
                {
                    "$set": {
                        "content": file_doc["content"],
                        "updated_at": file_doc.get("updated_at"),
                    },
                    "$setOnInsert": {
                        "created_at": file_doc.get("created_at"),
                    },
                },
                upsert=True,
            )
        migrated_count += 1

    # 2. user_skill_preferences -> skill_toggles
    migrated_prefs = 0
    async for doc in old_prefs.find({}):
        user_id = doc["user_id"]
        skill_name = doc["skill_name"]
        enabled = doc.get("enabled", True)

        existing_toggle = await new_toggles.find_one(
            {"skill_name": skill_name, "user_id": user_id}
        )
        if existing_toggle:
            continue

        installed_from = "marketplace" if skill_name in system_skill_names else "manual"
        await new_toggles.insert_one({
            "skill_name": skill_name,
            "user_id": user_id,
            "enabled": enabled,
            "installed_from": installed_from,
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        })
        migrated_prefs += 1

    # 3. user_skills -> skill_toggles
    async for doc in old_user.find({}):
        user_id = doc["user_id"]
        skill_name = doc["name"]
        enabled = doc.get("enabled", True)

        existing_toggle = await new_toggles.find_one(
            {"skill_name": skill_name, "user_id": user_id}
        )
        if existing_toggle:
            continue

        await new_toggles.insert_one({
            "skill_name": skill_name,
            "user_id": user_id,
            "enabled": enabled,
            "installed_from": "manual",
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        })

    # 4. 为旧版用户复制 marketplace 文件到 skill_files
    installed_count = 0
    async for toggle_doc in new_toggles.find({"installed_from": "marketplace"}):
        user_id = toggle_doc["user_id"]
        skill_name = toggle_doc["skill_name"]

        user_file_count = await db["skill_files"].count_documents(
            {"skill_name": skill_name, "user_id": user_id}
        )
        if user_file_count > 0:
            continue

        files_copied = 0
        async for mp_file in new_marketplace_files.find({"skill_name": skill_name}):
            await db["skill_files"].update_one(
                {"skill_name": skill_name, "user_id": user_id, "file_path": mp_file["file_path"]},
                {
                    "$set": {
                        "content": mp_file["content"],
                        "updated_at": mp_file.get("updated_at"),
                    },
                    "$setOnInsert": {
                        "created_at": mp_file.get("created_at"),
                    },
                },
                upsert=True,
            )
            files_copied += 1

        if files_copied > 0:
            installed_count += 1

    logger.info(
        f"Legacy skill migration done: "
        f"marketplace={migrated_count}, prefs={migrated_prefs}, "
        f"installations={installed_count}"
    )
