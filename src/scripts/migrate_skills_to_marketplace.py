#!/usr/bin/env python3
"""
迁移脚本：将 system_skills 迁移到 skill_marketplace

用法：
    python -m src.scripts.migrate_skills_to_marketplace

迁移策略：
1. system_skills -> skill_marketplace + skill_marketplace_files
2. user_skills -> skill_toggles (installed_from="manual")
3. user_skill_preferences -> skill_toggles (installed_from="marketplace")
4. skill_files 中 user_id="system" 的记录 -> skill_marketplace_files
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def migrate():
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

    # 创建索引
    await new_marketplace.create_index("skill_name", unique=True, background=True)
    await new_marketplace_files.create_index(
        [("skill_name", 1), ("file_path", 1)], unique=True, background=True
    )
    await new_toggles.create_index(
        [("skill_name", 1), ("user_id", 1)], unique=True, background=True
    )
    await db["skill_files"].create_index(
        [("skill_name", 1), ("user_id", 1), ("file_path", 1)],
        unique=True,
        background=True,
    )
    print("Created indexes")

    # ==========================================
    # 1. 迁移 system_skills -> skill_marketplace + skill_marketplace_files
    # ==========================================
    migrated_count = 0
    async for doc in old_system.find({}):
        skill_name = doc["name"]

        # 导入元数据到 skill_marketplace
        await new_marketplace.update_one(
            {"skill_name": skill_name},
            {
                "$set": {
                    "description": doc.get("description", ""),
                    "tags": [],
                    "version": doc.get("version", "1.0.0"),
                    "created_at": doc.get("created_at"),
                    "updated_at": doc.get("updated_at"),
                    "created_by": doc.get("updated_by", "system"),
                },
                "$setOnInsert": {
                    "skill_name": skill_name,
                },
            },
            upsert=True,
        )

        # 复制文件到 skill_marketplace_files
        async for file_doc in old_files.find({"skill_name": skill_name, "user_id": "system"}):
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
        print(f"Migrated marketplace skill: {skill_name}")

    print(f"\nMigrated {migrated_count} marketplace skills")

    # ==========================================
    # 2. 迁移 user_skills -> skill_toggles
    # ==========================================
    migrated_users = set()
    async for doc in old_user.find({}):
        user_id = doc["user_id"]
        skill_name = doc["name"]
        enabled = doc.get("enabled", True)

        await new_toggles.update_one(
            {"skill_name": skill_name, "user_id": user_id},
            {
                "$set": {
                    "enabled": enabled,
                    "installed_from": "manual",
                    "updated_at": doc.get("updated_at"),
                },
                "$setOnInsert": {
                    "created_at": doc.get("created_at"),
                },
            },
            upsert=True,
        )
        migrated_users.add(user_id)

    print(f"Migrated skills for {len(migrated_users)} users from user_skills")

    # ==========================================
    # 3. 迁移 user_skill_preferences -> skill_toggles
    # ==========================================
    migrated_prefs = 0
    async for doc in old_prefs.find({}):
        user_id = doc["user_id"]
        skill_name = doc["skill_name"]
        enabled = doc.get("enabled", True)

        # 判断来源：如果 skill_files 中有 system 版本则为商城来源
        has_system_version = await old_files.find_one(
            {"skill_name": skill_name, "user_id": "system"}
        )
        installed_from = "marketplace" if has_system_version else "manual"

        await new_toggles.update_one(
            {"skill_name": skill_name, "user_id": user_id},
            {
                "$set": {
                    "enabled": enabled,
                    "installed_from": installed_from,
                    "updated_at": doc.get("updated_at"),
                },
                "$setOnInsert": {
                    "created_at": doc.get("created_at"),
                },
            },
            upsert=True,
        )
        migrated_prefs += 1

    print(f"Migrated {migrated_prefs} user preferences to toggles")

    print("\nMigration complete!")
    print("\nOld collections can now be dropped after verifying:")
    print("  - system_skills")
    print("  - user_skills")
    print("  - user_skill_preferences")
    print("  - skill_files (user_id='system' records can be deleted)")
    print("\nTo drop old collections, run:")
    print("  db.system_skills.drop()")
    print("  db.user_skills.drop()")
    print("  db.user_skill_preferences.drop()")
    print('  db.skill_files.deleteMany({user_id: "system"})')


if __name__ == "__main__":
    asyncio.run(migrate())
