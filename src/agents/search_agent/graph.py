"""
Search Agent - 基于 LangGraph 的 Graph Agent

外层 Graph 管理多个节点，agent_node 执行 LLM + 工具调用。
后续可扩展：检索节点、记忆节点、规划节点等。

架构:
    START -> agent_node -> END

优化点：
1. 去掉外层 checkpoint（只保留内层 MemorySaver）
2. 使用 stream_mode="updates" 减少事件开销

后续可扩展:
    - START -> retrieve_node -> agent_node -> END
    - START -> plan_node -> agent_node -> summarize_node -> END
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict

from langchain_core.runnables import RunnableConfig

from src.agents.core.base import BaseGraphAgent, GraphBuilder, register_agent
from src.agents.search_agent.context import AgentContext
from src.agents.search_agent.nodes import agent_node
from src.agents.search_agent.state import SearchAgentState

# 设置用户上下文，供 backend 使用
from src.infra.backend.context import set_user_context
from src.infra.task.manager import TaskInterruptedError
from src.infra.writer.present import Presenter, PresenterConfig
from src.kernel.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# SearchAgent 类
# ============================================================================


@register_agent("search")
class SearchAgent(BaseGraphAgent):
    """
    Search Agent

    基于 LangGraph 的多节点 Agent，当前包含 agent_node。
    可扩展：检索节点、记忆节点、规划节点等。
    """

    _agent_id = "search"
    _agent_name = "Search Agent"
    _name_key = "agents.search.name"
    _description = "基于 LangGraph 的搜索和执行 Agent"
    _description_key = "agents.search.description"
    _version = "1.0.0"
    # Agent 选项配置（供前端渲染）
    _options = {
        "enable_thinking": {
            "type": "boolean",
            "default": False,
            "label": "Enable Thinking",
            "label_key": "agentOptions.enableThinking.label",
            "description": "Enable extended thinking mode (Anthropic models only)",
            "description_key": "agentOptions.enableThinking.description",
            "icon": "Brain",
        }
    }

    @property
    def state_class(self) -> type:
        return SearchAgentState

    def build_graph(self, builder: GraphBuilder) -> None:
        """
        构建 Graph

        当前结构: START -> agent_node -> END

        后续可扩展:
        - START -> retrieve_node -> agent_node -> END
        - START -> plan_node -> agent_node -> summarize_node -> END
        """
        builder.add_node("agent", agent_node)
        builder.set_entry_point("agent")
        builder.add_edge("agent", "END")

    async def initialize(self) -> None:
        """初始化 Agent"""
        if self._initialized:
            return

        # 不使用外层 checkpointer（历史消息由内层 MemorySaver 管理）
        # 构建 graph
        builder = GraphBuilder(self.state_class)
        self.build_graph(builder)
        self._graph = builder.compile(
            checkpointer=None,  # 不使用 checkpoint
            recursion_limit=settings.SESSION_MAX_RUNS_PER_SESSION,
        )

        self._initialized = True
        logger.info(f"{self.name} initialized (no outer checkpointer)")

    async def _stream(
        self,
        message: str,
        session_id: str,
        user_id: str | None = None,
        presenter=None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 graph，事件由 agent_node 内部通过 presenter.emit 直接发送。

        这里只需要：
        1. yield metadata（让 manager.py 保存）
        2. 执行 graph
        3. yield done/error
        """
        if not self._initialized:
            await self.initialize()

        set_user_context(user_id or "default", session_id)

        # 如果没有传入 presenter，创建一个仅用于生成事件的
        if presenter is None:
            presenter = Presenter(
                PresenterConfig(
                    session_id=session_id,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    user_id=user_id,
                    enable_storage=False,
                )
            )

        # 创建并初始化 AgentContext
        disabled_tools = kwargs.get("disabled_tools")
        context = AgentContext(
            session_id=session_id,
            agent_id=self.agent_id,
            user_id=user_id,
            disabled_tools=disabled_tools,
        )
        await context.setup()

        # 发送 metadata
        yield presenter.metadata()

        # 构建 config
        agent_options = kwargs.get("agent_options", {})
        logger.info(f"[SearchAgent] agent_options: {agent_options}")

        config: RunnableConfig = {
            "configurable": {
                "thread_id": session_id,
                "presenter": presenter,
                "context": context,
                "agent_options": agent_options,
                "disabled_tools": disabled_tools,
                "base_url": kwargs.get("base_url", ""),  # 传递 base_url 给工具使用
            },
            "recursion_limit": self.recursion_limit,
        }

        # 初始状态
        attachments = kwargs.get("attachments", [])
        initial_state = {
            "input": message,
            "session_id": session_id,
            "messages": [],  # 历史消息由 agent_node 内部的 deep_agent 管理
            "output": "",
            "attachments": attachments,
        }
        logger.info(
            f"[SearchAgent] initial_state attachments: {len(attachments) if attachments else 0} items"
        )

        try:
            # 直接执行 graph（用 ainvoke 而非 astream，因为不需要处理流式事件）
            # 事件由 agent_node 内部通过 presenter.emit 直接保存
            graph_task = asyncio.create_task(self._graph.ainvoke(initial_state, config))
            self._stream_tasks[presenter.run_id] = graph_task

            await graph_task

        except asyncio.CancelledError:
            if not graph_task.done():
                graph_task.cancel()
                try:
                    await graph_task
                except (asyncio.CancelledError, TaskInterruptedError):
                    pass
            raise

        except TaskInterruptedError:
            if not graph_task.done():
                graph_task.cancel()
                try:
                    await graph_task
                except (asyncio.CancelledError, TaskInterruptedError):
                    pass
            raise

        except Exception as e:
            # 错误事件由 agent_node 内部处理，这里只 yield 给 manager
            yield presenter.error(str(e), type(e).__name__)
            raise

        finally:
            self._stream_tasks.pop(presenter.run_id, None)
            await context.close()

        # 正常完成，发送 done 事件
        yield presenter.done()
