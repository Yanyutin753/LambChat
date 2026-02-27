"""
角色管理器

提供角色管理的业务逻辑。
"""

from typing import Optional

from src.infra.role.storage import RoleStorage
from src.kernel.schemas.role import Role, RoleCreate, RoleUpdate


class RoleManager:
    """
    角色管理器

    提供角色 CRUD 功能。
    """

    def __init__(self):
        self.storage = RoleStorage()

    async def create_role(self, role_data: RoleCreate) -> Role:
        """
        创建角色

        Args:
            role_data: 角色创建数据

        Returns:
            创建的角色
        """
        return await self.storage.create(role_data)

    async def get_role(self, role_id: str) -> Optional[Role]:
        """
        获取角色

        Args:
            role_id: 角色 ID

        Returns:
            角色或 None
        """
        return await self.storage.get_by_id(role_id)

    async def get_role_by_name(self, name: str) -> Optional[Role]:
        """
        通过名称获取角色

        Args:
            name: 角色名称

        Returns:
            角色或 None
        """
        return await self.storage.get_by_name(name)

    async def update_role(self, role_id: str, role_data: RoleUpdate) -> Optional[Role]:
        """
        更新角色

        Args:
            role_id: 角色 ID
            role_data: 更新数据

        Returns:
            更新后的角色
        """
        return await self.storage.update(role_id, role_data)

    async def delete_role(self, role_id: str) -> bool:
        """
        删除角色

        Args:
            role_id: 角色 ID

        Returns:
            是否删除成功
        """
        return await self.storage.delete(role_id)

    async def list_roles(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Role]:
        """
        列出角色

        Args:
            skip: 跳过数量
            limit: 返回数量

        Returns:
            角色列表
        """
        return await self.storage.list_roles(skip, limit)

    async def init_default_roles(self) -> None:
        """
        初始化默认角色
        """
        await self.storage.init_default_roles()
