"""
Graph Agent 基类

每个 Agent 就是一个 CompiledGraph，流式请求接入 graph，
节点通过 config 获取 Presenter 并输出 SSE 事件。
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, Callable, Dict, List, Optional, Type

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.infra.writer.present import Presenter, PresenterConfig

logger = logging.getLogger(__name__)

# ============================================================================
# Agent 注册表
# ============================================================================

_AGENT_REGISTRY: Dict[str, Type[Any]] = {}


def register_agent(agent_id: str):
    """
    Agent 注册装饰器

    用法:
        @register_agent("search")
        class SearchAgent:
            ...
    """

    def decorator(cls: Type[Any]) -> Type[Any]:
        _AGENT_REGISTRY[agent_id] = cls
        cls._agent_id = agent_id
        return cls

    return decorator


# ============================================================================
# BaseGraphAgent - Graph Agent 基类
# ============================================================================


class BaseGraphAgent(ABC):
    """
    Graph Agent 基类

    参考 LangGraph 设计，每个 Agent 就是一个 CompiledGraph。

    流程:
    1. 流式请求进入 -> 创建 Presenter
    2. Presenter 注入到 config.configurable["presenter"]
    3. 节点从 config 获取 presenter，调用 present_* 方法
    4. astream_events 捕获 LLM/Tool 事件
    5. 所有事件转换为 SSE 格式 yield 给前端

    子类实现:
        - build_graph(builder): 构建 graph 结构
        - state_class: 状态类 (可选)

    示例节点:
        def my_node(state: dict, config: RunnableConfig) -> dict:
            presenter = config["configurable"]["presenter"]
            presenter.present_text("Hello")
            return {"output": "done"}
    """

    _agent_id: str = "base"
    _agent_name: str = "Base Agent"
    _description: str = ""
    _version: str = "0.1.0"
    # Agent 选项配置（供前端渲染）
    # 格式: {"option_name": {"type": "boolean", "default": False, "label": "...", "description": "..."}}
    _options: Dict[str, Dict[str, Any]] = {}

    def __init__(self, recursion_limit: int = 100, enable_checkpointer: bool = True):
        self.recursion_limit = recursion_limit
        self.enable_checkpointer = enable_checkpointer
        self._graph: Any = None
        self._checkpointer: MemorySaver | None = None
        self._initialized = False
        self._stream_tasks: Dict[str, asyncio.Task] = {}  # run_id -> Task

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def name(self) -> str:
        return self._agent_name

    @property
    def options(self) -> Dict[str, Dict[str, Any]]:
        """获取 Agent 支持的选项配置"""
        return self._options

    @property
    def state_class(self) -> type:
        """状态类，子类可覆盖"""
        return dict

    @abstractmethod
    def build_graph(self, builder: "GraphBuilder") -> None:
        """
        构建 Graph

        子类实现此方法，使用 builder 添加节点和边。

        示例:
            def build_graph(self, builder):
                builder.add_node("agent", self.agent_node)
                builder.set_entry_point("agent")
                builder.add_edge("agent", END)
        """
        pass

    async def initialize(self) -> None:
        """初始化 Agent"""
        if self._initialized:
            return

        # 创建 checkpointer
        if self.enable_checkpointer:
            self._checkpointer = MemorySaver()

        # 构建 graph
        builder = GraphBuilder(self.state_class)
        self.build_graph(builder)
        self._graph = builder.compile(
            checkpointer=self._checkpointer,
            recursion_limit=self.recursion_limit,
        )

        self._initialized = True

    async def close(self, run_id: Optional[str] = None) -> None:
        """
        清理资源

        Args:
            run_id: 可选，指定要取消的运行 ID。如果不指定，则清理所有资源。
        """
        if run_id is not None:
            # 取消特定的 stream_task
            task = self._stream_tasks.pop(run_id, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            logger.info(f"[Agent {self.agent_id}] Cancelled stream task: run_id={run_id}")
        else:
            # 取消所有正在运行的 stream_task
            for _, task in list(self._stream_tasks.items()):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
            self._stream_tasks.clear()

            # 清理 graph 和 checkpointer
            self._graph = None
            self._checkpointer = None
            self._initialized = False
            logger.info(f"[Agent {self.agent_id}] Closed and cleaned up all resources")

    # ==================== 流式执行 ====================

    def stream(
        self,
        message: str,
        session_id: str = str(uuid.uuid4()),
        user_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行 Agent，yield SSE 事件字典

        这是主要的对外接口，返回格式:
            {"event": "message:chunk", "data": {"content": "..."}}
        """
        return self._stream(message, session_id, user_id=user_id, **kwargs)

    async def _stream(
        self,
        message: str,
        session_id: str,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """内部流式执行"""
        if not self._initialized:
            await self.initialize()

        # 优先使用传入的 presenter（来自 TaskManager，带有正确的 run_id）
        # 如果没有传入，则创建新的 Presenter
        presenter = kwargs.get("presenter")
        if presenter is None:
            presenter = Presenter(
                PresenterConfig(
                    session_id=session_id,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    user_id=user_id,
                    enable_storage=kwargs.get("enable_storage", True),
                )
            )
            logger.info(f"[Agent] Created new presenter: run_id={presenter.run_id}")
        else:
            logger.info(f"[Agent] Using passed presenter: run_id={presenter.run_id}")

        # 设置请求上下文（供工具使用）
        from src.infra.logging.context import TraceContext

        logger.info(
            f"[Agent] Setting TraceContext: session_id={session_id}, run_id={presenter.run_id}"
        )
        TraceContext.set_request_context(
            session_id=session_id,
            run_id=presenter.run_id,
            user_id=user_id,
        )

        # 确保 trace 在数据库中创建（绑定 user_id）
        await presenter._ensure_trace()

        # 发送元数据（由 manager.py 保存）
        meta_evt = presenter.metadata()
        yield meta_evt

        # 构建 config，注入 presenter
        config: RunnableConfig = {
            "configurable": {
                "thread_id": session_id,
                "presenter": presenter,
                **kwargs,
            },
            "recursion_limit": self.recursion_limit,
        }

        # 初始状态
        initial_state = {
            "input": message,
            "session_id": session_id,
            "messages": [],
            "context": kwargs,
        }

        try:
            # 导入中断检查函数
            from src.infra.task.manager import (
                BackgroundTaskManager,
                TaskInterruptedError,
            )

            # 使用队列来传递事件
            event_queue: asyncio.Queue = asyncio.Queue()
            stream_error = None
            stream_done = False

            async def run_stream():
                """运行 graph 流并将事件放入队列"""
                nonlocal stream_error, stream_done
                try:
                    async for event in self._graph.astream_events(
                        initial_state,
                        config,
                        version="v2",
                    ):
                        # 在生产事件时检查中断
                        await BackgroundTaskManager.check_interrupt(presenter.run_id)
                        await event_queue.put(("event", event))
                except TaskInterruptedError:
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    stream_error = e
                    await event_queue.put(("error", e))
                finally:
                    stream_done = True
                    # 放入终止信号，唤醒主循环（避免 await get() 永久阻塞）
                    await event_queue.put(("done", None))

            # 启动流任务
            stream_task = asyncio.create_task(run_stream())
            # 注册任务以便 close 可以取消
            self._stream_tasks[presenter.run_id] = stream_task

            try:
                while True:
                    # 直接 await 队列，cancel 时 CancelledError 会打断
                    item = await event_queue.get()

                    item_type, item_data = item

                    if item_type == "done":
                        break

                    if item_type == "error":
                        raise item_data

                    evt_type = item_data.get("event")

                    # LLM token 流
                    if evt_type == "on_chat_model_stream":
                        chunk = item_data.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            yield presenter.present_text(chunk.content)

                    # 工具调用开始
                    elif evt_type == "on_tool_start":
                        name = item_data.get("name", "")
                        inp = item_data.get("data", {}).get("input", {})
                        if name not in ["read_file", "read_todos", "write_todos"]:
                            yield presenter.present_tool_start(name, inp)

                    # 工具调用结束
                    elif evt_type == "on_tool_end":
                        name = item_data.get("name", "")
                        out = item_data.get("data", {}).get("output", "")
                        if name not in ["read_file", "read_todos", "write_todos"]:
                            yield presenter.present_tool_result(name, str(out))

                    # 链结束 - 可能包含节点返回的事件
                    elif evt_type == "on_chain_end":
                        output = item_data.get("data", {}).get("output", {})
                        # 如果节点返回了 __events__，发送这些事件
                        if isinstance(output, dict) and "__events__" in output:
                            for evt in output["__events__"]:
                                yield evt

            finally:
                # 注销并取消流任务
                self._stream_tasks.pop(presenter.run_id, None)
                if not stream_task.done():
                    stream_task.cancel()
                    try:
                        await stream_task
                    except (asyncio.CancelledError, TaskInterruptedError):
                        pass

        except asyncio.CancelledError:
            # 任务被取消，yield 队列中剩余的事件（由 manager.py 保存）
            while not event_queue.empty():
                try:
                    item_type, item_data = event_queue.get_nowait()
                    if item_type == "event" and item_data:
                        evt_type = item_data.get("event")
                        # 只 yield 关键事件类型
                        if evt_type == "on_chat_model_stream":
                            chunk = item_data.get("data", {}).get("chunk")
                            if chunk and hasattr(chunk, "content") and chunk.content:
                                yield presenter.present_text(chunk.content)
                        elif evt_type == "on_tool_start":
                            name = item_data.get("name", "")
                            inp = item_data.get("data", {}).get("input", {})
                            if name not in ["read_file", "read_todos", "write_todos"]:
                                yield presenter.present_tool_start(name, inp)
                        elif evt_type == "on_tool_end":
                            name = item_data.get("name", "")
                            out = item_data.get("data", {}).get("output", "")
                            if name not in ["read_file", "read_todos", "write_todos"]:
                                yield presenter.present_tool_result(name, str(out))
                except asyncio.QueueEmpty:
                    break
            raise

        # 其他异常（TaskInterruptedError, Exception）直接抛给 manager.py 处理

        # 发送完成
        yield presenter.done()

    async def invoke(self, message: str, session_id: str = str(uuid.uuid4()), **kwargs) -> str:
        """非流式执行，返回最终结果"""
        if not self._initialized:
            await self.initialize()

        config: RunnableConfig = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": self.recursion_limit,
        }

        result = await self._graph.ainvoke(
            {"input": message, "session_id": session_id, "messages": []},
            config,
        )
        return result.get("output", "")


# ============================================================================
# GraphBuilder - 增强的 Graph 构建器
# ============================================================================


class GraphBuilder:
    """
    Graph 构建器

    封装 LangGraph StateGraph，提供流畅的 API。

    用法:
        builder = GraphBuilder(MyState)
        builder.add_node("agent", agent_node)
        builder.set_entry_point("agent")
        builder.add_edge("agent", END)
        graph = builder.compile()
    """

    def __init__(self, state_class: type = dict):
        self._state_class = state_class
        self._nodes: Dict[str, Callable] = {}
        self._edges: List[tuple] = []
        self._entry_point: Optional[str] = None
        self._conditional_edges: List[tuple] = []

    def add_node(self, name: str, func: Callable, description: str = "") -> "GraphBuilder":
        """添加节点"""
        self._nodes[name] = func
        return self

    def add_edge(self, from_node: str, to_node: str) -> "GraphBuilder":
        """添加边"""
        self._edges.append((from_node, to_node))
        return self

    def set_entry_point(self, node_name: str) -> "GraphBuilder":
        """设置入口点"""
        self._entry_point = node_name
        return self

    def add_conditional_edges(
        self,
        from_node: str,
        condition: Callable,
        path_map: Dict[str, str],
    ) -> "GraphBuilder":
        """添加条件边"""
        self._conditional_edges.append((from_node, condition, path_map))
        return self

    def compile(self, checkpointer=None, recursion_limit: int = 100) -> Any:
        """编译 graph"""
        graph: StateGraph = StateGraph(self._state_class)

        # 添加节点
        for name, func in self._nodes.items():
            graph.add_node(name, func)

        # 设置入口点
        if self._entry_point:
            graph.add_edge(START, self._entry_point)

        # 添加边
        for from_node, to_node in self._edges:
            target = END if to_node == "END" else to_node
            graph.add_edge(from_node, target)

        # 添加条件边
        for from_node, condition, path_map in self._conditional_edges:
            normalized = {k: END if v == "END" else v for k, v in path_map.items()}
            graph.add_conditional_edges(from_node, condition, normalized)

        return graph.compile(checkpointer=checkpointer)


# ============================================================================
# 辅助函数 - 节点内获取 Presenter
# ============================================================================


def get_presenter(config: RunnableConfig) -> Presenter:
    """从 config 中获取 Presenter"""
    presenter = config.get("configurable", {}).get("presenter")
    if presenter is None:
        raise RuntimeError(
            "Presenter not found in config. Make sure to use BaseGraphAgent.stream()"
        )
    return presenter


# ============================================================================
# Agent 工厂
# ============================================================================


class AgentFactory:
    """Agent 工厂，管理实例创建和缓存"""

    _instances: Dict[str, BaseGraphAgent] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get(cls, agent_id: str) -> BaseGraphAgent:
        """获取 Agent 实例（单例）"""
        if agent_id in cls._instances:
            return cls._instances[agent_id]

        async with cls._lock:
            if agent_id in cls._instances:
                return cls._instances[agent_id]

            if agent_id not in _AGENT_REGISTRY:
                raise ValueError(f"Agent '{agent_id}' 未注册。可用: {list(_AGENT_REGISTRY.keys())}")

            agent_cls = _AGENT_REGISTRY[agent_id]
            agent = agent_cls()
            await agent.initialize()
            cls._instances[agent_id] = agent
            return agent

    @classmethod
    def list_agents(cls) -> List[Dict[str, Any]]:
        """列出所有可用 Agent（包含选项配置）"""
        return [
            {
                "id": aid,
                "name": getattr(cls, "_name_key", None) or getattr(cls, "_agent_name", aid.title()),
                "description": getattr(cls, "_description_key", None)
                or getattr(cls, "_description", ""),
                "version": getattr(cls, "_version", "0.1.0"),
                "options": getattr(cls, "_options", {}),
            }
            for aid, cls in _AGENT_REGISTRY.items()
        ]

    @classmethod
    async def close_all(cls) -> None:
        """关闭所有 Agent 实例"""
        for agent_id, agent in cls._instances.items():
            try:
                await agent.close()
            except Exception as e:
                logger.warning(f"Error closing Agent '{agent_id}': {e}")
        cls._instances.clear()


# ============================================================================
# 便捷函数
# ============================================================================


def get_agent_class(agent_id: str) -> Type[BaseGraphAgent]:
    """获取已注册的 Agent 类"""
    if agent_id not in _AGENT_REGISTRY:
        raise ValueError(f"Agent '{agent_id}' 未注册")
    return _AGENT_REGISTRY[agent_id]


def list_registered_agents() -> List[str]:
    """列出所有已注册的 Agent ID"""
    return list(_AGENT_REGISTRY.keys())
