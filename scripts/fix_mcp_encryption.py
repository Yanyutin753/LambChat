#!/usr/bin/env python3
"""
修复 MCP 加密数据

当 MCP_ENCRYPTION_KEY 变更后，旧数据无法解密。
此脚本会：
1. 扫描所有 MCP 服务器配置
2. 找出解密失败的记录
3. 清空敏感字段（env/headers），保留其他配置

使用方法：
    # 先备份数据库！
    # 然后运行：
    python scripts/fix_mcp_encryption.py --dry-run  # 预览将删除的内容
    python scripts/fix_mcp_encryption.py --fix      # 执行修复
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infra.config import settings
from src.infra.storage.mongo import get_mongo_client


async def fix_mcp_encryption(dry_run: bool = True):
    """修复 MCP 加密数据"""
    client = get_mongo_client()
    db = client[settings.MONGODB_DB]

    system_collection = db["system_mcp_servers"]
    user_collection = db["user_mcp_servers"]

    fixed_count = 0
    error_count = 0

    print("=" * 60)
    print("MCP 加密数据修复工具")
    print("=" * 60)
    print(f"数据库: {settings.MONGODB_DB}")
    print(f"模式: {'预览 (dry-run)' if dry_run else '执行修复'}")
    print()

    # 处理 system_mcp_servers
    print("检查 system_mcp_servers...")
    async for doc in system_collection.find({}):
        server_name = doc.get("name", "unknown")
        headers = doc.get("headers", {})
        env = doc.get("env", {})

        # 检查是否是加密格式但无法解密
        has_encrypted = False
        if isinstance(headers, dict) and "__encrypted__" in headers:
            has_encrypted = True
        if isinstance(env, dict) and "__encrypted__" in env:
            has_encrypted = True

        if has_encrypted:
            print(f"  - 发现加密数据: {server_name}")
            print(f"    headers: {list(headers.keys())}")
            print(f"    env: {list(env.keys())}")

            if not dry_run:
                # 清空敏感字段
                result = await system_collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"headers": {}, "env": {}}}
                )
                if result.modified_count > 0:
                    print(f"    ✅ 已清空")
                    fixed_count += 1
                else:
                    print(f"    ❌ 更新失败")
                    error_count += 1
            else:
                print(f"    [dry-run] 将清空 headers 和 env")
                fixed_count += 1

    # 处理 user_mcp_servers
    print("\n检查 user_mcp_servers...")
    async for doc in user_collection.find({}):
        server_name = doc.get("name", "unknown")
        user_id = doc.get("user_id", "unknown")
        headers = doc.get("headers", {})
        env = doc.get("env", {})

        has_encrypted = False
        if isinstance(headers, dict) and "__encrypted__" in headers:
            has_encrypted = True
        if isinstance(env, dict) and "__encrypted__" in env:
            has_encrypted = True

        if has_encrypted:
            print(f"  - 发现加密数据: {server_name} (user: {user_id})")
            print(f"    headers: {list(headers.keys())}")
            print(f"    env: {list(env.keys())}")

            if not dry_run:
                result = await user_collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"headers": {}, "env": {}}}
                )
                if result.modified_count > 0:
                    print(f"    ✅ 已清空")
                    fixed_count += 1
                else:
                    print(f"    ❌ 更新失败")
                    error_count += 1
            else:
                print(f"    [dry-run] 将清空 headers 和 env")
                fixed_count += 1

    print()
    print("=" * 60)
    if dry_run:
        print(f"预览完成: 发现 {fixed_count} 条需要修复的记录")
        print("运行 'python scripts/fix_mcp_encryption.py --fix' 执行修复")
    else:
        print(f"修复完成: 成功 {fixed_count} 条, 失败 {error_count} 条")
    print("=" * 60)

    client.close()
    return fixed_count, error_count


def main():
    parser = argparse.ArgumentParser(description="修复 MCP 加密数据")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="执行修复（默认是 dry-run 模式）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="预览模式，不修改数据（默认）"
    )
    args = parser.parse_args()

    # 如果指定了 --fix，则关闭 dry_run
    dry_run = not args.fix

    asyncio.run(fix_mcp_encryption(dry_run=dry_run))


if __name__ == "__main__":
    main()
