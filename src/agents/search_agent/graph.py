"""
Search Agent - 基于 LangGraph 的 Graph Agent

外层 Graph 管理多个节点，agent_node 执行 LLM + 工具调用。
后续可扩展：检索节点、记忆节点、规划节点等。

架构:
    START -> agent_node -> END

    后续可扩展:
    - START -> retrieve_node -> agent_node -> END
    - START -> plan_node -> agent_node -> summarize_node -> END
"""

import asyncio
import json
import logging

from langchain_core.runnables import RunnableConfig

from src.agents.core.base import BaseGraphAgent, GraphBuilder, register_agent
from src.agents.search_agent.context import AgentContext
from src.agents.search_agent.nodes import agent_node
from src.agents.search_agent.state import SearchAgentState

# 设置用户上下文，供 backend 使用
from src.infra.backend.context import set_user_context
from src.infra.storage.checkpoint import get_checkpointer

# 导入中断异常类型（cancel 走 CancelledError，这里只用于类型）
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
    # 支持的字段：
    # - type: "boolean" | "string" | "number"
    # - default: 默认值
    # - label: 默认标签（英文）
    # - label_key: i18n 翻译键（可选，前端优先使用）
    # - description: 默认描述（英文）
    # - description_key: i18n 翻译键（可选，前端优先使用）
    # - icon: lucide-react 图标名称（如 "Brain", "Zap", "Settings"）
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

        # 创建 checkpointer - 使用 infra 中的工厂函数
        if self.enable_checkpointer and self._checkpointer is None:
            self._checkpointer = get_checkpointer()

        # 构建 graph
        builder = GraphBuilder(self.state_class)
        self.build_graph(builder)
        self._graph = builder.compile(
            checkpointer=self._checkpointer,
            recursion_limit=settings.SESSION_MAX_RUNS_PER_SESSION,
        )

        self._initialized = True
        logger.info(f"{self.name} initialized")

    async def _stream(
        self,
        message: str,
        session_id: str,
        user_id: str | None = None,
        presenter=None,
        **kwargs,
    ):
        """
        内部流式实现

        使用事件队列实现实时流式输出：
        1. 发送 metadata
        2. 启动 graph 执行任务（后台）
        3. 从队列中读取事件并 yield
        4. 发送 done
        """
        if not self._initialized:
            await self.initialize()

        set_user_context(user_id or "default", session_id)

        # 创建事件队列
        event_queue: asyncio.Queue = asyncio.Queue()

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

        # 创建并初始化 AgentContext（从 kwargs 获取 disabled_tools）
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

        # 构建 config，注入 presenter、context 和事件队列
        agent_options = kwargs.get("agent_options", {})
        logger.info(f"[SearchAgent] kwargs keys: {list(kwargs.keys())}")
        logger.info(f"[SearchAgent] agent_options: {agent_options}")

        config: RunnableConfig = {
            "configurable": {
                "thread_id": session_id,
                "presenter": presenter,
                "context": context,
                "event_queue": event_queue,  # 注入事件队列
                "agent_options": agent_options,  # 传递 agent_options（包含所有选项）
                "disabled_tools": kwargs.get("disabled_tools"),  # 传递 disabled_tools
            },
            "recursion_limit": self.recursion_limit,
        }

        # 获取历史状态
        current_state = await self._graph.aget_state(config)
        history_messages = current_state.values.get("messages", [])

        # 初始状态 - 使用历史消息
        initial_state = {
            "input": message,
            "session_id": session_id,
            "messages": history_messages,  # 复用历史消息
            "output": "",
        }

        async def run_graph():
            """后台执行 graph"""
            try:
                # 使用 astream(stream_mode="updates") 替代 astream_events
                # 原因：外层 graph 只有 agent_node 一个节点，astream_events 会为内层
                # 每个 token 都生成外层事件副本（全部 pass 丢弃），导致 2x CPU 开销。
                # astream("updates") 只在节点完成时 yield 一次，真正的流式通过
                # agent_node 内部的 event_queue 实现，不受影响。
                async for _ in self._graph.astream(
                    initial_state,
                    config,
                    stream_mode="updates",
                ):
                    pass  # 事件由 agent_node 通过队列发送
            except Exception as e:
                # 发送错误事件
                error_event = presenter.error(str(e), type(e).__name__)
                await event_queue.put(("error", error_event))
            finally:
                # 标记结束
                await event_queue.put(("done", None))

        try:
            # 启动 graph 执行任务
            graph_task = asyncio.create_task(run_graph())
            # 注册任务以便 close 可以取消
            self._stream_tasks[presenter.run_id] = graph_task

            # 从队列中读取事件并 yield（直接 await，cancel 时 CancelledError 会打断）
            while True:
                event_type, event_data = await event_queue.get()

                if event_type == "done":
                    break

                if event_type == "error":
                    yield event_data
                    data = event_data.get("data", "{}")
                    if isinstance(data, str):
                        data = json.loads(data)
                    raise Exception(data.get("error", "Unknown error"))

                if event_data:
                    yield event_data

            # 等待 graph 任务完成
            await graph_task

        except asyncio.CancelledError:
            # 任务被取消，yield 队列中剩余的事件（由 manager.py 保存）
            while not event_queue.empty():
                try:
                    _, remaining_event = event_queue.get_nowait()
                    if remaining_event:
                        yield remaining_event
                except asyncio.QueueEmpty:
                    break
            raise

        finally:
            # 注销并取消 graph_task
            self._stream_tasks.pop(presenter.run_id, None)
            if not graph_task.done():
                graph_task.cancel()
                try:
                    await graph_task
                except (asyncio.CancelledError, TaskInterruptedError):
                    pass
            await context.close()

        # 正常完成，发送 done 事件
        yield presenter.done()
