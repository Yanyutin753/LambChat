"""
Agent 配置路由

提供 Agent 配置管理接口：
- 全局 Agent 启用/禁用配置
- 角色可用的 Agents 映射
- 用户默认 Agent 设置
"""

from fastapi import APIRouter, Depends

from src.agents.core.base import AgentFactory, list_registered_agents
from src.api.deps import require_permissions
from src.infra.agent.config_storage import get_agent_config_storage
from src.infra.logging import get_logger
from src.infra.role.manager import get_role_manager
from src.kernel.schemas.agent import (
    AgentConfig,
    AgentConfigUpdate,
    GlobalAgentConfigResponse,
    RoleAgentAssignment,
    RoleAgentAssignmentResponse,
    RoleAgentAssignmentUpdate,
    RoleModelAssignment,
    RoleModelAssignmentUpdate,
    UserAgentPreference,
    UserAgentPreferenceResponse,
    UserAgentPreferenceUpdate,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission

router = APIRouter()
logger = get_logger(__name__)


# ============================================
# 管理员接口
# ============================================


@router.get("/global", response_model=GlobalAgentConfigResponse)
async def get_global_agent_config(
    _: TokenPayload = Depends(require_permissions(Permission.AGENT_ADMIN.value)),
):
    """获取全局 Agent 配置"""
    storage = get_agent_config_storage()

    all_agents = AgentFactory.list_agents()
    saved_configs = await storage.get_global_config()
    saved_configs_map = {c.id: c for c in saved_configs}

    # 合并：使用保存的配置，新注册的 agent 默认启用
    agent_configs = []
    for agent in all_agents:
        agent_id = agent["id"]
        if agent_id in saved_configs_map:
            agent_configs.append(saved_configs_map[agent_id])
        else:
            agent_configs.append(
                AgentConfig(
                    id=agent_id,
                    name=agent["name"],
                    description=agent["description"],
                    enabled=True,
                )
            )

    # 持久化新发现的 agents
    await storage.set_global_config(agent_configs)

    return GlobalAgentConfigResponse(
        agents=agent_configs,
        available_agents=[a.id for a in agent_configs if a.enabled],
    )


@router.put("/global", response_model=GlobalAgentConfigResponse)
async def update_global_agent_config(
    config_update: AgentConfigUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.AGENT_ADMIN.value)),
):
    """更新全局 Agent 配置"""
    storage = get_agent_config_storage()

    # 验证 agent IDs 是否已注册
    registered_ids = set(list_registered_agents())
    for agent in config_update.agents:
        if agent.id not in registered_ids:
            from src.kernel.exceptions import ValidationError

            raise ValidationError(f"Agent '{agent.id}' 未注册")

    agents = config_update.agents
    await storage.set_global_config(agents)

    return GlobalAgentConfigResponse(
        agents=agents,
        available_agents=[a.id for a in agents if a.enabled],
    )


@router.get("/roles/{role_id}", response_model=RoleAgentAssignment)
async def get_role_agents(
    role_id: str,
    _: TokenPayload = Depends(require_permissions(Permission.AGENT_ADMIN.value)),
):
    """获取角色的可用 Agents"""
    storage = get_agent_config_storage()
    role_manager = get_role_manager()

    role = await role_manager.get_role(role_id)
    if not role:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"角色 '{role_id}' 不存在")

    allowed_agents = await storage.get_role_agents(role_id) or []

    return RoleAgentAssignment(
        role_id=role_id,
        role_name=role.name,
        allowed_agents=allowed_agents,
    )


@router.put("/roles/{role_id}", response_model=RoleAgentAssignmentResponse)
async def update_role_agents(
    role_id: str,
    assignment: RoleAgentAssignmentUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.AGENT_ADMIN.value)),
):
    """设置角色的可用 Agents"""
    storage = get_agent_config_storage()
    role_manager = get_role_manager()

    role = await role_manager.get_role(role_id)
    if not role:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"角色 '{role_id}' 不存在")

    await storage.set_role_agents(role_id, role.name, assignment.allowed_agents)

    return RoleAgentAssignmentResponse(
        role_id=role_id,
        role_name=role.name,
        allowed_agents=assignment.allowed_agents,
    )


# ============================================
# 角色 Models 管理
# ============================================


@router.get("/roles/{role_id}/models", response_model=RoleModelAssignment)
async def get_role_models(
    role_id: str,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取角色的可用 Models"""
    storage = get_agent_config_storage()
    role_manager = get_role_manager()

    role = await role_manager.get_role(role_id)
    if not role:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"角色 '{role_id}' 不存在")

    allowed_models = await storage.get_role_models(role_id) or []

    return RoleModelAssignment(
        role_id=role_id,
        role_name=role.name,
        allowed_models=allowed_models,
    )


@router.put("/roles/{role_id}/models", response_model=RoleModelAssignment)
async def update_role_models(
    role_id: str,
    assignment: RoleModelAssignmentUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """设置角色的可用 Models"""
    storage = get_agent_config_storage()
    role_manager = get_role_manager()

    role = await role_manager.get_role(role_id)
    if not role:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"角色 '{role_id}' 不存在")

    await storage.set_role_models(role_id, role.name, assignment.allowed_models)

    return RoleModelAssignment(
        role_id=role_id,
        role_name=role.name,
        allowed_models=assignment.allowed_models,
    )


# ============================================
# 用户接口
# ============================================


@router.get("/user/preference", response_model=UserAgentPreference)
async def get_user_preference(
    user: TokenPayload = Depends(require_permissions("agent:read")),
):
    """获取用户的默认 Agent 设置"""
    storage = get_agent_config_storage()
    preference = await storage.get_user_preference(user.sub)

    if not preference:
        return UserAgentPreference(default_agent_id=None)

    return preference


@router.put("/user/preference", response_model=UserAgentPreferenceResponse)
async def update_user_preference(
    preference: UserAgentPreferenceUpdate,
    user: TokenPayload = Depends(require_permissions("agent:read")),
):
    """设置用户的默认 Agent"""
    storage = get_agent_config_storage()
    result = await storage.set_user_preference(user.sub, preference.default_agent_id)

    return UserAgentPreferenceResponse(
        default_agent_id=result.default_agent_id,
    )


@router.delete("/user/preference", response_model=UserAgentPreferenceResponse)
async def delete_user_preference(
    user: TokenPayload = Depends(require_permissions("agent:read")),
):
    """删除用户的默认 Agent 设置"""
    storage = get_agent_config_storage()
    await storage.delete_user_preference(user.sub)

    return UserAgentPreferenceResponse(default_agent_id=None)
