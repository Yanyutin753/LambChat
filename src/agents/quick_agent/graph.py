"""
Quick Agent - 快问快答

消息直发 LLM，单节点图，无工具/技能/子代理/沙箱。
完全复用 BaseGraphAgent 的流式执行链路（metadata/事件处理/用量/done），
历史由外层图 messages channel + checkpointer 维护。

架构:
    START -> quick_agent_node -> END
"""

from src.agents.core.base import BaseGraphAgent, GraphBuilder, register_agent
from src.agents.quick_agent.nodes import quick_agent_node
from src.agents.quick_agent.state import QuickAgentState
from src.infra.logging import get_logger

logger = get_logger(__name__)


@register_agent("quick")
class QuickAgent(BaseGraphAgent):
    """
    Quick Agent - 快问快答

    适用于：
    - 快速问答、闲聊、翻译、改写等单轮即可完成的请求
    - 对延迟敏感、不需要任何工具调用的场景
    """

    _agent_id = "quick"
    _agent_name = "Everyday Assistant"
    _name_key = "agents.quick.name"
    _description = "Everyday questions, writing and translation, with direct responses."
    _description_key = "agents.quick.description"
    _version = "1.0.0"
    _sort_order = 2  # 排序权重，数值越小越靠前（search=1, quick=2）
    _supports_sandbox = False  # 不支持沙箱环境
    _icon = "Zap"

    @property
    def state_class(self) -> type:
        return QuickAgentState

    async def initialize(self) -> None:
        """初始化 Agent

        checkpointer 必须走 get_async_checkpointer()（按 CHECKPOINT_BACKEND
        选 PG/Mongo），与 fast/search/team 的内层图共用同一存储与
        thread_id=session_id 命名空间——否则生产 PG 环境下 quick 的历史
        会写进 Mongo，跨 agent 切换互通静默失效。基类默认的 Mongo 工厂
        不感知 CHECKPOINT_BACKEND，故此处覆写。
        """
        if self._initialized:
            return

        from src.infra.storage.checkpoint import get_async_checkpointer

        self._checkpointer = await get_async_checkpointer()
        builder = GraphBuilder(self.state_class)
        self.build_graph(builder)
        self._graph = builder.compile(
            checkpointer=self._checkpointer,
            recursion_limit=self.recursion_limit,
        )

        self._initialized = True
        logger.info(f"{self.name} initialized (direct LLM, shared checkpoint namespace)")

    def build_graph(self, builder: GraphBuilder) -> None:
        """
        构建 Graph

        当前结构: START -> quick_agent_node -> END
        """
        builder.add_node("agent", quick_agent_node)
        builder.set_entry_point("agent")
        builder.add_edge("agent", "END")
