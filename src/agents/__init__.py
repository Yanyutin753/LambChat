"""
Agent 模块

提供 Graph Agent 基类和注册机制。

每个 Agent 就是一个 CompiledGraph：
- 流式请求接入 graph
- 节点通过 config 获取 Presenter 输出 SSE 事件
"""

from src.agents.core import (
    # 注册
    _AGENT_REGISTRY,
    # 工厂
    AgentFactory,
    # 旧版兼容
    AgentGraphBuilder,
    # 基类
    BaseGraphAgent,
    EdgeDefinition,
    GraphBuilder,
    NodeDefinition,
    get_agent_class,
    # 辅助
    get_presenter,
    list_registered_agents,
    register_agent,
    route_by_tool_calls,
)


def discover_agents() -> None:
    """发现并注册所有 Agent"""
    # 导入会触发 @register_agent 装饰器
    from src.agents.search_agent import SearchAgent  # noqa: F401


async def get_agent_async(agent_id: str) -> BaseGraphAgent:
    """异步获取 Agent 实例"""
    return await AgentFactory.get(agent_id)


def list_agents() -> list[dict[str, str]]:
    """列出所有注册的 Agent"""
    return AgentFactory.list_agents()


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
    # 便捷函数
    "get_agent_async",
    "list_agents",
    "discover_agents",
    # 旧版兼容
    "AgentGraphBuilder",
    "NodeDefinition",
    "EdgeDefinition",
    "route_by_tool_calls",
]
