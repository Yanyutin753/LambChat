"""
Agent 图编排

使用 LangGraph 构建 Agent 执行图。
"""

from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph


class NodeDefinition(TypedDict):
    """节点定义"""

    name: str
    function: Callable
    description: Optional[str]


class EdgeDefinition(TypedDict):
    """边定义"""

    from_node: str
    to_node: str
    condition: Optional[Callable[[Any], str]]


class AgentGraphBuilder:
    """
    Agent 图构建器

    使用 LangGraph 构建 Agent 执行流程。
    """

    def __init__(self, state_class: type = dict):
        self._state_class = state_class
        self._nodes: Dict[str, Callable] = {}
        self._edges: List[tuple] = []
        self._entry_point: Optional[str] = None
        self._conditional_edges: List[tuple] = []

    def add_node(self, name: str, function: Callable) -> "AgentGraphBuilder":
        """添加节点"""
        self._nodes[name] = function
        return self

    def add_edge(self, from_node: str, to_node: str) -> "AgentGraphBuilder":
        """添加边"""
        self._edges.append((from_node, to_node))
        return self

    def set_entry_point(self, node_name: str) -> "AgentGraphBuilder":
        """设置入口点"""
        self._entry_point = node_name
        return self

    def add_conditional_edges(
        self,
        from_node: str,
        condition: Callable[[Any], str],
        path_map: Dict[str, str],
    ) -> "AgentGraphBuilder":
        """添加条件边"""
        self._conditional_edges.append((from_node, condition, path_map))
        return self

    def build(self) -> Any:
        """构建并编译图"""
        graph = StateGraph(self._state_class)

        # 添加节点
        for name, function in self._nodes.items():
            graph.add_node(name, function)

        # 设置入口点
        if self._entry_point:
            graph.set_entry_point(self._entry_point)

        # 添加普通边
        for from_node, to_node in self._edges:
            if to_node == "END":
                graph.add_edge(from_node, END)
            else:
                graph.add_edge(from_node, to_node)

        # 添加条件边
        for from_node, condition, path_map in self._conditional_edges:
            normalized_map = {}
            for key, value in path_map.items():
                normalized_map[key] = END if value == "END" else value
            graph.add_conditional_edges(from_node, condition, normalized_map)

        return graph.compile()


def route_by_tool_calls(state: Any) -> str:
    """根据工具调用路由"""
    messages = (
        state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
    )
    last_message = messages[-1] if messages else None

    if not last_message:
        return "end"

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return "end"
