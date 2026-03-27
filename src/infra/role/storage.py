"""
角色存储层

提供角色的数据库操作。
"""

import json
from datetime import datetime
from typing import Any, Optional

from src.infra.logging import get_logger
from src.kernel.config import settings
from src.kernel.exceptions import NotFoundError, ValidationError
from src.kernel.schemas.role import Role, RoleCreate, RoleLimits, RoleUpdate
from src.kernel.types import Permission

logger = get_logger(__name__)

# 角色对象缓存 key 前缀和 TTL（按角色名缓存，所有调用方共享）
_ROLE_OBJ_CACHE_PREFIX = "role:obj:"
_ROLE_OBJ_VERSION_PREFIX = "role:obj_ver:"
_ROLE_OBJ_CACHE_TTL = 300  # 5 分钟


async def _get_redis():
    """延迟获取 Redis 客户端，避免模块级循环导入。"""
    from src.infra.storage.redis import get_redis_client

    return get_redis_client()


def _role_to_cache_dict(role: Role) -> dict:
    """将 Role 对象序列化为 JSON 可存储的 dict。"""
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "permissions": [p if isinstance(p, str) else p.value for p in role.permissions],
        "allowed_agents": role.allowed_agents,
        "limits": role.limits.model_dump() if role.limits else None,
        "is_system": role.is_system,
        "created_at": role.created_at.isoformat()
        if isinstance(role.created_at, datetime)
        else str(role.created_at),
        "updated_at": role.updated_at.isoformat()
        if isinstance(role.updated_at, datetime)
        else str(role.updated_at),
    }


def _cache_dict_to_role(data: dict | None) -> Role | None:
    """将缓存 dict 反序列化为 Role 对象。"""
    if data is None:
        return None
    if data.get("limits"):
        data["limits"] = RoleLimits(**data["limits"])
    if isinstance(data.get("created_at"), str):
        data["created_at"] = datetime.fromisoformat(data["created_at"])
    if isinstance(data.get("updated_at"), str):
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
    # 还原权限字符串为 Permission 枚举，与 DB 路径保持一致
    if isinstance(data.get("permissions"), list):
        data["permissions"] = _parse_permissions_static(data["permissions"])
    return Role(**data)


def _parse_permissions_static(permissions: list[str]) -> list[Permission]:
    """模块级版本的权限解析（供 _cache_dict_to_role 使用）。"""
    valid = []
    for p in permissions:
        try:
            valid.append(Permission(p))
        except ValueError:
            pass
    return valid


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
            "limits": role_data.limits.model_dump() if role_data.limits else None,
            "is_system": False,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(role_dict)
        role_dict["id"] = str(result.inserted_id)
        role_dict["permissions"] = role_data.permissions  # 保持枚举类型

        return Role(**role_dict)

    def _parse_permissions(self, permissions: list[str]) -> list[Permission]:
        """
        解析权限列表，过滤无效的权限字符串

        Args:
            permissions: 权限字符串列表

        Returns:
            有效的 Permission 枚举列表
        """
        valid_permissions = []
        for p in permissions:
            try:
                valid_permissions.append(Permission(p))
            except ValueError:
                # 忽略无效的权限字符串
                pass
        return valid_permissions

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
        role_dict["permissions"] = self._parse_permissions(role_dict.get("permissions", []))
        return Role(**role_dict)

    async def get_by_name(self, name: str) -> Optional[Role]:
        """
        通过名称获取角色（带 Redis 缓存）

        Args:
            name: 角色名称

        Returns:
            角色对象或 None
        """
        version: str = "0"

        try:
            redis = await _get_redis()
            raw = await redis.get(f"{_ROLE_OBJ_VERSION_PREFIX}{name}")
            version = raw or "0"
            cache_key = f"{_ROLE_OBJ_CACHE_PREFIX}{name}:v{version}"

            cached = await redis.get(cache_key)
            if cached is not None:
                logger.debug(f"[Role Cache] Hit for role {name}")
                return _cache_dict_to_role(json.loads(cached))
        except Exception as e:
            logger.warning(f"[Role Cache] Redis get failed for role {name}: {e}")

        # 缓存未命中，查询数据库
        logger.debug(f"[Role Cache] Miss for role {name}")
        role_dict = await self.collection.find_one({"name": name})

        if not role_dict:
            result = None
        else:
            role_dict["id"] = str(role_dict.pop("_id"))
            role_dict["permissions"] = self._parse_permissions(role_dict.get("permissions", []))
            result = Role(**role_dict)

        # 写入缓存（CAS: 写入前重新检查版本号，避免 TOCTOU）
        try:
            redis = await _get_redis()
            current_version = await redis.get(f"{_ROLE_OBJ_VERSION_PREFIX}{name}")
            current_version = current_version or "0"
            if current_version == version:
                cache_key = f"{_ROLE_OBJ_CACHE_PREFIX}{name}:v{current_version}"
                cache_data = json.dumps(_role_to_cache_dict(result) if result else None)
                await redis.set(cache_key, cache_data, ex=_ROLE_OBJ_CACHE_TTL)
            else:
                logger.debug(f"[Role Cache] Version changed for role {name}, skip stale write")
        except Exception as e:
            logger.warning(f"[Role Cache] Redis set failed for role {name}: {e}")

        return result

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

        if role_data.limits is not None:
            update_dict["limits"] = role_data.limits.model_dump() if role_data.limits else None

        from bson import ObjectId

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(role_id)},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            raise NotFoundError(f"角色 '{role_id}' 不存在")

        result["id"] = str(result.pop("_id"))
        result["permissions"] = self._parse_permissions(result.get("permissions", []))
        role = Role(**result)

        # 写操作后自动失效缓存
        await self.invalidate_cache(existing.name)
        if role_data.name and role_data.name != existing.name:
            await self.invalidate_cache(role_data.name)

        return role

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

        # 删除后自动失效缓存
        if existing:
            await self.invalidate_cache(existing.name)

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
            role_dict["permissions"] = self._parse_permissions(role_dict.get("permissions", []))
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
            role_dict["permissions"] = self._parse_permissions(role_dict.get("permissions", []))
            roles.append(Role(**role_dict))

        return roles

    async def get_by_names(self, names: list[str]) -> list[Role]:
        """
        通过名称列表批量获取角色（每个角色独立走缓存）

        Args:
            names: 角色名称列表

        Returns:
            角色列表
        """
        if not names:
            return []
        roles = []
        for name in names:
            role = await self.get_by_name(name)
            if role:
                roles.append(role)
        return roles

    async def invalidate_cache(self, role_name: str) -> None:
        """使指定角色的缓存失效（递增版本号）"""
        try:
            redis = await _get_redis()
            await redis.incr(f"{_ROLE_OBJ_VERSION_PREFIX}{role_name}")
            logger.info(f"[Role Cache] Invalidated cache for role {role_name}")
        except Exception as e:
            logger.warning(f"[Role Cache] Redis incr failed for role {role_name}: {e}")

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
                # 清除 get_by_name 可能缓存的 None，避免新建角色后查询命中空缓存
                await self.invalidate_cache(role_data["name"])
            elif role_data.get("is_system", False):
                # 系统角色：更新权限列表、描述、限制和is_system标记
                now = datetime.now()
                await self.collection.update_one(
                    {"name": role_data["name"]},
                    {
                        "$set": {
                            "permissions": role_data["permissions"],
                            "description": role_data.get("description"),
                            "limits": role_data.get("limits"),
                            "is_system": True,  # 确保is_system被更新
                            "updated_at": now,
                        }
                    },
                )
                # 系统角色权限可能变更，失效缓存
                await self.invalidate_cache(role_data["name"])
