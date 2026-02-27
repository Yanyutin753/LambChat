"""
Agent 核心模块

提供 Graph Agent 基类和注册机制。
"""

from src.agents.core.base import (
    # 注册
    _AGENT_REGISTRY,
    # 工厂
    AgentFactory,
    # 基类
    BaseGraphAgent,
    GraphBuilder,
    get_agent_class,
    # 辅助
    get_presenter,
    list_registered_agents,
    register_agent,
)
from src.agents.core.graph import (
    AgentGraphBuilder,
    EdgeDefinition,
    NodeDefinition,
    route_by_tool_calls,
)

__all__ = [
    # 基类
    "BaseGraphAgent",
    "GraphBuilder",
    # 注册
    "_AGENT_REGISTRY",
    "register_agent",
    "get_agent_class",
    "list_registered_agents",
    # 工厂
    "AgentFactory",
    # 辅助
    "get_presenter",
    # 旧版兼容
    "AgentGraphBuilder",
    "NodeDefinition",
    "EdgeDefinition",
    "route_by_tool_calls",
]
