"""
Fast Agent 模块 - 快速响应，无沙箱

Agent 已通过 @register_agent("fast") 装饰器自动注册。
"""

from src.agents.fast_agent.context import FastAgentContext
from src.agents.fast_agent.graph import FastAgent
from src.agents.fast_agent.nodes import fast_agent_node
from src.agents.fast_agent.state import FastAgentState

__all__ = [
    "FastAgent",
    "FastAgentContext",
    "FastAgentState",
    "fast_agent_node",
]
