"""
Graph Agent 基类

每个 Agent 就是一个 CompiledGraph，流式请求接入 graph，
节点通过 config 获取 Presenter 并输出 SSE 事件。
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Type

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from src.infra.agent import AgentEventProcessor
from src.infra.logging import get_logger
from src.infra.writer.present import Presenter, PresenterConfig
from src.kernel.config import settings

logger = get_logger(__name__)

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
    # 排序权重（数值越小越靠前）
    _sort_order: int = 100
    # Agent 选项配置（供前端渲染）
    # 格式: {"option_name": {"type": "boolean", "default": False, "label": "...", "description": "..."}}
    _options: Dict[str, Dict[str, Any]] = {}

    def __init__(self, recursion_limit: int | None = None, enable_checkpointer: bool = True):
        self.recursion_limit = recursion_limit or settings.SESSION_MAX_RUNS_PER_SESSION
        self.enable_checkpointer = enable_checkpointer
        self._graph: Any = None
        self._checkpointer: Any = None
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

        # 创建 checkpointer（优先 MongoDB，fallback 到 MemorySaver）
        if self.enable_checkpointer:
            from src.infra.storage.checkpoint import get_mongo_checkpointer

            self._checkpointer = get_mongo_checkpointer()
            if self._checkpointer is None:
                from langgraph.checkpoint.memory import MemorySaver

                self._checkpointer = MemorySaver()

                # 启动后台清理任务，防止内存泄漏
                self._cleanup_task = asyncio.create_task(self._cleanup_memory_saver())
                self._cleanup_task.add_done_callback(lambda t: None)  # prevent GC

                logger.warning(
                    f"[Agent {self._agent_id}] Using MemorySaver with TTL cleanup (1 hour)"
                )
            else:
                logger.info(f"[Agent {self._agent_id}] Using MongoDB checkpointer")

        # 构建 graph
        builder = GraphBuilder(self.state_class)
        self.build_graph(builder)
        self._graph = builder.compile(
            checkpointer=self._checkpointer,
            recursion_limit=self.recursion_limit,
        )

        self._initialized = True

    async def _cleanup_memory_saver(self) -> None:
        """定期清理 MemorySaver 中的旧数据，防止内存泄漏"""
        from langgraph.checkpoint.memory import MemorySaver

        while True:
            try:
                await asyncio.sleep(3600)  # 每小时清理一次

                if not isinstance(self._checkpointer, MemorySaver):
                    break

                storage = self._checkpointer.storage
                if not storage:
                    continue

                # 清理 1 小时前的 checkpoint
                cutoff_time = datetime.now() - timedelta(hours=1)
                to_delete = []

                for thread_id in list(storage.keys()):
                    try:
                        checkpoints = storage.get(thread_id, {})
                        if not checkpoints:
                            to_delete.append(thread_id)
                            continue

                        # 检查最新 checkpoint 的时间
                        # LangGraph 的 ts 字段是 ISO 格式字符串（如 "2024-01-01T00:00:00"），
                        # 需要用 datetime.fromisoformat() 而非 datetime.fromtimestamp()
                        latest_checkpoint = max(
                            checkpoints.values(), key=lambda x: getattr(x, "ts", 0)
                        )
                        ts_raw = getattr(latest_checkpoint, "ts", "0")
                        checkpoint_time = None
                        if isinstance(ts_raw, str):
                            try:
                                checkpoint_time = datetime.fromisoformat(ts_raw)
                            except (ValueError, TypeError):
                                pass
                        else:
                            try:
                                checkpoint_time = datetime.fromtimestamp(float(ts_raw))
                            except (TypeError, ValueError):
                                pass

                        if checkpoint_time is not None and checkpoint_time < cutoff_time:
                            to_delete.append(thread_id)
                    except Exception:
                        pass

                # 删除旧的 checkpoint
                for thread_id in to_delete:
                    try:
                        del storage[thread_id]
                    except Exception:
                        pass

                if to_delete:
                    logger.info(
                        f"[Agent {self._agent_id}] Cleaned {len(to_delete)} old checkpoints "
                        f"(total remaining: {len(storage)})"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Agent {self._agent_id}] Failed to cleanup MemorySaver: {e}")

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
            "attachments": kwargs.get("attachments", []),
        }

        try:
            # 导入中断检查函数
            from src.infra.task.manager import (
                BackgroundTaskManager,
                TaskInterruptedError,
            )

            # 使用队列来传递事件（限制大小防止消费者慢时内存无限增长）
            event_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
            stream_error = None
            stream_done = False

            async def run_stream():
                """运行 graph 流并将事件放入队列"""
                nonlocal stream_error, stream_done
                try:
                    # 使用 astream_events API
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

            # 中断检查间隔（秒）- 1 秒是性能和响应速度的平衡点
            interrupt_check_interval = 1.0

            # 创建事件处理器
            event_processor = AgentEventProcessor(presenter, base_url=kwargs.get("base_url", ""))

            try:
                while True:
                    # 使用 wait_for 定期检查中断信号
                    # 即使 LLM 请求阻塞，也能响应取消
                    try:
                        item = await asyncio.wait_for(
                            event_queue.get(), timeout=interrupt_check_interval
                        )
                    except asyncio.TimeoutError:
                        # 超时时使用快速内存检查（无 IO 开销）
                        if BackgroundTaskManager.check_interrupt_fast(presenter.run_id):
                            raise TaskInterruptedError(
                                f"Task interrupted: run_id={presenter.run_id}"
                            )
                        continue

                    item_type, item_data = item

                    if item_type == "done":
                        break

                    if item_type == "error":
                        raise item_data

                    # 使用 AgentEventProcessor 处理事件
                    await event_processor.process_event(item_data)

            finally:
                # 注销并取消流任务
                self._stream_tasks.pop(presenter.run_id, None)
                if not stream_task.done():
                    stream_task.cancel()
                    try:
                        await stream_task
                    except (asyncio.CancelledError, TaskInterruptedError):
                        pass
                # Flush pending chunks and clear event_processor memory
                await event_processor.finalize()

        except asyncio.CancelledError:
            # 任务被取消，yield 队列中剩余的事件（由 manager.py 保存）
            try:
                while not event_queue.empty():
                    try:
                        item_type, item_data = event_queue.get_nowait()
                        if item_type == "event" and item_data:
                            # 使用 AgentEventProcessor 处理剩余事件
                            try:
                                await event_processor.process_event(item_data)
                            except Exception:
                                pass
                    except asyncio.QueueEmpty:
                        break
            finally:
                # 确保清理 event_processor 内存
                await event_processor.finalize()
            raise

        # 其他异常（TaskInterruptedError, Exception）直接抛给 manager.py 处理

        # 发送 token 使用统计
        if event_processor.total_input_tokens > 0 or event_processor.total_output_tokens > 0:
            agent_options = kwargs.get("agent_options") or {}
            await presenter.emit(
                presenter.present_token_usage(
                    input_tokens=event_processor.total_input_tokens,
                    output_tokens=event_processor.total_output_tokens,
                    total_tokens=event_processor.total_tokens
                    or event_processor.total_input_tokens + event_processor.total_output_tokens,
                    cache_creation_tokens=event_processor.total_cache_creation_tokens,
                    cache_read_tokens=event_processor.total_cache_read_tokens,
                    model_id=agent_options.get("model_id"),
                    model=agent_options.get("model"),
                )
            )

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

    def compile(self, checkpointer=None, recursion_limit: int | None = None) -> Any:
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
    def list_agents(cls, default_agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有可用 Agent（包含选项配置），按 sort_order 和名称排序，默认 agent 排在最前面"""
        # 如果注册表为空，尝试发现 agents
        if not _AGENT_REGISTRY:
            from src.agents import discover_agents

            discover_agents()

        agents = [
            {
                "id": aid,
                "name": getattr(agent_cls, "_name_key", None)
                or getattr(agent_cls, "_agent_name", aid.title()),
                "description": getattr(agent_cls, "_description_key", None)
                or getattr(agent_cls, "_description", ""),
                "version": getattr(agent_cls, "_version", "0.1.0"),
                "sort_order": getattr(agent_cls, "_sort_order", 100),
                "supports_sandbox": getattr(agent_cls, "_supports_sandbox", False),
                "options": getattr(agent_cls, "_options", {}),
            }
            for aid, agent_cls in _AGENT_REGISTRY.items()
        ]

        # 排序：默认 agent 放最前面，其余按 sort_order 和名称排序
        def sort_key(agent):
            is_default = agent["id"] == default_agent_id
            return (0 if is_default else 1, agent["sort_order"], agent["name"])

        agents.sort(key=sort_key)
        return agents

    @classmethod
    async def get_filtered_agents(
        cls,
        user_roles: List[str],
        role_agent_map: dict,
        default_agent_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取用户可用的 Agents（根据全局配置和角色配置过滤）

        过滤规则:
        1. 全局配置存在 → 以全局启用列表为基准
        2. 全局配置不存在 → 默认所有 agent 启用
        3. 角色配置存在（含空列表） → 取角色允许与全局启用的交集
        4. 角色配置不存在 → 使用全局配置
        """
        from src.infra.agent.config_storage import get_agent_config_storage

        logger.info(
            f"[get_filtered_agents] user_roles={user_roles}, role_agent_map={role_agent_map}"
        )

        # 获取所有注册 agents
        all_agents = cls.list_agents(default_agent_id)
        all_agent_ids = {a["id"] for a in all_agents}

        # 获取全局配置
        storage = get_agent_config_storage()
        global_configs = await storage.get_global_config()

        if global_configs:
            # 全局配置已保存过 → 以它为准（即使全部禁用也尊重）
            enabled_agent_ids = {a.id for a in global_configs if a.enabled}
            logger.info(f"[get_filtered_agents] global config exists, enabled={enabled_agent_ids}")
        else:
            # 从未配置过全局设置 → 默认全部启用
            enabled_agent_ids = all_agent_ids
            logger.info("[get_filtered_agents] no global config yet, using all agents")

        # 收集角色允许的 agents
        role_allowed: Optional[set] = None
        for role_id in user_roles:
            role_config = role_agent_map.get(role_id)
            if role_config is not None:
                # 角色有配置（包括空列表）
                if role_allowed is None:
                    role_allowed = set()
                role_allowed.update(role_config)

        if role_allowed is None:
            # 所有角色都未配置 → 使用全局配置
            final_ids = enabled_agent_ids
            logger.info("[get_filtered_agents] no role config, using global config")
        else:
            # 至少一个角色有配置 → 取交集
            final_ids = role_allowed & enabled_agent_ids
            logger.info(
                f"[get_filtered_agents] role_config intersect global: {role_allowed} & {enabled_agent_ids} = {final_ids}"
            )

        filtered = [a for a in all_agents if a["id"] in final_ids]
        logger.info(f"[get_filtered_agents] filtered count={len(filtered)}")
        return filtered

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
