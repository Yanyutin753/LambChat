"""
Fast Agent - 基于 LangGraph 的快速 Agent

特点：
- 无沙箱（使用内存 backend）
- 支持 Skills
- 快速响应

架构:
    START -> fast_agent_node -> END
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict

from langchain_core.runnables import RunnableConfig

from src.agents.core.base import BaseGraphAgent, GraphBuilder, register_agent
from src.agents.fast_agent.context import FastAgentContext
from src.agents.fast_agent.nodes import fast_agent_node
from src.agents.fast_agent.state import FastAgentState
from src.infra.backend.context import set_user_context
from src.infra.task.manager import TaskInterruptedError
from src.infra.writer.present import Presenter, PresenterConfig
from src.kernel.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# FastAgent 类
# ============================================================================


@register_agent("fast")
class FastAgent(BaseGraphAgent):
    """
    Fast Agent - 快速响应，无沙箱

    适用于：
    - 快速对话
    - 无需文件系统操作的场景
    - 低延迟要求的场景
    """

    _agent_id = "fast"
    _agent_name = "Fast Agent"
    _name_key = "agents.fast.name"
    _description = "快速响应的 AI 助手，无沙箱，支持 Skills"
    _description_key = "agents.fast.description"
    _version = "1.0.0"
    _sort_order = 2  # 排序权重，数值越小越靠前

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
        return FastAgentState

    def build_graph(self, builder: GraphBuilder) -> None:
        """
        构建 Graph

        当前结构: START -> fast_agent_node -> END
        """
        builder.add_node("agent", fast_agent_node)
        builder.set_entry_point("agent")
        builder.add_edge("agent", "END")

    async def initialize(self) -> None:
        """初始化 Agent"""
        if self._initialized:
            return

        builder = GraphBuilder(self.state_class)
        self.build_graph(builder)
        self._graph = builder.compile(
            checkpointer=None,
            recursion_limit=settings.SESSION_MAX_RUNS_PER_SESSION,
        )

        self._initialized = True
        logger.info(f"{self.name} initialized (no sandbox, no checkpointer)")

    async def _stream(
        self,
        message: str,
        session_id: str,
        user_id: str | None = None,
        presenter=None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 graph
        """
        if not self._initialized:
            await self.initialize()

        set_user_context(user_id or "default", session_id)

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

        # 创建并初始化 FastAgentContext
        disabled_tools = kwargs.get("disabled_tools")
        context = FastAgentContext(
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
        logger.info(f"[FastAgent] agent_options: {agent_options}")

        config: RunnableConfig = {
            "configurable": {
                "thread_id": session_id,
                "presenter": presenter,
                "context": context,
                "agent_options": agent_options,
                "base_url": kwargs.get("base_url", ""),
            },
            "recursion_limit": self.recursion_limit,
        }

        # 初始状态
        attachments = kwargs.get("attachments", [])
        initial_state = {
            "input": message,
            "session_id": session_id,
            "messages": [],
            "output": "",
            "attachments": attachments,
        }
        logger.info(
            f"[FastAgent] initial_state attachments: {len(attachments) if attachments else 0} items"
        )

        try:
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
            yield presenter.error(str(e), type(e).__name__)
            raise

        finally:
            self._stream_tasks.pop(presenter.run_id, None)
            await context.close()

        yield presenter.done()
