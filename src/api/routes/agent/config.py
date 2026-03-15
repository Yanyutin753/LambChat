"""
Agent 配置路由

提供 Agent 配置管理接口：
- 全局 Agent 启用/禁用配置
- 角色可用的 Agents 映射
- 用户默认 Agent 设置
"""

import logging

from fastapi import APIRouter, Depends

from src.agents.core.base import AgentFactory
from src.api.deps import get_current_user_required
from src.infra.agent.config_storage import get_agent_config_storage
from src.infra.role.manager import get_role_manager
from src.kernel.schemas.agent import (
    AgentConfig,
    AgentConfigUpdate,
    GlobalAgentConfigResponse,
    RoleAgentAssignment,
    RoleAgentAssignmentUpdate,
    UserAgentPreference,
    UserAgentPreferenceUpdate,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# 管理员接口
# ============================================


@router.get("/global", response_model=GlobalAgentConfigResponse)
async def get_global_agent_config(
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取全局 Agent 配置

    需要 AGENT_ADMIN 权限
    """
    # 检查权限
    if Permission.AGENT_ADMIN.value not in user.permissions:
        from src.kernel.exceptions import AuthorizationError

        raise AuthorizationError("需要 AGENT_ADMIN 权限")

    storage = get_agent_config_storage()

    # 获取所有注册的 agents
    all_agents = AgentFactory.list_agents()

    # 获取已保存的配置
    saved_configs = await storage.get_global_config()
    saved_configs_map = {c.id: c for c in saved_configs}

    # 合并：使用保存的配置，不存在的使用默认值
    agent_configs = []
    for agent in all_agents:
        agent_id = agent["id"]
        if agent_id in saved_configs_map:
            agent_configs.append(saved_configs_map[agent_id])
        else:
            # 新注册的 agent，默认启用
            agent_configs.append(
                AgentConfig(
                    id=agent_id,
                    name=agent["name"],
                    description=agent["description"],
                    enabled=True,
                )
            )

    # 保存新发现的 agents
    await storage.set_global_config(agent_configs)

    return GlobalAgentConfigResponse(
        agents=agent_configs,
        available_agents=[a.id for a in agent_configs if a.enabled],
    )


@router.put("/global")
async def update_global_agent_config(
    config_update: AgentConfigUpdate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新全局 Agent 配置

    需要 AGENT_ADMIN 权限
    """
    # 检查权限
    if Permission.AGENT_ADMIN.value not in user.permissions:
        from src.kernel.exceptions import AuthorizationError

        raise AuthorizationError("需要 AGENT_ADMIN 权限")

    storage = get_agent_config_storage()
    await storage.set_global_config(config_update.agents)

    return {
        "message": "全局 Agent 配置已更新",
        "agents": config_update.agents,
    }


@router.get("/roles/{role_id}", response_model=RoleAgentAssignment)
async def get_role_agents(
    role_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取角色的可用 Agents

    需要 AGENT_ADMIN 权限
    """
    # 检查权限
    if Permission.AGENT_ADMIN.value not in user.permissions:
        from src.kernel.exceptions import AuthorizationError

        raise AuthorizationError("需要 AGENT_ADMIN 权限")

    storage = get_agent_config_storage()
    role_manager = get_role_manager()

    # 获取角色信息
    role = await role_manager.get_role(role_id)
    if not role:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"角色 '{role_id}' 不存在")

    allowed_agents = await storage.get_role_agents(role_id)
    # None 表示未配置，返回空列表
    if allowed_agents is None:
        allowed_agents = []

    return RoleAgentAssignment(
        role_id=role_id,
        role_name=role.name,
        allowed_agents=allowed_agents,
    )


@router.put("/roles/{role_id}")
async def update_role_agents(
    role_id: str,
    assignment: RoleAgentAssignmentUpdate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    设置角色的可用 Agents

    需要 AGENT_ADMIN 权限
    """
    # 检查权限
    if Permission.AGENT_ADMIN.value not in user.permissions:
        from src.kernel.exceptions import AuthorizationError

        raise AuthorizationError("需要 AGENT_ADMIN 权限")

    storage = get_agent_config_storage()
    role_manager = get_role_manager()

    # 获取角色信息
    role = await role_manager.get_role(role_id)
    if not role:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"角色 '{role_id}' 不存在")

    await storage.set_role_agents(role_id, role.name, assignment.allowed_agents)

    return {
        "message": f"角色 '{role.name}' 的可用 Agents 已更新",
        "role_id": role_id,
        "allowed_agents": assignment.allowed_agents,
    }


# ============================================
# 用户接口
# ============================================


@router.get("/user/preference", response_model=UserAgentPreference)
async def get_user_preference(
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取用户的默认 Agent 设置
    """
    storage = get_agent_config_storage()
    preference = await storage.get_user_preference(user.sub)

    if not preference:
        return UserAgentPreference(default_agent_id=None)

    return preference


@router.put("/user/preference")
async def update_user_preference(
    preference: UserAgentPreferenceUpdate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    设置用户的默认 Agent
    """
    storage = get_agent_config_storage()
    result = await storage.set_user_preference(user.sub, preference.default_agent_id)

    return {
        "message": "默认 Agent 已设置",
        "default_agent_id": result.default_agent_id,
    }


@router.delete("/user/preference")
async def delete_user_preference(
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    删除用户的默认 Agent 设置
    """
    storage = get_agent_config_storage()
    await storage.delete_user_preference(user.sub)

    return {"message": "默认 Agent 设置已删除"}
