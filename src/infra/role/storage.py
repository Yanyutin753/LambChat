"""
角色存储层

提供角色的数据库操作。
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.redis import create_redis_client
from src.infra.utils.datetime import to_iso, utc_now
from src.kernel.config import settings
from src.kernel.errors import ErrorCode
from src.kernel.exceptions import NotFoundError, ValidationError
from src.kernel.schemas.role import Role, RoleCreate, RoleLimits, RoleUpdate
from src.kernel.types import Permission

logger = get_logger(__name__)

# 角色对象缓存 key 前缀和 TTL（按角色名缓存，所有调用方共享）
_ROLE_OBJ_CACHE_PREFIX = "role:obj:"
_ROLE_OBJ_VERSION_PREFIX = "role:obj_ver:"
_ROLE_OBJ_CACHE_TTL = 300  # 5 分钟
ROLE_ALLOWED_AGENTS_LIMIT = 100
ROLE_LIST_LIMIT_MAX = 200
ROLE_BATCH_LOOKUP_LIMIT = 100
_role_cache_redis = None


async def _get_redis():
    """Get a dedicated Redis client for role cache operations."""
    global _role_cache_redis
    if _role_cache_redis is None:
        _role_cache_redis = create_redis_client(isolated_pool=True)
    return _role_cache_redis


async def close_role_cache_redis() -> None:
    """Close the dedicated Redis client used by the role object cache."""
    global _role_cache_redis
    redis = _role_cache_redis
    _role_cache_redis = None
    if redis is None:
        return
    try:
        await redis.aclose()
    except Exception as e:
        logger.warning("[Role Cache] Failed to close Redis client: %s", e)


def _role_to_cache_dict(role: Role) -> dict:
    """将 Role 对象序列化为 JSON 可存储的 dict。"""
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "permissions": [p if isinstance(p, str) else p.value for p in role.permissions],
        "allowed_agents": _bounded_allowed_agents(role.allowed_agents),
        "limits": role.limits.model_dump() if role.limits else None,
        "is_system": role.is_system,
        "created_at": to_iso(role.created_at)
        if isinstance(role.created_at, datetime)
        else str(role.created_at),
        "updated_at": to_iso(role.updated_at)
        if isinstance(role.updated_at, datetime)
        else str(role.updated_at),
    }


def _cache_dict_to_role(data: dict | None) -> Role | None:
    """将缓存 dict 反序列化为 Role 对象。"""
    if data is None:
        return None
    _normalize_role_dict(data)
    return Role(**data)


def _bounded_allowed_agents(allowed_agents: list[str] | None) -> list[str]:
    if not allowed_agents:
        return []
    bounded = []
    seen = set()
    for agent_id in allowed_agents:
        if agent_id in seen:
            continue
        seen.add(agent_id)
        bounded.append(agent_id)
        if len(bounded) >= ROLE_ALLOWED_AGENTS_LIMIT:
            break
    return bounded


def _bounded_list_limit(limit: int) -> int:
    return min(max(int(limit), 1), ROLE_LIST_LIMIT_MAX)


def _bounded_unique_strings(values: list[str], limit: int) -> list[str]:
    bounded: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        bounded.append(value)
        if len(bounded) >= limit:
            break
    return bounded


def _normalize_role_dict(data: dict) -> dict:
    if data.get("limits"):
        data["limits"] = RoleLimits(**data["limits"])
    if isinstance(data.get("created_at"), str):
        data["created_at"] = datetime.fromisoformat(data["created_at"])
    if isinstance(data.get("updated_at"), str):
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
    # 还原权限字符串为 Permission 枚举，与 DB 路径保持一致
    if isinstance(data.get("permissions"), list):
        data["permissions"] = _parse_permissions_static(data["permissions"])
    data["allowed_agents"] = _bounded_allowed_agents(data.get("allowed_agents"))
    return data


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

    async def ensure_indexes(self) -> None:
        """Create a unique index on role name (get_by_name is a RBAC hot path)."""
        try:
            await self.collection.create_index(
                [("name", 1)],
                name="role_name_unique_idx",
                unique=True,
                background=True,
            )
            logger.info("Role storage indexes ensured")
        except Exception as e:
            logger.error(f"Failed to create role storage indexes: {e}")

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
            raise ValidationError(ErrorCode.ROLE_NAME_EXISTS, args={"name": role_data.name})

        now = utc_now()
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
        return Role(**_normalize_role_dict(role_dict))

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
                cached_data = await run_blocking_io(json.loads, cached)
                return _cache_dict_to_role(cached_data)
        except Exception as e:
            logger.warning(f"[Role Cache] Redis get failed for role {name}: {e}")

        # 缓存未命中，查询数据库
        logger.debug(f"[Role Cache] Miss for role {name}")
        role_dict = await self.collection.find_one({"name": name})

        if not role_dict:
            result = None
        else:
            role_dict["id"] = str(role_dict.pop("_id"))
            result = Role(**_normalize_role_dict(role_dict))

        # 写入缓存（CAS: 写入前重新检查版本号，避免 TOCTOU）
        try:
            redis = await _get_redis()
            current_version = await redis.get(f"{_ROLE_OBJ_VERSION_PREFIX}{name}")
            current_version = current_version or "0"
            if current_version == version:
                cache_key = f"{_ROLE_OBJ_CACHE_PREFIX}{name}:v{current_version}"
                cache_data = await run_blocking_io(
                    json.dumps,
                    _role_to_cache_dict(result) if result else None,
                )
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
            raise NotFoundError(ErrorCode.ROLE_NOT_FOUND)

        if existing.is_system:
            raise ValidationError(
                ErrorCode.SYSTEM_ROLE_PROTECTED, message="System roles cannot be modified"
            )

        update_dict: dict = {"updated_at": utc_now()}

        if role_data.name is not None:
            # 检查新名称是否已存在
            name_check = await self.get_by_name(role_data.name)
            if name_check and name_check.id != role_id:
                raise ValidationError(ErrorCode.ROLE_NAME_EXISTS, args={"name": role_data.name})
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
            raise NotFoundError(ErrorCode.ROLE_NOT_FOUND)

        result["id"] = str(result.pop("_id"))
        role = Role(**_normalize_role_dict(result))

        # 写操作后自动失效缓存
        await self.invalidate_cache(existing.name)
        if role_data.name and role_data.name != existing.name:
            await self.invalidate_cache(role_data.name)
        try:
            from src.api.deps import clear_auth_cache

            clear_auth_cache()
        except Exception:
            pass

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
            raise ValidationError(
                ErrorCode.SYSTEM_ROLE_PROTECTED, message="System roles cannot be deleted"
            )

        from bson import ObjectId

        result = await self.collection.delete_one({"_id": ObjectId(role_id)})

        # 删除后自动失效缓存
        if existing:
            await self.invalidate_cache(existing.name)
            try:
                from src.api.deps import clear_auth_cache

                clear_auth_cache()
            except Exception:
                pass

        return result.deleted_count > 0

    async def list_roles(
        self,
        skip: int = 0,
        limit: int = 100,
        q: str | None = None,
    ) -> list[Role]:
        """
        列出角色

        Args:
            skip: 跳过数量
            limit: 返回数量

        Returns:
            角色列表
        """
        limit = _bounded_list_limit(limit)
        query: dict[str, Any] = {}
        if q:
            escaped_q = re.escape(q)
            query["$or"] = [
                {"name": {"$regex": escaped_q, "$options": "i"}},
                {"description": {"$regex": escaped_q, "$options": "i"}},
            ]

        cursor = self.collection.find(query).sort("name", 1).skip(skip).limit(limit)
        roles = []

        async for role_dict in cursor:
            role_dict["id"] = str(role_dict.pop("_id"))
            roles.append(Role(**_normalize_role_dict(role_dict)))

        return roles

    async def count_roles(self, q: str | None = None) -> int:
        """Count roles matching an optional search query."""
        query: dict[str, Any] = {}
        if q:
            escaped_q = re.escape(q)
            query["$or"] = [
                {"name": {"$regex": escaped_q, "$options": "i"}},
                {"description": {"$regex": escaped_q, "$options": "i"}},
            ]
        return await self.collection.count_documents(query)

    async def get_by_ids(self, role_ids: list[str]) -> list[Role]:
        """
        通过 ID 列表获取角色

        Args:
            role_ids: 角色 ID 列表

        Returns:
            角色列表
        """
        from bson import ObjectId

        object_ids: list[ObjectId] = []
        for role_id in _bounded_unique_strings(role_ids, ROLE_BATCH_LOOKUP_LIMIT):
            try:
                object_ids.append(ObjectId(role_id))
            except Exception:
                continue
        if not object_ids:
            return []
        cursor = self.collection.find({"_id": {"$in": object_ids}})
        roles = []

        async for role_dict in cursor:
            role_dict["id"] = str(role_dict.pop("_id"))
            roles.append(Role(**_normalize_role_dict(role_dict)))

        return roles

    async def get_by_names(self, names: list[str]) -> list[Role]:
        """
        通过名称列表批量获取角色（每个角色独立走缓存）

        Args:
            names: 角色名称列表

        Returns:
            角色列表
        """
        names = _bounded_unique_strings(names, ROLE_BATCH_LOOKUP_LIMIT)
        if not names:
            return []
        results = await asyncio.gather(*(self.get_by_name(name) for name in names))
        return [role for role in results if role]

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
                now = utc_now()
                await self.collection.insert_one(
                    {
                        **role_data,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                # 清除 get_by_name 可能缓存的 None，避免新建角色后查询命中空缓存
                await self.invalidate_cache(role_data["name"])
            elif role_data["name"] == "user":
                migration_key = "scheduled_task_permissions_v1"
                raw_role = await self.collection.find_one(
                    {"name": role_data["name"]},
                    {"permissions": 1, "migrations": 1},
                )
                migrations = (raw_role or {}).get("migrations") or {}
                if not migrations.get(migration_key):
                    now = utc_now()
                    scheduled_task_permissions = [
                        Permission.SCHEDULED_TASK_READ.value,
                        Permission.SCHEDULED_TASK_WRITE.value,
                        Permission.SCHEDULED_TASK_DELETE.value,
                    ]
                    await self.collection.update_one(
                        {"name": role_data["name"]},
                        {
                            "$addToSet": {
                                "permissions": {"$each": scheduled_task_permissions},
                            },
                            "$set": {
                                f"migrations.{migration_key}": True,
                                "updated_at": now,
                            },
                        },
                    )
                    await self.invalidate_cache(role_data["name"])
                    try:
                        from src.api.deps import clear_auth_cache

                        clear_auth_cache()
                    except Exception:
                        pass
            elif role_data.get("is_system", False):
                # 系统角色：更新权限列表、描述、限制和is_system标记
                now = utc_now()
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
