"""
Search Agent 节点

LangGraph 节点函数，使用 deep agent 执行任务。
后续可扩展：retrieve_node, summarize_node 等。
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from src.agents.core.base import get_presenter
from src.agents.search_agent.prompt import DEFAULT_SYSTEM_PROMPT
from src.infra.llm.client import LLMClient
from src.infra.sandbox import get_sandbox_from_settings

# 获取 sandbox_id 用于关闭
from src.infra.sandbox.base import SandboxFactory
from src.infra.skill.middleware import SkillsMiddleware

# Human-in-the-loop 工具
from src.infra.tool.human_tool import get_human_tool

# Inject Skill 工具 - 按需加载技能到沙箱
# 设置全局 middleware 供 inject_skill 工具使用
from src.infra.tool.inject_skill import get_inject_skill_tool, set_skills_middleware
from src.infra.tool.mcp_client import MCPClientManager

# Reveal File 工具 - 向用户展示文件
from src.infra.tool.reveal_file_tool import get_reveal_file_tool
from src.infra.writer.present import _get_timestamp
from src.kernel.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# 状态定义
# ============================================================================


class SearchAgentState(TypedDict):
    """
    Search Agent 状态

    Attributes:
        input: 用户输入
        session_id: 会话 ID
        messages: 消息历史
        output: 输出结果
        context: Agent 上下文（运行时注入）
        retrieved_docs: 检索到的文档（retrieve_node 添加）
    """

    input: str
    session_id: str
    messages: List[Any]
    output: str
    context: Optional[Dict[str, Any]]
    retrieved_docs: Optional[List[str]]


# ============================================================================
# 上下文
# ============================================================================


class AgentContext:
    """Agent 上下文，管理工具和技能"""

    def __init__(
        self,
        session_id: str = str(uuid.uuid4()),
        agent_id: str = "search",
        user_id: Optional[str] = None,
        disabled_tools: Optional[List[str]] = None,
    ):
        self.session_id = session_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.disabled_tools = disabled_tools  # 用户禁用的工具列表
        self.skills_middleware = None
        self.mcp_manager = None
        self.tools: List[Any] = []
        self.system_prompt = DEFAULT_SYSTEM_PROMPT

    def filter_tools(self) -> List[Any]:
        """
        根据 disabled_tools 过滤工具

        支持两种模式：
        1. 精确匹配: "read_file" 匹配名为 "read_file" 的工具
        2. MCP 模式匹配: "mcp:server_name" 匹配来自该服务器的所有工具

        注意：ask_human 和 reveal_file 是内置工具，始终可用，不受过滤影响。
        """
        # 如果 disabled_tools 为 None 或空列表，返回所有工具
        if not self.disabled_tools:
            return self.tools

        # 内置工具，始终可用
        builtin_tools = frozenset(["ask_human", "reveal_file", "inject_skill"])

        disabled_set = set(self.disabled_tools)
        mcp_servers = set()
        exact_names = set()

        for tool_name in disabled_set:
            if tool_name.startswith("mcp:"):
                mcp_servers.add(tool_name[4:])
            else:
                exact_names.add(tool_name)

        # 构建 MCP 前缀元组，用于 startswith 批量匹配（避免内层循环）
        mcp_prefixes = tuple(f"{s}:" for s in mcp_servers) if mcp_servers else ()

        filtered = []
        for tool in self.tools:
            tool_name = getattr(tool, "name", str(tool))

            if tool_name in builtin_tools:
                filtered.append(tool)
                continue

            if tool_name in exact_names:
                continue

            # MCP 服务器模式匹配（用 tuple startswith 一次性检查所有前缀）
            if mcp_prefixes and tool_name.startswith(mcp_prefixes):
                continue
            if mcp_servers and hasattr(tool, "server") and tool.server in mcp_servers:
                continue

            filtered.append(tool)

        logger.debug(
            "[AgentContext] Tool filtering: %d/%d tools enabled (disabled: %s)",
            len(filtered),
            len(self.tools),
            self.disabled_tools,
        )
        return filtered

    async def setup(self) -> None:
        """初始化：技能 + 工具"""
        logger.info(
            f"[AgentContext] Starting setup, ENABLE_SKILLS={settings.ENABLE_SKILLS}, ENABLE_MCP={settings.ENABLE_MCP}"
        )

        human_tool = get_human_tool(session_id=self.session_id)
        self.tools.append(human_tool)
        logger.info("[AgentContext] Added human tool")

        reveal_file_tool = get_reveal_file_tool()
        self.tools.append(reveal_file_tool)
        logger.info("[AgentContext] Added reveal_file tool")

        inject_skill_tool = get_inject_skill_tool()
        self.tools.append(inject_skill_tool)
        logger.info("[AgentContext] Added inject_skill tool")

        # MCP 工具
        if settings.ENABLE_MCP:
            try:
                logger.info(f"[AgentContext] Initializing MCP client for user {self.user_id}")
                self.mcp_manager = MCPClientManager(
                    config_path=None, user_id=self.user_id, use_database=True
                )
                await self.mcp_manager.initialize()
                mcp_tools = await self.mcp_manager.get_tools()
                logger.info(
                    f"[AgentContext] Loaded {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}"
                )
                self.tools.extend(mcp_tools)
            except Exception as e:
                logger.error(f"[AgentContext] Failed to load MCP tools: {e}", exc_info=True)
        else:
            logger.warning("[AgentContext] MCP is disabled (ENABLE_MCP=False)")

        logger.info(f"[AgentContext] Setup complete, total {len(self.tools)} tools available")

    async def close(self) -> None:
        """清理"""
        if self.mcp_manager:
            try:
                await self.mcp_manager.close()
            except Exception:
                pass


# ============================================================================
# 节点函数
# ============================================================================


async def agent_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Agent 主节点

    创建 deep agent (内层 graph) 并执行，通过事件队列流式发送事件。
    支持会话上下文：传递历史消息给 inner_graph，并在执行后保存消息。
    """
    presenter = get_presenter(config)
    configurable = config.get("configurable", {})
    context: AgentContext = configurable.get("context", AgentContext())
    event_queue: Optional[asyncio.Queue] = configurable.get("event_queue")

    # 获取 agent_options（支持所有选项）
    agent_options = configurable.get("agent_options") or {}
    enable_thinking = agent_options.get("enable_thinking", False)
    logger.info(f"agent_options: {agent_options}")

    # 获取历史消息
    existing_messages = state.get("messages", [])
    new_message = HumanMessage(content=state.get("input", ""))

    llm = LLMClient.get_deep_agent_model(
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        thinking={"type": "enabled"} if enable_thinking else None,
    )

    # 创建 sandbox backend (langchain-daytona/runloop/modal)
    # 每次请求创建新的 sandbox，函数结束时关闭
    backend = get_sandbox_from_settings()
    sandbox_id = None

    sandbox_id = SandboxFactory.get_sandbox_id(backend)

    # 注意：backend 通过 create_deep_agent 的 config 传递给工具
    # 使用 try-finally 确保 sandbox 在任何情况下都能正确关闭
    # 避免中间过程报错导致没有正常关闭
    try:
        # 技能：只注入系统提示元数据，不再预加载文件到沙箱
        # 技能文件通过 inject_skill 工具按需加载
        if settings.ENABLE_SKILLS:
            # 创建 SkillsMiddleware 并设置为全局实例
            skills_middleware = SkillsMiddleware(
                user_id=context.user_id,
                sandbox=backend,
            )

            if skills_middleware:
                set_skills_middleware(skills_middleware)

                # 只注入技能元数据到系统提示（不预加载文件到沙箱）
                context.system_prompt = await skills_middleware.inject_skills_async(
                    DEFAULT_SYSTEM_PROMPT
                )

        # 过滤工具（根据用户选择的 enabled_tools）
        filtered_tools = context.filter_tools()

        # 创建内层 graph (deep agent)
        inner_graph = create_deep_agent(
            model=llm,
            system_prompt=context.system_prompt,
            backend=backend,
            tools=filtered_tools if filtered_tools else None,
            checkpointer=MemorySaver(),
        ).with_config({"recursion_limit": 100})

        inner_config: RunnableConfig = {
            "configurable": {
                "thread_id": state.get("session_id", str(uuid.uuid4())),
                "backend": backend,  # 传递 backend 给工具使用
            },
            "recursion_limit": 100,
        }

        async def emit_event(event_data: Dict[str, Any]) -> None:
            """发送事件到队列（事件会在 graph.py 中统一保存）"""
            if event_queue:
                await event_queue.put(("event", event_data))

        # 发送用户消息事件
        await emit_event(
            presenter._build_event(
                "user:message",
                {"content": state.get("input", ""), "timestamp": _get_timestamp()},
            )
        )

        # 构建传入的消息列表 - 包含历史
        all_messages = existing_messages + [new_message]

        # 跟踪子代理（task工具）的执行状态
        # 使用 run_id 映射来追踪子代理（包括其所有子事件）
        # key: task_run_id (task 工具的 run_id), value: (instance_id, subagent_type, depth)
        task_run_id_to_agent: dict[str, tuple[str, str, int]] = {}

        # 收集输出文本
        output_text = ""

        # 跟踪每个 (depth, agent_id) 组合的 thinking 块 ID
        # 用于合并同一块的多个 thinking 事件
        thinking_ids: Dict[str, Optional[str]] = {}  # key: f"{depth}:{agent_id}"

        async for event in inner_graph.astream_events(
            {"messages": all_messages},  # 传入完整历史
            inner_config,
            version="v2",
        ):
            evt_type = event.get("event")
            tool_name = event.get("name", "")

            # 检测 task 工具的开始和结束，用于跟踪子代理执行状态
            if evt_type == "on_tool_start" and tool_name == "task":
                # 发送 agent:call 事件
                inp = event.get("data", {}).get("input", {})
                subagent_type = (
                    inp.get("subagent_type", "unknown") if isinstance(inp, dict) else "unknown"
                )
                description = inp.get("description", "")[:500] if isinstance(inp, dict) else ""
                # 使用 LangChain 的 run_id 作为唯一实例 ID
                # run_id 在 event["run_id"] 中
                run_id = event.get("run_id", uuid.uuid4().hex[:8])
                instance_id = f"{subagent_type}_{run_id}"

                # 通过 parent_ids 计算正确的深度
                # 遍历 parent_ids 查找父级 task 的深度
                parent_ids = event.get("parent_ids", [])
                parent_depth = 0
                for pid in parent_ids:
                    if pid in task_run_id_to_agent:
                        parent_depth = task_run_id_to_agent[pid][2]  # 获取父级的 depth
                        break
                current_depth = parent_depth + 1

                # 记录 task run_id 到 agent 的映射
                task_run_id_to_agent[run_id] = (
                    instance_id,
                    subagent_type,
                    current_depth,
                )
                logger.debug(
                    "Subagent started: instance_id=%s, run_id=%s, depth=%d",
                    instance_id,
                    run_id,
                    current_depth,
                )
                await emit_event(
                    presenter.present_agent_call(
                        agent_id=instance_id,  # 使用唯一实例 ID
                        agent_name=subagent_type,  # 显示名称为类型
                        input_message=description,
                        depth=current_depth,
                    )
                )
                continue

            if evt_type == "on_tool_end" and tool_name == "task":
                # 发送 agent:result 事件
                out = event.get("data", {}).get("output")
                # 从 Command 对象中提取结果（如果是 Command）
                result_text = str(out) if out is not None else ""
                if out is not None and hasattr(out, "update"):
                    # Command 对象，提取 ToolMessage
                    update_dict = out.update if isinstance(out.update, dict) else {}
                    messages = update_dict.get("messages", [])
                    if messages and hasattr(messages[0], "content"):
                        result_text = messages[0].content
                # 通过 run_id 获取对应的子代理实例（而不是 pop 栈）
                run_id = event.get("run_id", "")
                agent_info = task_run_id_to_agent.get(run_id)
                if agent_info:
                    current_instance_id, _, current_depth = agent_info
                    # 清理 run_id 映射
                    del task_run_id_to_agent[run_id]
                else:
                    current_instance_id = "unknown"
                    current_depth = 1
                logger.debug(
                    "Subagent ended: instance_id=%s, depth=%d",
                    current_instance_id,
                    current_depth,
                )
                await emit_event(
                    presenter.present_agent_result(
                        agent_id=current_instance_id,  # 使用唯一实例 ID
                        result=result_text,
                        success=True,
                        depth=current_depth,
                    )
                )
                continue

            # 获取当前子代理ID
            # 策略：使用 parent_ids 查找事件所属的 task
            # 这样可以正确处理并行子代理的情况
            current_agent_id = None
            current_depth = 0
            parent_ids = event.get("parent_ids", [])

            # 遍历 parent_ids 查找匹配的 task
            for pid in parent_ids:
                if pid in task_run_id_to_agent:
                    agent_info = task_run_id_to_agent[pid]
                    current_agent_id = agent_info[0]  # instance_id
                    current_depth = agent_info[2]  # depth
                    break

            # 调试日志：帮助诊断并行子代理问题
            if current_depth > 0:
                logger.debug(
                    "Event %s/%s: agent_id=%s, depth=%d, run_id=%s, parent_ids=%s",
                    evt_type,
                    tool_name or "N/A",
                    current_agent_id,
                    current_depth,
                    event.get("run_id", "N/A"),
                    parent_ids[:2] if parent_ids else [],  # 只显示前2个避免日志过长
                )

            if evt_type == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk:
                    content = chunk.content

                    # 处理字符串内容（普通文本）
                    if isinstance(content, str) and content:
                        # 只累计主代理的输出
                        if current_depth == 0:
                            output_text += content
                        await emit_event(
                            presenter.present_text(
                                content,
                                depth=current_depth,
                                agent_id=current_agent_id,
                            )
                        )

                    # 处理列表内容（Anthropic 格式，包含 thinking、text、tool_use 等）
                    elif isinstance(content, list):
                        for block in content:
                            btype = block.get("type", "") if isinstance(block, dict) else ""

                            if btype == "thinking":
                                # Anthropic extended thinking
                                thinking_text = block.get("thinking", "")
                                if thinking_text:
                                    # 为每个 (depth, agent_id) 组合维护独立的 thinking_id
                                    thinking_key = f"{current_depth}:{current_agent_id}"
                                    if thinking_ids.get(thinking_key) is None:
                                        thinking_ids[thinking_key] = (
                                            f"thinking_{uuid.uuid4().hex[:8]}"
                                        )
                                    await emit_event(
                                        presenter.present_thinking(
                                            thinking_text,
                                            thinking_id=thinking_ids[thinking_key],
                                            depth=current_depth,
                                            agent_id=current_agent_id,
                                        )
                                    )

                            elif btype == "text":
                                # 普通文本
                                text = block.get("text", "")
                                if text:
                                    # thinking 结束，重置对应 agent 的 thinking_id
                                    thinking_key = f"{current_depth}:{current_agent_id}"
                                    if thinking_ids.get(thinking_key):
                                        thinking_ids[thinking_key] = None
                                    # 只累计主代理的输出
                                    if current_depth == 0:
                                        output_text += text
                                    await emit_event(
                                        presenter.present_text(
                                            text,
                                            depth=current_depth,
                                            agent_id=current_agent_id,
                                        )
                                    )

                            elif btype == "tool_use":
                                # 工具调用在 on_tool_start 中处理，这里忽略
                                pass

            elif evt_type == "on_tool_start":
                inp = event.get("data", {}).get("input", {})
                await emit_event(
                    presenter.present_tool_start(
                        tool_name,
                        inp,
                        depth=current_depth,
                        agent_id=current_agent_id,
                    )
                )

            elif evt_type == "on_tool_end":
                out = event.get("data", {}).get("output", "")
                await emit_event(
                    presenter.present_tool_result(
                        tool_name,
                        str(out),
                        depth=current_depth,
                        agent_id=current_agent_id,
                    )
                )

        # 获取内层 graph 的最终状态（包含所有生成的消息）
        inner_state = await inner_graph.aget_state(inner_config)
        new_messages = inner_state.values.get("messages", [])

        # 滑动窗口截断
        max_messages = settings.SESSION_MAX_MESSAGES
        # 只取新生成的消息（去掉我们传入的历史部分）
        final_messages = new_messages if len(new_messages) > len(all_messages) else all_messages
        trimmed_messages = (
            final_messages[-max_messages:] if len(final_messages) > max_messages else final_messages
        )

        return {
            "output": output_text,
            "messages": trimmed_messages,
        }
    finally:
        # 关闭 sandbox（无论成功失败都要关闭）
        try:
            if sandbox_id:
                await SandboxFactory.close_sandbox(sandbox_id)
        except Exception as e:
            logger.warning(f"Failed to close sandbox: {e}")


# ============================================================================
# 后续可扩展的节点
# ============================================================================


async def retrieve_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    检索节点（示例）

    从知识库检索相关文档，添加到状态中。
    """
    # TODO: 实现检索逻辑
    # input_text = state.get("input", "")
    # docs = await retriever.aretrieve(input_text)
    # return {"retrieved_docs": docs}
    return state


async def summarize_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    总结节点（示例）

    对输出进行总结或格式化。
    """
    # TODO: 实现总结逻辑
    return state
