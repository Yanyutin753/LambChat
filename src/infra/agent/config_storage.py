"""
Agent 配置存储层

提供 Agent 配置的数据库操作：
- 全局 Agent 启用/禁用配置
- 角色可用的 Agents 映射
- 用户默认 Agent 设置
"""

from datetime import datetime
from typing import Optional

from src.kernel.config import settings
from src.kernel.schemas.agent import AgentConfig, UserAgentPreference


class AgentConfigStorage:
    """
    Agent 配置存储类

    使用 MongoDB 存储配置数据：
    - 全局 agent 配置 (collection: agent_config)
    - 角色-agents 映射 (collection: role_agents)
    - 用户默认 agent (collection: user_agent_preferences)
    """

    def __init__(self):
        self._config_collection = None
        self._role_agents_collection = None
        self._user_prefs_collection = None

    @property
    def config_collection(self):
        """延迟加载 MongoDB 集合 - 全局配置"""
        if self._config_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._config_collection = db["agent_config"]
        return self._config_collection

    @property
    def role_agents_collection(self):
        """延迟加载 MongoDB 集合 - 角色 Agents"""
        if self._role_agents_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._role_agents_collection = db["role_agents"]
        return self._role_agents_collection

    @property
    def user_prefs_collection(self):
        """延迟加载 MongoDB 集合 - 用户偏好"""
        if self._user_prefs_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._user_prefs_collection = db["user_agent_preferences"]
        return self._user_prefs_collection

    # ============================================
    # 全局 Agent 配置
    # ============================================

    async def get_global_config(self) -> list[AgentConfig]:
        """
        获取全局 Agent 配置

        Returns:
            Agent 配置列表
        """
        doc = await self.config_collection.find_one({"type": "global"})
        if not doc:
            return []

        return [AgentConfig(**agent) for agent in doc.get("agents", [])]

    async def set_global_config(self, agents: list[AgentConfig]) -> list[AgentConfig]:
        """
        设置全局 Agent 配置

        Args:
            agents: Agent 配置列表

        Returns:
            更新后的配置
        """
        now = datetime.now()
        await self.config_collection.update_one(
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
        """
        获取全局启用的 Agent ID 列表

        Returns:
            启用的 Agent ID 列表
        """
        agents = await self.get_global_config()
        return [a.id for a in agents if a.enabled]

    # ============================================
    # 角色 Agents 映射
    # ============================================

    async def get_role_agents(self, role_id: str) -> Optional[list[str]]:
        """
        获取角色的可用 Agents

        Args:
            role_id: 角色 ID

        Returns:
            可用的 Agent ID 列表，None 表示未配置
        """
        doc = await self.role_agents_collection.find_one({"role_id": role_id})
        if not doc:
            return None  # 未配置

        allowed = doc.get("allowed_agents", [])
        return allowed if allowed is not None else None

    async def set_role_agents(
        self, role_id: str, role_name: str, agent_ids: list[str]
    ) -> list[str]:
        """
        设置角色的可用 Agents

        Args:
            role_id: 角色 ID
            role_name: 角色名称
            agent_ids: 可用的 Agent ID 列表

        Returns:
            更新后的 Agent ID 列表
        """
        now = datetime.now()
        await self.role_agents_collection.update_one(
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
        """
        删除角色的 Agents 配置

        Args:
            role_id: 角色 ID

        Returns:
            是否删除成功
        """
        result = await self.role_agents_collection.delete_one({"role_id": role_id})
        return result.deleted_count > 0

    async def get_all_role_agents(self) -> list[dict]:
        """
        获取所有角色的 Agents 配置

        Returns:
            角色配置列表
        """
        cursor = self.role_agents_collection.find()
        results = []
        async for doc in cursor:
            results.append(
                {
                    "role_id": doc["role_id"],
                    "role_name": doc.get("role_name", ""),
                    "allowed_agents": doc.get("allowed_agents", []),
                }
            )
        return results

    # ============================================
    # 用户默认 Agent
    # ============================================

    async def get_user_preference(self, user_id: str) -> Optional[UserAgentPreference]:
        """
        获取用户的默认 Agent 设置

        Args:
            user_id: 用户 ID

        Returns:
            用户偏好设置
        """
        doc = await self.user_prefs_collection.find_one({"user_id": user_id})
        if not doc:
            return None

        return UserAgentPreference(default_agent_id=doc.get("default_agent_id"))

    async def set_user_preference(self, user_id: str, agent_id: str) -> UserAgentPreference:
        """
        设置用户的默认 Agent

        Args:
            user_id: 用户 ID
            agent_id: 默认 Agent ID

        Returns:
            更新后的偏好设置
        """
        now = datetime.now()
        await self.user_prefs_collection.update_one(
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
        """
        删除用户的默认 Agent 设置

        Args:
            user_id: 用户 ID

        Returns:
            是否删除成功
        """
        result = await self.user_prefs_collection.delete_one({"user_id": user_id})
        return result.deleted_count > 0


# 全局单例
_agent_config_storage: Optional[AgentConfigStorage] = None


def get_agent_config_storage() -> AgentConfigStorage:
    """获取 Agent 配置存储单例"""
    global _agent_config_storage
    if _agent_config_storage is None:
        _agent_config_storage = AgentConfigStorage()
    return _agent_config_storage
