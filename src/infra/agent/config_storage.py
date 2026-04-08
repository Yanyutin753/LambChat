"""
Agent 配置存储层

提供 Agent 配置的数据库操作：
- 全局 Agent 启用/禁用配置
- 角色可用的 Agents 映射
- 用户默认 Agent 设置
"""

from datetime import datetime, timezone
from typing import Any, Optional

from src.kernel.config import settings
from src.kernel.schemas.agent import AgentConfig, UserAgentPreference

# MongoDB 集合名称
_COLL_AGENT_CONFIG = "agent_config"
_COLL_ROLE_AGENTS = "role_agents"
_COLL_ROLE_MODELS = "role_models"
_COLL_USER_PREFERENCES = "user_agent_preferences"


class AgentConfigStorage:
    """
    Agent 配置存储类

    使用 MongoDB 存储配置数据：
    - 全局 agent 配置 (collection: agent_config)
    - 角色-agents 映射 (collection: role_agents)
    - 用户默认 agent (collection: user_agent_preferences)
    """

    def __init__(self):
        self._collections: dict[str, Any] = {}

    def _get_collection(self, name: str):
        """延迟加载 MongoDB 集合"""
        if name not in self._collections:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collections[name] = db[name]
        return self._collections[name]

    async def ensure_indexes(self):
        """创建必要的 MongoDB 索引"""
        await self._get_collection(_COLL_AGENT_CONFIG).create_index("type", unique=True)
        await self._get_collection(_COLL_ROLE_AGENTS).create_index("role_id", unique=True)
        await self._get_collection(_COLL_ROLE_MODELS).create_index("role_id", unique=True)
        await self._get_collection(_COLL_USER_PREFERENCES).create_index("user_id", unique=True)

    # ============================================
    # 全局 Agent 配置
    # ============================================

    async def get_global_config(self) -> list[AgentConfig]:
        """获取全局 Agent 配置"""
        doc = await self._get_collection(_COLL_AGENT_CONFIG).find_one({"type": "global"})
        if not doc:
            return []
        return [AgentConfig(**agent) for agent in doc.get("agents", [])]

    async def set_global_config(self, agents: list[AgentConfig]) -> list[AgentConfig]:
        """设置全局 Agent 配置"""
        now = datetime.now(timezone.utc)
        await self._get_collection(_COLL_AGENT_CONFIG).update_one(
            {"type": "global"},
            {
                "$set": {
                    "agents": [agent.model_dump() for agent in agents],
                    "updated_at": now.isoformat(),
                }
            },
            upsert=True,
        )
        return agents

    async def get_enabled_agent_ids(self) -> list[str]:
        """获取全局启用的 Agent ID 列表"""
        agents = await self.get_global_config()
        return [a.id for a in agents if a.enabled]

    # ============================================
    # 角色 Agents 映射
    # ============================================

    async def get_role_agents(self, role_id: str) -> Optional[list[str]]:
        """
        获取角色的可用 Agents

        Returns:
            可用的 Agent ID 列表，None 表示未配置
        """
        doc = await self._get_collection(_COLL_ROLE_AGENTS).find_one({"role_id": role_id})
        if not doc:
            return None
        return doc.get("allowed_agents") or None

    async def set_role_agents(
        self, role_id: str, role_name: str, agent_ids: list[str]
    ) -> list[str]:
        """设置角色的可用 Agents"""
        now = datetime.now(timezone.utc)
        await self._get_collection(_COLL_ROLE_AGENTS).update_one(
            {"role_id": role_id},
            {
                "$set": {
                    "role_name": role_name,
                    "allowed_agents": agent_ids,
                    "updated_at": now.isoformat(),
                }
            },
            upsert=True,
        )
        return agent_ids

    async def delete_role_agents(self, role_id: str) -> bool:
        """删除角色的 Agents 配置"""
        result = await self._get_collection(_COLL_ROLE_AGENTS).delete_one({"role_id": role_id})
        return result.deleted_count > 0

    async def get_all_role_agents(self) -> list[dict]:
        """获取所有角色的 Agents 配置"""
        cursor = self._get_collection(_COLL_ROLE_AGENTS).find()
        return [
            {
                "role_id": doc["role_id"],
                "role_name": doc.get("role_name", ""),
                "allowed_agents": doc.get("allowed_agents", []),
            }
            async for doc in cursor
        ]

    # ============================================
    # 角色 Models 映射
    # ============================================

    async def get_role_models(self, role_id: str) -> Optional[list[str]]:
        """
        获取角色的可用 Models

        Returns:
            可用的 Model value 列表，None 表示未配置（不限制）
        """
        doc = await self._get_collection(_COLL_ROLE_MODELS).find_one({"role_id": role_id})
        if not doc:
            return None
        return doc.get("allowed_models") or None

    async def set_role_models(
        self, role_id: str, role_name: str, model_values: list[str]
    ) -> list[str]:
        """设置角色的可用 Models"""
        now = datetime.now(timezone.utc)
        await self._get_collection(_COLL_ROLE_MODELS).update_one(
            {"role_id": role_id},
            {
                "$set": {
                    "role_name": role_name,
                    "allowed_models": model_values,
                    "updated_at": now.isoformat(),
                }
            },
            upsert=True,
        )
        return model_values

    async def delete_role_models(self, role_id: str) -> bool:
        """删除角色的 Models 配置"""
        result = await self._get_collection(_COLL_ROLE_MODELS).delete_one({"role_id": role_id})
        return result.deleted_count > 0

    async def get_all_role_models(self) -> list[dict]:
        """获取所有角色的 Models 配置"""
        cursor = self._get_collection(_COLL_ROLE_MODELS).find()
        return [
            {
                "role_id": doc["role_id"],
                "role_name": doc.get("role_name", ""),
                "allowed_models": doc.get("allowed_models", []),
            }
            async for doc in cursor
        ]

    # ============================================
    # 用户默认 Agent
    # ============================================

    async def get_user_preference(self, user_id: str) -> Optional[UserAgentPreference]:
        """获取用户的默认 Agent 设置"""
        doc = await self._get_collection(_COLL_USER_PREFERENCES).find_one({"user_id": user_id})
        if not doc:
            return None
        return UserAgentPreference(default_agent_id=doc.get("default_agent_id"))

    async def set_user_preference(self, user_id: str, agent_id: str) -> UserAgentPreference:
        """设置用户的默认 Agent"""
        now = datetime.now(timezone.utc)
        await self._get_collection(_COLL_USER_PREFERENCES).update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "default_agent_id": agent_id,
                    "updated_at": now.isoformat(),
                }
            },
            upsert=True,
        )
        return UserAgentPreference(default_agent_id=agent_id)

    async def delete_user_preference(self, user_id: str) -> bool:
        """删除用户的默认 Agent 设置"""
        result = await self._get_collection(_COLL_USER_PREFERENCES).delete_one({"user_id": user_id})
        return result.deleted_count > 0


# 全局单例
_agent_config_storage: Optional[AgentConfigStorage] = None


def get_agent_config_storage() -> AgentConfigStorage:
    """获取 Agent 配置存储单例"""
    global _agent_config_storage
    if _agent_config_storage is None:
        _agent_config_storage = AgentConfigStorage()
    return _agent_config_storage
