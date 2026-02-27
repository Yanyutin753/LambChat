"""
角色存储层

提供角色的数据库操作。
"""

from datetime import datetime
from typing import Any, Optional

from src.kernel.config import settings
from src.kernel.exceptions import NotFoundError, ValidationError
from src.kernel.schemas.role import Role, RoleCreate, RoleUpdate
from src.kernel.types import Permission


class RoleStorage:
    """
    角色存储类

    使用 MongoDB 存储角色数据。
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
            self._collection = db["roles"]
        return self._collection

    async def create(self, role_data: RoleCreate) -> Role:
        """
        创建角色

        Args:
            role_data: 角色创建数据

        Returns:
            创建的角色

        Raises:
            ValidationError: 角色名已存在
        """
        # 检查角色名是否存在
        existing = await self.get_by_name(role_data.name)
        if existing:
            raise ValidationError(f"角色 '{role_data.name}' 已存在")

        now = datetime.now()
        role_dict: dict[str, Any] = {
            "name": role_data.name,
            "description": role_data.description,
            "permissions": [p.value for p in role_data.permissions],
            "is_system": False,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(role_dict)
        role_dict["id"] = str(result.inserted_id)
        role_dict["permissions"] = role_data.permissions  # 保持枚举类型

        return Role(**role_dict)

    async def get_by_id(self, role_id: str) -> Optional[Role]:
        """
        通过 ID 获取角色

        Args:
            role_id: 角色 ID

        Returns:
            角色对象或 None
        """
        from bson import ObjectId

        try:
            role_dict = await self.collection.find_one({"_id": ObjectId(role_id)})
        except Exception:
            return None

        if not role_dict:
            return None

        role_dict["id"] = str(role_dict.pop("_id"))
        role_dict["permissions"] = [Permission(p) for p in role_dict.get("permissions", [])]
        return Role(**role_dict)

    async def get_by_name(self, name: str) -> Optional[Role]:
        """
        通过名称获取角色

        Args:
            name: 角色名称

        Returns:
            角色对象或 None
        """
        role_dict = await self.collection.find_one({"name": name})

        if not role_dict:
            return None

        role_dict["id"] = str(role_dict.pop("_id"))
        role_dict["permissions"] = [Permission(p) for p in role_dict.get("permissions", [])]
        return Role(**role_dict)

    async def update(self, role_id: str, role_data: RoleUpdate) -> Optional[Role]:
        """
        更新角色

        Args:
            role_id: 角色 ID
            role_data: 更新数据

        Returns:
            更新后的角色

        Raises:
            NotFoundError: 角色不存在
            ValidationError: 系统角色不可修改
        """
        # 获取现有角色
        existing = await self.get_by_id(role_id)
        if not existing:
            raise NotFoundError(f"角色 '{role_id}' 不存在")

        if existing.is_system:
            raise ValidationError("系统角色不可修改")

        update_dict: dict = {"updated_at": datetime.now()}

        if role_data.name is not None:
            # 检查新名称是否已存在
            name_check = await self.get_by_name(role_data.name)
            if name_check and name_check.id != role_id:
                raise ValidationError(f"角色名 '{role_data.name}' 已存在")
            update_dict["name"] = role_data.name

        if role_data.description is not None:
            update_dict["description"] = role_data.description

        if role_data.permissions is not None:
            update_dict["permissions"] = [p.value for p in role_data.permissions]

        from bson import ObjectId

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(role_id)},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            raise NotFoundError(f"角色 '{role_id}' 不存在")

        result["id"] = str(result.pop("_id"))
        result["permissions"] = [Permission(p) for p in result.get("permissions", [])]
        return Role(**result)

    async def delete(self, role_id: str) -> bool:
        """
        删除角色

        Args:
            role_id: 角色 ID

        Returns:
            是否删除成功

        Raises:
            ValidationError: 系统角色不可删除
        """
        # 检查是否为系统角色
        existing = await self.get_by_id(role_id)
        if existing and existing.is_system:
            raise ValidationError("系统角色不可删除")

        from bson import ObjectId

        result = await self.collection.delete_one({"_id": ObjectId(role_id)})
        return result.deleted_count > 0

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
        cursor = self.collection.find().skip(skip).limit(limit)
        roles = []

        async for role_dict in cursor:
            role_dict["id"] = str(role_dict.pop("_id"))
            role_dict["permissions"] = [Permission(p) for p in role_dict.get("permissions", [])]
            roles.append(Role(**role_dict))

        return roles

    async def get_by_ids(self, role_ids: list[str]) -> list[Role]:
        """
        通过 ID 列表获取角色

        Args:
            role_ids: 角色 ID 列表

        Returns:
            角色列表
        """
        from bson import ObjectId

        object_ids = [ObjectId(rid) for rid in role_ids]
        cursor = self.collection.find({"_id": {"$in": object_ids}})
        roles = []

        async for role_dict in cursor:
            role_dict["id"] = str(role_dict.pop("_id"))
            role_dict["permissions"] = [Permission(p) for p in role_dict.get("permissions", [])]
            roles.append(Role(**role_dict))

        return roles

    async def init_default_roles(self) -> None:
        """
        初始化默认角色

        对于系统角色（is_system=True），如果已存在则更新其权限列表。
        """
        from src.infra.auth.rbac import RBACManager

        rbac_manager = RBACManager()
        default_roles = rbac_manager.get_default_roles()

        for role_data in default_roles:
            existing = await self.get_by_name(role_data["name"])
            if not existing:
                # 创建新角色
                now = datetime.now()
                await self.collection.insert_one(
                    {
                        **role_data,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
            elif role_data.get("is_system", False):
                # 系统角色：更新权限列表以包含新权限
                now = datetime.now()
                await self.collection.update_one(
                    {"name": role_data["name"]},
                    {
                        "$set": {
                            "permissions": role_data["permissions"],
                            "updated_at": now,
                        }
                    },
                )
