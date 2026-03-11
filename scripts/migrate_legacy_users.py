"""
数据库迁移脚本：将旧用户的 email_verified 和 is_active 从 None 改为 True

运行方式：
    cd /root/clawd/lambchat
    python scripts/migrate_legacy_users.py
"""

import asyncio
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient

from src.kernel.config import settings


async def migrate_legacy_users():
    """将旧用户的 email_verified 和 is_active 从 None 改为 True"""
    # 使用 motor 异步客户端
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB]
    users_collection = db["users"]

    print("开始迁移旧用户数据...")

    # 查找所有 email_verified 为 None 或不存在的用户
    result1 = await users_collection.update_many(
        {"email_verified": None},
        {"$set": {"email_verified": True}},
    )
    print(f"✅ 更新 email_verified=None: {result1.modified_count} 个用户")

    # 查找所有 is_active 为 None 或不存在的用户
    result2 = await users_collection.update_many(
        {"is_active": None},
        {"$set": {"is_active": True}},
    )
    print(f"✅ 更新 is_active=None: {result2.modified_count} 个用户")

    # 确保所有用户都有这两个字段
    result3 = await users_collection.update_many(
        {"email_verified": {"$exists": False}},
        {"$set": {"email_verified": True}},
    )
    print(f"✅ 添加缺失的 email_verified 字段: {result3.modified_count} 个用户")

    result4 = await users_collection.update_many(
        {"is_active": {"$exists": False}},
        {"$set": {"is_active": True}},
    )
    print(f"✅ 添加缺失的 is_active 字段: {result4.modified_count} 个用户")

    print("\n迁移完成！")

    # 验证
    total_users = await users_collection.count_documents({})
    verified_users = await users_collection.count_documents({"email_verified": True})
    active_users = await users_collection.count_documents({"is_active": True})

    print("\n验证结果:")
    print(f"  总用户数: {total_users}")
    print(f"  email_verified=True: {verified_users}")
    print(f"  is_active=True: {active_users}")

    client.close()


if __name__ == "__main__":
    asyncio.run(migrate_legacy_users())
