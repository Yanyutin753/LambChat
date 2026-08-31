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
from src.kernel.errors import ErrorCode
from src.kernel.schemas.agent import (
    AgentCatalogConfig,
    AgentCatalogConfigResponse,
    AgentCatalogConfigUpdate,
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


def _catalog_entry_from_registered(
    agent: dict,
    saved: AgentCatalogConfig | AgentConfig | None = None,
) -> AgentCatalogConfig:
    """Merge registered runtime defaults with persisted catalog metadata."""
    saved_sort_order = getattr(saved, "sort_order", None) if saved else None
    return AgentCatalogConfig(
        id=agent["id"],
        name=agent.get("name") or agent["id"],
        description=agent.get("description") or "",
        enabled=saved.enabled if saved else True,
        icon=(getattr(saved, "icon", None) if saved else None) or "Bot",
        sort_order=saved_sort_order
        if saved_sort_order is not None
        else agent.get("sort_order", 100),
        labels=getattr(saved, "labels", {}) if saved else {},
    )


async def _load_catalog_config() -> list[AgentCatalogConfig]:
    storage = get_agent_config_storage()
    all_agents = AgentFactory.list_agents()
    saved_configs = await storage.get_catalog_config()
    if not saved_configs and hasattr(storage, "get_global_config"):
        global_configs = await storage.get_global_config()
        saved_configs_map: dict[str, AgentCatalogConfig | AgentConfig] = {
            c.id: c for c in global_configs
        }
    else:
        saved_configs_map = {c.id: c for c in saved_configs}

    catalog = [
        _catalog_entry_from_registered(agent, saved_configs_map.get(agent["id"]))
        for agent in all_agents
    ]
    catalog.sort(key=lambda agent: (agent.sort_order, agent.name))
    await storage.set_catalog_config(catalog)
    return catalog


def _catalog_to_global_config(agent: AgentCatalogConfig) -> AgentConfig:
    return AgentConfig(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        enabled=agent.enabled,
        icon=agent.icon,
        sort_order=agent.sort_order,
        labels=agent.labels,
    )


# ============================================
# 管理员接口
# ============================================


@router.get("/global", response_model=GlobalAgentConfigResponse)
async def get_global_agent_config(
    _: TokenPayload = Depends(require_permissions(Permission.AGENT_ADMIN.value)),
):
    """获取全局 Agent 配置"""
    catalog = await _load_catalog_config()
    agent_configs = [_catalog_to_global_config(agent) for agent in catalog]

    return GlobalAgentConfigResponse(
        agents=agent_configs,
        available_agents=[a.id for a in agent_configs if a.enabled],
    )


@router.get("/catalog", response_model=AgentCatalogConfigResponse)
async def get_agent_catalog_config(
    _: TokenPayload = Depends(require_permissions(Permission.AGENT_ADMIN.value)),
):
    """获取可配置 Agent 展示目录。"""
    catalog = await _load_catalog_config()
    return AgentCatalogConfigResponse(
        agents=catalog,
        available_agents=[a.id for a in catalog if a.enabled],
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

            raise ValidationError(ErrorCode.AGENT_NOT_REGISTERED, args={"agent": agent.id})

    registered_agents = {agent["id"]: agent for agent in AgentFactory.list_agents()}
    catalog_agents = [
        AgentCatalogConfig(
            id=agent.id,
            name=agent.name or registered_agents[agent.id].get("name", agent.id),
            description=agent.description or registered_agents[agent.id].get("description", ""),
            enabled=agent.enabled,
            icon=agent.icon or "Bot",
            sort_order=agent.sort_order
            if agent.sort_order is not None
            else registered_agents[agent.id].get("sort_order", 100),
            labels=agent.labels,
        )
        for agent in config_update.agents
    ]
    await storage.set_catalog_config(catalog_agents)
    agents = [_catalog_to_global_config(agent) for agent in catalog_agents]

    return GlobalAgentConfigResponse(
        agents=agents,
        available_agents=[a.id for a in agents if a.enabled],
    )


@router.put("/catalog", response_model=AgentCatalogConfigResponse)
async def update_agent_catalog_config(
    config_update: AgentCatalogConfigUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.AGENT_ADMIN.value)),
):
    """更新可配置 Agent 展示目录。"""
    storage = get_agent_config_storage()

    registered_ids = set(list_registered_agents())
    for agent in config_update.agents:
        if agent.id not in registered_ids:
            from src.kernel.exceptions import ValidationError

            raise ValidationError(ErrorCode.AGENT_NOT_REGISTERED, args={"agent": agent.id})

    registered_agents = {agent["id"]: agent for agent in AgentFactory.list_agents()}
    agents = [
        AgentCatalogConfig(
            id=agent.id,
            name=agent.name or registered_agents[agent.id].get("name", agent.id),
            description=agent.description or registered_agents[agent.id].get("description", ""),
            enabled=agent.enabled,
            icon=agent.icon or "Bot",
            sort_order=agent.sort_order,
            labels=agent.labels,
        )
        for agent in config_update.agents
    ]
    await storage.set_catalog_config(agents)

    return AgentCatalogConfigResponse(
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

        raise NotFoundError(ErrorCode.ROLE_NOT_FOUND)

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

        raise NotFoundError(ErrorCode.ROLE_NOT_FOUND)

    allowed_agents = await storage.set_role_agents(role_id, role.name, assignment.allowed_agents)

    return RoleAgentAssignmentResponse(
        role_id=role_id,
        role_name=role.name,
        allowed_agents=allowed_agents,
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

        raise NotFoundError(ErrorCode.ROLE_NOT_FOUND)

    allowed_models = await storage.get_role_models(role_id)

    return RoleModelAssignment(
        role_id=role_id,
        role_name=role.name,
        allowed_models=allowed_models or [],
        configured=allowed_models is not None,
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

        raise NotFoundError(ErrorCode.ROLE_NOT_FOUND)

    allowed_models = await storage.set_role_models(role_id, role.name, assignment.allowed_models)

    return RoleModelAssignment(
        role_id=role_id,
        role_name=role.name,
        allowed_models=allowed_models,
        configured=True,
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
