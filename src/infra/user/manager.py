"""
用户管理器

提供用户管理的业务逻辑。
"""

from typing import Optional

from src.infra.auth.jwt import create_access_token, create_refresh_token
from src.infra.role.storage import RoleStorage
from src.infra.settings.service import SettingsService
from src.infra.user.storage import UserStorage
from src.kernel.config import settings
from src.kernel.schemas.user import Token, User, UserCreate, UserListResponse, UserUpdate


class UserManager:
    """
    用户管理器

    提供用户注册、登录、更新等功能。
    """

    def __init__(self):
        self.storage = UserStorage()
        self.role_storage = RoleStorage()
        self.settings_service = SettingsService()

    async def register(self, user_data: UserCreate) -> User:
        """
        注册新用户

        Args:
            user_data: 用户创建数据

        Returns:
            创建的用户
        """
        # 如果没有指定角色，检查是否是第一个用户
        if not user_data.roles:
            # 检查是否已有用户
            existing_users = await self.storage.list_users(limit=1)
            if not existing_users:
                # 第一个用户设为管理员
                user_data.roles = ["admin"]
            else:
                # 从设置中读取默认角色
                default_role = await self.settings_service.get("DEFAULT_USER_ROLE")
                user_data.roles = [default_role or "user"]

        user = await self.storage.create(user_data)
        return User.model_validate(user.model_dump())

    async def login(self, username_or_email: str, password: str) -> Optional[Token]:
        """
        用户登录（支持用户名或邮箱）

        Args:
            username_or_email: 用户名或邮箱
            password: 密码

        Returns:
            Token 或 None

        Raises:
            EmailNotVerifiedError: 邮箱未验证（当 REQUIRE_EMAIL_VERIFICATION=true 时）
        """
        user = await self.storage.authenticate(username_or_email, password)
        if not user:
            return None

        # 检查邮箱验证状态
        if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
            from src.kernel.exceptions import EmailNotVerifiedError

            raise EmailNotVerifiedError("请先验证邮箱后再登录", user.email)

        # 获取用户的角色和权限
        roles = []
        permissions = set()

        for role_name in user.roles:
            role = await self.role_storage.get_by_name(role_name)
            if role:
                roles.append(role.name)
                for perm in role.permissions:
                    # Handle both Permission enum and string
                    if isinstance(perm, str):
                        permissions.add(perm)
                    else:
                        permissions.add(perm.value)

        # 创建 token（用户信息从 API 动态获取）
        access_token = create_access_token(user_id=user.id)

        refresh_token = create_refresh_token(
            user_id=user.id,
            username=user.username,
        )

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        )

    async def get_user(self, user_id: str) -> Optional[User]:
        """
        获取用户

        Args:
            user_id: 用户 ID

        Returns:
            用户或 None
        """
        user = await self.storage.get_by_id(user_id)
        if not user:
            return None
        return User.model_validate(user.model_dump())

    async def update_user(self, user_id: str, user_data: UserUpdate) -> Optional[User]:
        """
        更新用户

        Args:
            user_id: 用户 ID
            user_data: 更新数据

        Returns:
            更新后的用户
        """
        return await self.storage.update(user_id, user_data)

    async def delete_user(self, user_id: str) -> bool:
        """
        删除用户

        Args:
            user_id: 用户 ID

        Returns:
            是否删除成功
        """
        # Schedule S3 files deletion as background task (non-blocking)
        import asyncio

        async def cleanup_s3_files(uid: str):
            """Background task to delete user's S3 files"""
            try:
                from src.infra.storage.s3 import get_storage_service

                storage = get_storage_service()
                if storage and hasattr(storage, "_config") and storage._config.bucket_name:
                    await storage.delete_user_files(uid)
            except Exception:
                # Ignore S3 deletion errors - may not be configured
                pass

        # Run S3 cleanup in background (non-blocking)
        asyncio.create_task(cleanup_s3_files(user_id))

        return await self.storage.delete(user_id)

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> UserListResponse:
        """
        列出用户（分页）

        Args:
            skip: 跳过数量
            limit: 返回数量（默认20）
            search: 搜索字符串（用户名/邮箱模糊匹配）
            is_active: 是否激活

        Returns:
            分页用户列表响应
        """
        users = await self.storage.list_users(skip, limit, is_active, search)
        total = await self.storage.count_users(search, is_active)
        return UserListResponse(
            users=users,
            total=total,
            skip=skip,
            limit=limit,
            has_more=skip + limit < total,
        )
