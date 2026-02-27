"""
用户存储层

提供用户的数据库操作。
"""

from datetime import datetime
from typing import Any, Optional

from src.infra.auth.password import hash_password, verify_password
from src.kernel.config import settings
from src.kernel.exceptions import NotFoundError, ValidationError
from src.kernel.schemas.user import User, UserCreate, UserInDB, UserUpdate


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
        return self._collection

    async def create(self, user_data: UserCreate) -> UserInDB:
        """
        创建用户

        Args:
            user_data: 用户创建数据

        Returns:
            创建的用户（含敏感数据）

        Raises:
            ValidationError: 用户名或邮箱已存在
        """
        # 检查用户名是否存在
        existing = await self.get_by_username(user_data.username)
        if existing:
            raise ValidationError(f"用户名 '{user_data.username}' 已存在")

        # 检查邮箱是否存在
        existing = await self.get_by_email(user_data.email)
        if existing:
            raise ValidationError(f"邮箱 '{user_data.email}' 已存在")

        now = datetime.now()
        user_dict: dict[str, Any] = {
            "username": user_data.username,
            "email": user_data.email,
            "password_hash": hash_password(user_data.password),
            "roles": user_data.roles,
            "avatar_url": user_data.avatar_url,  # Data URI for avatar
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(user_dict)
        user_dict["id"] = str(result.inserted_id)

        return UserInDB(**user_dict)

    async def get_by_id(self, user_id: str) -> Optional[UserInDB]:
        """
        通过 ID 获取用户

        Args:
            user_id: 用户 ID

        Returns:
            用户对象或 None
        """
        from bson import ObjectId

        try:
            user_dict = await self.collection.find_one({"_id": ObjectId(user_id)})
        except Exception:
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
        update_dict: dict = {"updated_at": datetime.now()}

        if user_data.username is not None:
            # 检查新用户名是否已存在
            existing = await self.get_by_username(user_data.username)
            if existing and existing.id != user_id:
                raise ValidationError(f"用户名 '{user_data.username}' 已存在")
            update_dict["username"] = user_data.username

        if user_data.email is not None:
            # 检查新邮箱是否已存在
            existing = await self.get_by_email(user_data.email)
            if existing and existing.id != user_id:
                raise ValidationError(f"邮箱 '{user_data.email}' 已存在")
            update_dict["email"] = user_data.email

        if user_data.password is not None:
            update_dict["password_hash"] = hash_password(user_data.password)

        if user_data.avatar_url is not None:
            update_dict["avatar_url"] = user_data.avatar_url

        if user_data.roles is not None:
            update_dict["roles"] = user_data.roles

        if user_data.is_active is not None:
            update_dict["is_active"] = user_data.is_active

        from bson import ObjectId

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            raise NotFoundError(f"用户 '{user_id}' 不存在")

        result["id"] = str(result.pop("_id"))
        return User(**result)

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
    ) -> list[User]:
        """
        列出用户

        Args:
            skip: 跳过数量
            limit: 返回数量
            is_active: 是否激活

        Returns:
            用户列表
        """
        query = {}
        if is_active is not None:
            query["is_active"] = is_active

        cursor = self.collection.find(query).skip(skip).limit(limit)
        users = []

        async for user_dict in cursor:
            user_dict["id"] = str(user_dict.pop("_id"))
            users.append(User(**user_dict))

        return users

    async def authenticate(self, username_or_email: str, password: str) -> Optional[UserInDB]:
        """
        验证用户凭据（支持用户名或邮箱登录）

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

        if not user.is_active:
            return None

        if not verify_password(password, user.password_hash):
            return None

        return user
