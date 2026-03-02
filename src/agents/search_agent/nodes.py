"""
Search Agent 节点

LangGraph 节点函数，使用 deep agent 执行任务。
后续可扩展：retrieve_node, summarize_node 等。
"""

import logging
import time
import uuid
from typing import Any, Dict

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.core.base import get_presenter
from src.agents.search_agent.context import AgentContext
from src.agents.search_agent.prompt import DEFAULT_SYSTEM_PROMPT, SANDBOX_SYSTEM_PROMPT
from src.infra.agent import AgentEventProcessor
from src.infra.backend import (
    create_postgres_backend_factory,
    create_sandbox_backend_factory,
)
from src.infra.llm.client import LLMClient
from src.infra.sandbox import SessionSandboxManager
from src.infra.skill import load_skill_files
from src.infra.skill.loader import build_skills_prompt
from src.infra.storage.checkpoint import get_async_checkpointer
from src.infra.storage.postgres import create_postgres_store
from src.infra.writer.present import Presenter
from src.kernel.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# 节点函数
# ============================================================================


async def agent_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Agent 主节点

    创建 deep agent (内层 graph) 并执行，通过 presenter 流式发送事件。
    历史消息从内层 graph 的 checkpoint 获取（MongoDB持久化）。
    """
    start_time = time.time()

    presenter = get_presenter(config)
    configurable = config.get("configurable", {})
    context: AgentContext = configurable.get("context", AgentContext())

    # 获取 agent_options
    agent_options = configurable.get("agent_options") or {}
    enable_thinking = agent_options.get("enable_thinking", False)
    logger.info(f"agent_options: {agent_options}")

    # 获取附件
    attachments = state.get("attachments", [])

    # 发送用户消息事件
    await presenter.emit_user_message(
        state.get("input", ""), attachments=attachments if attachments else None
    )

    # 创建 LLM
    llm = LLMClient.get_deep_agent_model(
        api_base=settings.LLM_API_BASE,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        thinking={"type": "enabled"} if enable_thinking else None,
    )

    # 多租户隔离
    tenant_id = context.user_id or "default"
    assistant_id = f"assistant-{tenant_id}"

    # 加载技能文件和技能列表（一次数据库查询）
    skill_result = await load_skill_files(context.user_id)
    initial_skill_files = skill_result["files"]
    skills_list = skill_result["skills"]

    # 创建 Backend 工厂和获取系统提示
    backend_factory, system_prompt, store = await _create_backend_and_prompt(
        state=state,
        context=context,
        presenter=presenter,
        assistant_id=assistant_id,
        skills=skills_list,
    )

    # 设置系统提示
    context.system_prompt = system_prompt

    # 过滤工具
    filtered_tools = None
    if settings.ENABLE_MCP:
        filtered_tools = context.filter_tools()

    # 创建内层 graph (deep agent)
    inner_checkpointer = await get_async_checkpointer()

    # 传入 skills 参数
    skills_param = None
    if settings.ENABLE_SKILLS:
        skills_param = ["/skills/"]

    inner_graph = create_deep_agent(
        model=llm,
        system_prompt=context.system_prompt,
        backend=backend_factory,
        tools=filtered_tools if filtered_tools else None,
        checkpointer=inner_checkpointer,
        store=store,  # 传递 PostgresStore
        skills=skills_param,
    ).with_config({"recursion_limit": settings.SESSION_MAX_RUNS_PER_SESSION})

    inner_config: RunnableConfig = {
        "configurable": {
            "thread_id": state.get("session_id", str(uuid.uuid4())),
            "backend": backend_factory,
        },
        "recursion_limit": config.get("recursion_limit", settings.SESSION_MAX_RUNS_PER_SESSION),
    }

    # 从内层 graph 的 checkpoint 获取历史消息
    inner_state = await inner_graph.aget_state(inner_config)
    existing_messages = inner_state.values.get("messages", [])

    # 构建传入的消息列表
    new_message = HumanMessage(content=state.get("input", ""))
    all_messages = existing_messages + [new_message]

    # 传递 messages 给 sync_conversation 工具使用
    inner_config["configurable"]["messages"] = existing_messages

    # 创建事件处理器
    event_processor = AgentEventProcessor(presenter)

    # 流式处理事件
    async for event in inner_graph.astream_events(
        {"messages": all_messages, "files": initial_skill_files},
        inner_config,
        version="v2",
    ):
        await event_processor.process_event(event)

    # 发送 token 使用统计事件
    await _emit_token_usage(event_processor, presenter, start_time)

    # 获取内层 graph 的最终状态
    inner_state = await inner_graph.aget_state(inner_config)
    new_messages = inner_state.values.get("messages", [])

    final_messages = new_messages if len(new_messages) > len(all_messages) else all_messages

    return {
        "output": event_processor.output_text,
        "messages": final_messages,
    }


async def _create_backend_and_prompt(
    state: Dict[str, Any],
    context: AgentContext,
    presenter: Presenter,
    assistant_id: str,
    skills: list[dict],
) -> tuple[Any, str, Any]:
    """
    创建 Backend 工厂函数和系统提示

    根据是否启用沙箱模式，返回相应的 Backend 工厂和系统提示。
    同时构建并注入 skills 提示。

    Args:
        state: 状态字典
        context: Agent 上下文
        presenter: 输出处理器
        assistant_id: 助手 ID
        skills: 预加载的技能列表，用于构建 skills prompt

    Returns:
        (backend_factory, system_prompt, store) 元组，store 在沙箱模式下为 None
    """
    # 构建 skills 提示（使用预加载的 skills，避免重复数据库查询）
    skills_prompt = ""
    if settings.ENABLE_SKILLS and skills:
        try:
            skills_prompt = await build_skills_prompt(skills)
        except Exception as e:
            logger.warning(f"Failed to build skills prompt: {e}")

    # 使用 PostgreSQL，每个 agent 创建独立的 store 实例
    store = create_postgres_store()

    if not settings.ENABLE_SANDBOX:
        logger.info(
            f"Sandbox disabled, using CompositeBackend with PostgresStore for assistant: {assistant_id}"
        )
        return (
            create_postgres_backend_factory(assistant_id),
            DEFAULT_SYSTEM_PROMPT.replace("{skills}", skills_prompt),
            store,
        )

    # 沙箱模式
    sandbox_manager = SessionSandboxManager()

    # 发送沙箱开始初始化事件
    try:
        await presenter.emit_sandbox_starting()
    except Exception as e:
        logger.warning(f"Failed to emit sandbox:starting event: {e}")

    try:
        sandbox_backend, work_dir = await sandbox_manager.get_or_create(
            session_id=state.get("session_id", str(uuid.uuid4())),
            user_id=context.user_id or "default",
        )

        # 发送沙箱就绪事件
        try:
            await presenter.emit_sandbox_ready(
                sandbox_id=sandbox_backend.id,
                work_dir=work_dir,
            )
        except Exception as e:
            logger.warning(f"Failed to emit sandbox:ready event: {e}")

        logger.info(f"Sandbox enabled, using sandbox backend for assistant: {assistant_id}")

        # 格式化沙箱提示词，注入 work_dir 和 skills
        system_prompt = SANDBOX_SYSTEM_PROMPT.replace("{work_dir}", work_dir).replace(
            "{skills}", skills_prompt
        )
        return (
            create_sandbox_backend_factory(sandbox_backend, assistant_id),
            system_prompt,
            store,
        )

    except Exception as e:
        # 发送沙箱初始化失败事件
        try:
            await presenter.emit_sandbox_error(f"沙箱初始化失败: {str(e)}")
        except Exception as emit_err:
            logger.warning(f"Failed to emit sandbox:error event: {emit_err}")
        raise


async def _emit_token_usage(
    event_processor: AgentEventProcessor,
    presenter: Presenter,
    start_time: float,
) -> None:
    """发送 token 使用统计事件"""
    total_input_tokens = event_processor.total_input_tokens
    total_output_tokens = event_processor.total_output_tokens
    total_tokens = event_processor.total_tokens

    if total_input_tokens > 0 or total_output_tokens > 0 or total_tokens > 0:
        if total_tokens == 0:
            total_tokens = total_input_tokens + total_output_tokens

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
