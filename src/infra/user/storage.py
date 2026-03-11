"""
用户存储层

提供用户的数据库操作。
"""

import re
from datetime import datetime, timezone
from typing import Any, Optional

from src.infra.auth.password import hash_password, verify_password
from src.kernel.config import settings
from src.kernel.exceptions import NotFoundError, ValidationError
from src.kernel.schemas.user import User, UserCreate, UserInDB, UserUpdate


def _escape_regex(text: str) -> str:
    """
    转义正则表达式特殊字符，防止 ReDoS 攻击

    Args:
        text: 用户输入的搜索文本

    Returns:
        转义后的安全正则表达式字符串
    """
    # 转义所有正则表达式特殊字符
    return re.escape(text)


def _safe_search_pattern(text: str) -> str:
    """
    创建安全的搜索模式

    使用转义后的文本，并添加锚定以避免意外匹配。
    对于邮箱等包含特殊字符的搜索，确保正确转义。

    Args:
        text: 用户输入的搜索文本

    Returns:
        安全的正则表达式模式
    """
    escaped = _escape_regex(text)
    # 不添加锚定，允许部分匹配（如搜索 "john" 匹配 "johnson"）
    return escaped


class UserStorage:
    """
    用户存储类

    使用 MongoDB 存储用户数据。
    """

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db["users"]
            # 确保在第一次访问时创建索引
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果事件循环正在运行，调度索引创建
                    asyncio.create_task(self._ensure_indexes())
                else:
                    # 否则同步运行
                    loop.run_until_complete(self._ensure_indexes())
            except RuntimeError:
                # 如果没有事件循环，忽略（会在第一次异步操作时创建）
                pass
        return self._collection

    async def _ensure_indexes(self):
        """确保必要的索引存在（包括唯一索引）并迁移旧用户数据"""
        try:
            collection = self.collection  # 使用属性而不是直接访问 _collection
            # 创建唯一索引防止并发竞态条件
            await collection.create_index("username", unique=True, background=True)
            await collection.create_index("email", unique=True, background=True)
            # 其他常用查询索引
            await collection.create_index("oauth_provider", background=True)
            await collection.create_index("reset_token", background=True, sparse=True)
            await collection.create_index("verification_token", background=True, sparse=True)

            # 自动迁移旧用户：将 None 改为 True
            await self._migrate_legacy_users()
        except Exception as e:
            # 索引创建失败不应阻止应用启动
            import logging

            logging.getLogger(__name__).warning(f"Failed to create indexes: {e}")

    async def _migrate_legacy_users(self):
        """迁移旧用户数据：将 email_verified 和 is_active 从 None 改为 True"""
        try:
            # 迁移 email_verified: None -> True
            result1 = await self.collection.update_many(
                {"email_verified": None},
                {"$set": {"email_verified": True}},
            )
            if result1.modified_count > 0:
                import logging

                logging.getLogger(__name__).info(
                    f"[Migration] Updated email_verified for {result1.modified_count} users"
                )

            # 迁移 is_active: None -> True
            result2 = await self.collection.update_many(
                {"is_active": None},
                {"$set": {"is_active": True}},
            )
            if result2.modified_count > 0:
                import logging

                logging.getLogger(__name__).info(
                    f"[Migration] Updated is_active for {result2.modified_count} users"
                )
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"[Migration] Failed to migrate legacy users: {e}")

    async def create(self, user_data: UserCreate) -> UserInDB:
        """
        创建用户（并发安全）

        使用 MongoDB unique index 防止并发竞态条件。
        不再使用"先检查后插入"模式，而是直接插入并捕获 duplicate key error。

        注册时设置 is_active=False (pending 状态)，需要邮箱验证后激活。
        OAuth 用户自动激活。

        Args:
            user_data: 用户创建数据

        Returns:
            创建的用户（含敏感数据）

        Raises:
            ValidationError: 用户名或邮箱已存在
        """
        from pymongo.errors import DuplicateKeyError

        now = datetime.now()
        # For OAuth users, generate a random password if not provided
        password = user_data.password
        is_oauth_user = bool(user_data.oauth_provider and user_data.oauth_id)
        if not password and is_oauth_user:
            import secrets

            password = secrets.token_urlsafe(32)

        # OAuth 用户或管理员创建的用户自动激活和验证，普通用户需要邮箱验证
        should_skip_verification = is_oauth_user or user_data.skip_verification
        user_dict: dict[str, Any] = {
            "username": user_data.username,
            "email": user_data.email,
            "password_hash": hash_password(password) if password else None,
            "roles": user_data.roles if user_data.roles else [],  # 使用提供的角色，否则为空
            "avatar_url": user_data.avatar_url,  # Data URI for avatar
            "oauth_provider": user_data.oauth_provider.value if user_data.oauth_provider else None,
            "oauth_id": user_data.oauth_id,
            "is_active": should_skip_verification,  # OAuth 或管理员创建的用户自动激活
            "email_verified": should_skip_verification,  # OAuth 或管理员创建的用户自动验证
            "verification_token": None,
            "verification_token_expires": None,
            "reset_token": None,
            "reset_token_expires": None,
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = await self.collection.insert_one(user_dict)
            user_dict["id"] = str(result.inserted_id)
            return UserInDB(**user_dict)
        except DuplicateKeyError as e:
            # 解析哪个字段重复
            error_msg = str(e)
            if "username" in error_msg or "username_1" in error_msg:
                raise ValidationError(f"用户名 '{user_data.username}' 已存在")
            elif "email" in error_msg or "email_1" in error_msg:
                raise ValidationError(f"邮箱 '{user_data.email}' 已存在")
            else:
                # 未知重复键错误
                raise ValidationError("用户名或邮箱已存在")

    async def get_by_id(self, user_id: str) -> Optional[UserInDB]:
        """
        通过 ID 获取用户

        Args:
            user_id: 用户 ID

        Returns:
            用户对象或 None
        """
        from bson import ObjectId
        from bson.errors import InvalidId

        try:
            user_dict = await self.collection.find_one({"_id": ObjectId(user_id)})
        except InvalidId:
            # 无效的 ObjectId 格式
            return None

        if not user_dict:
            return None

        user_dict["id"] = str(user_dict.pop("_id"))
        return UserInDB(**user_dict)

    async def get_by_username(self, username: str) -> Optional[UserInDB]:
        """
        通过用户名获取用户

        Args:
            username: 用户名

        Returns:
            用户对象或 None
        """
        user_dict = await self.collection.find_one({"username": username})

        if not user_dict:
            return None

        user_dict["id"] = str(user_dict.pop("_id"))
        return UserInDB(**user_dict)

    async def get_by_email(self, email: str) -> Optional[UserInDB]:
        """
        通过邮箱获取用户

        Args:
            email: 邮箱

        Returns:
            用户对象或 None
        """
        user_dict = await self.collection.find_one({"email": email})

        if not user_dict:
            return None

        user_dict["id"] = str(user_dict.pop("_id"))
        return UserInDB(**user_dict)

    async def get_by_oauth(self, oauth_provider: str, oauth_id: str) -> Optional[UserInDB]:
        """
        通过 OAuth 提供商和 ID 获取用户

        Args:
            oauth_provider: OAuth 提供商 (google, github, apple)
            oauth_id: OAuth 提供商返回的用户 ID

        Returns:
            用户对象或 None
        """
        user_dict = await self.collection.find_one(
            {
                "oauth_provider": oauth_provider,
                "oauth_id": oauth_id,
            }
        )

        if not user_dict:
            return None

        user_dict["id"] = str(user_dict.pop("_id"))
        return UserInDB(**user_dict)

    async def update(self, user_id: str, user_data: UserUpdate) -> Optional[User]:
        """
        更新用户

        Args:
            user_id: 用户 ID
            user_data: 更新数据

        Returns:
            更新后的用户

        Raises:
            NotFoundError: 用户不存在
        """
        from pymongo.errors import DuplicateKeyError

        update_dict: dict = {"updated_at": datetime.now()}

        if user_data.username is not None:
            update_dict["username"] = user_data.username

        if user_data.email is not None:
            update_dict["email"] = user_data.email

        if user_data.password is not None:
            update_dict["password_hash"] = hash_password(user_data.password)

        # Check if avatar_url was explicitly set (even to None) using model_fields_set
        if "avatar_url" in user_data.model_fields_set:
            update_dict["avatar_url"] = user_data.avatar_url

        if user_data.roles is not None:
            update_dict["roles"] = user_data.roles

        if user_data.is_active is not None:
            update_dict["is_active"] = user_data.is_active

        # 支持邮箱验证和密码重置字段
        if hasattr(user_data, "email_verified") and user_data.email_verified is not None:
            update_dict["email_verified"] = user_data.email_verified

        if hasattr(user_data, "verification_token") and user_data.verification_token is not None:
            update_dict["verification_token"] = user_data.verification_token

        if hasattr(user_data, "verification_token_expires"):
            update_dict["verification_token_expires"] = user_data.verification_token_expires

        if hasattr(user_data, "reset_token"):
            update_dict["reset_token"] = user_data.reset_token

        if hasattr(user_data, "reset_token_expires"):
            update_dict["reset_token_expires"] = user_data.reset_token_expires

        from bson import ObjectId

        try:
            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(user_id)},
                {"$set": update_dict},
                return_document=True,
            )

            if not result:
                raise NotFoundError(f"用户 '{user_id}' 不存在")

            result["id"] = str(result.pop("_id"))
            return User(**result)
        except DuplicateKeyError as e:
            # 解析哪个字段重复
            error_msg = str(e)
            if "username" in error_msg or "username_1" in error_msg:
                raise ValidationError(f"用户名 '{user_data.username}' 已存在")
            elif "email" in error_msg or "email_1" in error_msg:
                raise ValidationError(f"邮箱 '{user_data.email}' 已存在")
            else:
                # 未知重复键错误
                raise ValidationError("用户名或邮箱已存在")

    async def delete(self, user_id: str) -> bool:
        """
        删除用户

        Args:
            user_id: 用户 ID

        Returns:
            是否删除成功
        """
        from bson import ObjectId

        result = await self.collection.delete_one({"_id": ObjectId(user_id)})
        return result.deleted_count > 0

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> list[User]:
        """
        列出用户

        Args:
            skip: 跳过数量
            limit: 返回数量
            is_active: 是否激活
            search: 搜索字符串（用户名/邮箱模糊匹配）

        Returns:
            用户列表
        """
        query: dict = {}
        if is_active is not None:
            query["is_active"] = is_active
        if search:
            # 使用安全的搜索模式防止 ReDoS 攻击
            escaped_search = _safe_search_pattern(search)
            query["$or"] = [
                {"username": {"$regex": escaped_search, "$options": "i"}},
                {"email": {"$regex": escaped_search, "$options": "i"}},
            ]

        cursor = self.collection.find(query).skip(skip).limit(limit)
        users = []

        async for user_dict in cursor:
            user_dict["id"] = str(user_dict.pop("_id"))
            users.append(User(**user_dict))

        return users

    async def count_users(
        self,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> int:
        """
        统计用户数量

        Args:
            search: 搜索字符串（用户名/邮箱模糊匹配）
            is_active: 是否激活

        Returns:
            匹配的用户总数
        """
        query: dict = {}
        if is_active is not None:
            query["is_active"] = is_active
        if search:
            # 使用安全的搜索模式防止 ReDoS 攻击
            escaped_search = _safe_search_pattern(search)
            query["$or"] = [
                {"username": {"$regex": escaped_search, "$options": "i"}},
                {"email": {"$regex": escaped_search, "$options": "i"}},
            ]
        return await self.collection.count_documents(query)

    async def authenticate(self, username_or_email: str, password: str) -> Optional[UserInDB]:
        """
        验证用户凭据（支持用户名或邮箱登录）

        注意：此方法只验证密码，不检查激活状态。
        激活状态检查由 UserManager.login() 处理，以便返回正确的错误信息。

        Args:
            username_or_email: 用户名或邮箱
            password: 密码

        Returns:
            验证成功返回用户对象，否则返回 None
        """
        # 先尝试用户名查找
        user = await self.get_by_username(username_or_email)
        # 如果用户名查找失败，尝试邮箱查找
        if not user:
            user = await self.get_by_email(username_or_email)

        if not user:
            return None

        # 只验证密码，不检查 is_active
        # is_active 检查由 UserManager.login() 处理，以便返回正确的错误信息
        if not verify_password(password, user.password_hash):
            return None

        return user

    async def get_by_reset_token(self, token: str) -> Optional[UserInDB]:
        """
        通过密码重置令牌获取用户

        Args:
            token: 密码重置令牌

        Returns:
            用户对象或 None
        """
        user_dict = await self.collection.find_one({"reset_token": token})
        if not user_dict:
            return None
        user_dict["id"] = str(user_dict.pop("_id"))
        return UserInDB(**user_dict)

    async def get_by_verification_token(self, token: str) -> Optional[UserInDB]:
        """
        通过邮箱验证令牌获取用户

        Args:
            token: 邮箱验证令牌

        Returns:
            用户对象或 None（令牌无效或已过期）
        """
        user_dict = await self.collection.find_one({"verification_token": token})
        if not user_dict:
            return None

        # 检查令牌是否过期（如果有设置过期时间）
        expires = user_dict.get("verification_token_expires")
        if expires is not None:
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires:
                return None

        user_dict["id"] = str(user_dict.pop("_id"))
        return UserInDB(**user_dict)

    async def set_email_verified(self, user_id: str, verified: bool = True) -> bool:
        """
        设置用户邮箱验证状态

        Args:
            user_id: 用户 ID
            verified: 是否已验证

        Returns:
            是否更新成功
        """
        from bson import ObjectId

        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"email_verified": verified, "updated_at": datetime.now()}},
        )
        return result.modified_count > 0

    async def set_reset_token(self, user_id: str, token: str, expires: datetime) -> bool:
        """
        设置用户密码重置令牌

        Args:
            user_id: 用户 ID
            token: 重置令牌
            expires: 过期时间

        Returns:
            是否更新成功
        """
        from bson import ObjectId

        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "reset_token": token,
                    "reset_token_expires": expires,
                    "updated_at": datetime.now(),
                }
            },
        )
        return result.modified_count > 0

    async def clear_reset_token(self, user_id: str) -> bool:
        """
        清除用户密码重置令牌

        Args:
            user_id: 用户 ID

        Returns:
            是否更新成功
        """
        from bson import ObjectId

        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "reset_token": None,
                    "reset_token_expires": None,
                    "updated_at": datetime.now(),
                }
            },
        )
        return result.modified_count > 0
