"""
Search Agent 节点

LangGraph 节点函数，使用 deep agent 执行任务。
后续可扩展：retrieve_node, summarize_node 等。
"""

import logging
import time
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
from src.infra.sandbox import SessionSandboxManager
from src.infra.skill.middleware import SkillsMiddleware

# 设置全局 middleware 供 inject_skill 工具使用
from src.infra.tool.inject_skill import set_skills_middleware
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
    # 记录开始时间
    start_time = time.time()

    presenter = get_presenter(config)
    configurable = config.get("configurable", {})
    context: AgentContext = configurable.get("context", AgentContext())

    # 获取 agent_options（支持所有选项）
    agent_options = configurable.get("agent_options") or {}
    enable_thinking = agent_options.get("enable_thinking", False)
    logger.info(f"agent_options: {agent_options}")

    # 获取历史消息
    existing_messages = state.get("messages", [])
    new_message = HumanMessage(content=state.get("input", ""))

    # 发送用户消息事件
    await presenter.emit_user_message(state.get("input", ""))

    llm = LLMClient.get_deep_agent_model(
        api_base=settings.LLM_API_BASE,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        thinking={"type": "enabled"} if enable_thinking else None,
    )

    # 创建 sandbox backend (langchain-daytona/runloop/modal)
    # 使用 SessionSandboxManager 管理 session-sandbox 绑定
    # 对话结束时 stop 而非 delete，下次对话可恢复
    sandbox_manager = None
    workflow_path = None

    if settings.ENABLE_SANDBOX:
        sandbox_manager = SessionSandboxManager()

        # 发送沙箱开始初始化事件
        try:
            await presenter.emit_sandbox_starting()
        except Exception as e:
            logger.warning(f"Failed to emit sandbox:starting event: {e}")

        try:
            backend, workflow_path = await sandbox_manager.get_or_create(
                session_id=state.get("session_id", str(uuid.uuid4())),
                user_id=context.user_id or "default",
            )

            # 发送沙箱就绪事件
            try:
                await presenter.emit_sandbox_ready(
                    sandbox_id=backend.id,
                    work_dir=workflow_path,
                )
            except Exception as e:
                logger.warning(f"Failed to emit sandbox:ready event: {e}")

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
                        SANDBOX_SYSTEM_PROMPT.replace("{workflow_path}", workflow_path)
                    )
            else:
                context.system_prompt = SANDBOX_SYSTEM_PROMPT.replace(
                    "{workflow_path}", workflow_path
                )

        except Exception as e:
            # 发送沙箱初始化失败事件
            try:
                await presenter.emit_sandbox_error(f"沙箱初始化失败: {str(e)}")
            except Exception as emit_err:
                logger.warning(f"Failed to emit sandbox:error event: {emit_err}")
            raise

    else:

        def backend(rt):  # type: ignore[misc]
            return StateBackend(rt)

        context.system_prompt = DEFAULT_SYSTEM_PROMPT
        logger.warning("Sandbox is disabled (ENABLE_SANDBOX=False), using CompositeBackend: 临时")

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

    # 构建传入的消息列表 - 包含历史
    all_messages = existing_messages + [new_message]

    # 跟踪子代理（task工具）的执行状态
    # 使用 run_id 映射来追踪子代理（包括其所有子事件）
    # key: task_run_id (task 工具的 run_id), value: (instance_id, subagent_type, depth)
    task_run_id_to_agent: dict[str, tuple[str, str, int]] = {}

    # 收集输出文本
    output_text = ""

    # Token 统计
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0

    # 跟踪每个 (depth, agent_id) 组合的 thinking 块 ID
    # 用于合并同一块的多个 thinking 事件
    thinking_ids: Dict[str, Optional[str]] = {}  # key: f"{depth}:{agent_id}"

    async for event in inner_graph.astream_events(
        {"messages": all_messages},
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
            await presenter.emit(
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
            await presenter.emit(
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

        # 获取 token 使用统计 (on_chat_model_end 事件)
        # 注意：LangChain 的 usage_metadata 在 on_chat_model_end 事件中提供
        if evt_type == "on_chat_model_end":
            response = event.get("data", {}).get("output")
            if response:
                # 尝试从 response.usage_metadata 获取 (AIMessage)
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    # usage_metadata 包含 input_tokens, output_tokens, total_tokens
                    input_tok = usage.get("input_tokens", 0)
                    output_tok = usage.get("output_tokens", 0)
                    total_tok = usage.get("total_tokens", 0)
                    if isinstance(input_tok, int):
                        total_input_tokens += input_tok
                    if isinstance(output_tok, int):
                        total_output_tokens += output_tok
                    if isinstance(total_tok, int):
                        total_tokens += total_tok
                else:
                    # 备选：从 response.metadata 中获取
                    metadata = getattr(response, "metadata", {})
                    if metadata:
                        usage = metadata.get("usage")
                        if usage:
                            input_tok = usage.get("input_tokens", 0)
                            output_tok = usage.get("output_tokens", 0)
                            total_tok = usage.get("total_tokens", 0)
                            if isinstance(input_tok, int):
                                total_input_tokens += input_tok
                            if isinstance(output_tok, int):
                                total_output_tokens += output_tok
                            if isinstance(total_tok, int):
                                total_tokens += total_tok
            continue

        if evt_type == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk:
                content = chunk.content

                # 处理字符串内容（普通文本）
                if isinstance(content, str) and content:
                    # 只累计主代理的输出
                    if current_depth == 0:
                        output_text += content
                    await presenter.emit(
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
                                    thinking_ids[thinking_key] = f"thinking_{uuid.uuid4().hex[:8]}"
                                await presenter.emit(
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
                                await presenter.emit(
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
            await presenter.emit(
                presenter.present_tool_start(
                    tool_name,
                    inp,
                    depth=current_depth,
                    agent_id=current_agent_id,
                )
            )

        elif evt_type == "on_tool_end":
            out = event.get("data", {}).get("output", "")
            await presenter.emit(
                presenter.present_tool_result(
                    tool_name,
                    str(out),
                    depth=current_depth,
                    agent_id=current_agent_id,
                )
            )

    # 发送 token 使用统计事件
    if total_input_tokens > 0 or total_output_tokens > 0 or total_tokens > 0:
        # 如果 total_tokens 为 0，但有其他 token 数，则计算 total
        if total_tokens == 0:
            total_tokens = total_input_tokens + total_output_tokens
        # 计算耗时
        duration = time.time() - start_time
        try:
            await presenter.emit(
                presenter.present_token_usage(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    total_tokens=total_tokens,
                    duration=duration,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to emit token:usage event: {e}")

    # 获取内层 graph 的最终状态（包含所有生成的消息）
    inner_state = await inner_graph.aget_state(inner_config)
    new_messages = inner_state.values.get("messages", [])

    final_messages = new_messages if len(new_messages) > len(all_messages) else all_messages

    return {
        "output": output_text,
        "messages": final_messages,
    }
