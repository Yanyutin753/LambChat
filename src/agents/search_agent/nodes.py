"""
Search Agent 节点

LangGraph 节点函数，使用 deep agent 执行任务。
后续可扩展：retrieve_node, summarize_node 等。
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from src.agents.core.base import get_presenter
from src.agents.search_agent.context import AgentContext
from src.agents.search_agent.prompt import DEFAULT_SYSTEM_PROMPT, SANDBOX_SYSTEM_PROMPT
from src.infra.llm.client import LLMClient
from src.infra.sandbox import get_sandbox_from_settings

# 获取 sandbox_id 用于关闭
from src.infra.sandbox.base import SandboxFactory
from src.infra.skill.middleware import SkillsMiddleware

# 设置全局 middleware 供 inject_skill 工具使用
from src.infra.tool.inject_skill import set_skills_middleware
from src.infra.writer.present import _get_timestamp
from src.kernel.config import settings

logger = logging.getLogger(__name__)


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
        api_base=settings.LLM_API_BASE,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        thinking={"type": "enabled"} if enable_thinking else None,
    )

    try:
        # 创建 sandbox backend (langchain-daytona/runloop/modal)
        # 每次请求创建新的 sandbox，函数结束时关闭
        sandbox_id = None  # Initialize before the if block

        if settings.ENABLE_SANDBOX:
            backend = get_sandbox_from_settings()
            sandbox_id = SandboxFactory.get_sandbox_id(backend)

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
                        SANDBOX_SYSTEM_PROMPT
                    )

        else:

            def backend(rt):
                return StateBackend(rt)

            context.system_prompt = DEFAULT_SYSTEM_PROMPT
            logger.warning(
                "Sandbox is disabled (ENABLE_SANDBOX=False), using CompositeBackend: 临时"
            )

        # 过滤工具（根据用户选择的 enabled_tools）
        if settings.ENABLE_MCP:
            filtered_tools = context.filter_tools()

        # 创建内层 graph (deep agent)
        inner_graph = create_deep_agent(
            model=llm,
            system_prompt=context.system_prompt,
            backend=backend,
            tools=filtered_tools if filtered_tools and settings.ENABLE_MCP else None,
            checkpointer=MemorySaver(),
        ).with_config({"recursion_limit": settings.SESSION_MAX_RUNS_PER_SESSION})

        inner_config: RunnableConfig = {
            "configurable": {
                "thread_id": state.get("session_id", str(uuid.uuid4())),
                "backend": backend,  # 传递 backend 给工具使用
                "messages": existing_messages,  # 传递 messages 给 sync_conversation 工具使用
            },
            "recursion_limit": config.get("recursion_limit", settings.SESSION_MAX_RUNS_PER_SESSION),
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
                inp: Dict[str, Any] = event.get("data", {}).get("input", {})
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
