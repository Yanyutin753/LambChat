"""
Search Agent 节点

LangGraph 节点函数，使用 deep agent 执行任务。
后续可扩展：retrieve_node, summarize_node 等。
"""

import time
import uuid
from typing import Any, Dict

from deepagents import create_deep_agent
from deepagents.middleware.subagents import CompiledSubAgent, SubAgent
from langchain_core.runnables import RunnableConfig

from src.agents.core.base import get_presenter
from src.agents.core.node_utils import (
    build_human_message,
    emit_token_usage,
    resolve_fallback_model,
)
from src.agents.core.subagent_prompts import SUBAGENT_PROMPT, get_memory_guide
from src.agents.core.thinking import build_thinking_config
from src.agents.search_agent.context import SearchAgentContext
from src.agents.search_agent.prompt import DEFAULT_SYSTEM_PROMPT, SANDBOX_SYSTEM_PROMPT
from src.infra.agent import AgentEventProcessor
from src.infra.agent.middleware import (
    PromptCachingMiddleware,
    SandboxMCPMiddleware,
    SectionPromptMiddleware,
    ToolResultBinaryMiddleware,
    create_retry_middleware,
)
from src.infra.agent.middleware_subagent import SubagentActivityMiddleware
from src.infra.backend import (
    create_persistent_backend_factory,
    create_sandbox_backend_factory,
)
from src.infra.llm.client import LLMClient
from src.infra.logging import get_logger
from src.infra.sandbox.session_manager import get_session_sandbox_manager
from src.infra.skill.loader import build_skills_prompt
from src.infra.storage.checkpoint import get_async_checkpointer
from src.infra.storage.mongodb_store import create_store
from src.infra.writer.present import Presenter
from src.kernel.config import settings

logger = get_logger(__name__)


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
    context: SearchAgentContext = configurable.get("context", SearchAgentContext())

    # 获取 agent_options
    agent_options = configurable.get("agent_options") or {}
    selected_model = agent_options.get("model")  # Per-request model override
    model_id = agent_options.get("model_id")  # Model config ID for specific channel/provider
    thinking_config = build_thinking_config(agent_options)
    logger.info(f"agent_options: {agent_options}")

    # 获取附件
    attachments = state.get("attachments", [])

    # 创建 LLM
    llm_start = time.time()
    llm = await LLMClient.get_model(
        model=selected_model,
        model_id=model_id,
        thinking=thinking_config,
    )
    llm_init_time = time.time() - llm_start
    logger.debug(f"[Agent] LLM init: {llm_init_time * 1000:.3f}ms")

    # 查询 fallback_model 配置
    fallback_model_value = await resolve_fallback_model(
        model_id, selected_model, log_prefix="[Agent]"
    )

    # 多租户隔离
    tenant_id = context.user_id or "default"
    assistant_id = f"assistant-{tenant_id}"
    logger.info(f"tenant_id: {tenant_id}")

    # 创建 Backend 工厂和获取系统提示
    backend_start = time.time()
    backend_factory, system_prompt, store, sandbox_backend = await _create_backend_and_prompt(
        state=state,
        context=context,
        presenter=presenter,
        assistant_id=assistant_id,
    )
    backend_init_time = time.time() - backend_start
    logger.debug(f"[Agent] Backend init: {backend_init_time * 1000:.3f}ms")

    # 构建 skills 提示（使用预加载的 skills，避免重复数据库查询）
    skills_prompt = ""
    if settings.ENABLE_SKILLS and context.skills:
        try:
            skills_prompt = await build_skills_prompt(context.skills)
        except Exception as e:
            logger.warning(f"Failed to build skills prompt: {e}")

    # 构建记忆系统提示
    memory_guide = get_memory_guide() if settings.ENABLE_MEMORY else ""

    # 过滤工具（懒加载 MCP 工具）
    filtered_tools = None
    if settings.ENABLE_MCP:
        await context.get_tools()
        filtered_tools = context.filter_tools() or None

        # 延迟加载模式：将 search_tools 注册到 ToolNode
        # 这样 ToolNode 的 tools_by_name 里也有 search_tools，
        # 避免 "not a valid tool" 错误
        if context.deferred_manager is not None and filtered_tools is not None:
            from src.infra.tool.tool_search_tool import ToolSearchTool

            search_tool = ToolSearchTool(
                manager=context.deferred_manager,
                search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
            )
            filtered_tools.append(search_tool)

    # 创建内层 graph (deep agent)
    checkpointer_start = time.time()
    inner_checkpointer = await get_async_checkpointer()
    checkpointer_init_time = time.time() - checkpointer_start
    logger.debug(f"[Agent] Checkpointer init: {checkpointer_init_time * 1000:.3f}ms")

    # 创建 graph（带计时）
    graph_compile_start = time.time()

    # 自定义子代理配置 - 强制将所有中间信息保存到文件
    search_base_url = configurable.get("base_url", "")
    subagent_middleware = [
        *create_retry_middleware(fallback_model=fallback_model_value, thinking=thinking_config),
        ToolResultBinaryMiddleware(base_url=search_base_url),
        SubagentActivityMiddleware(backend=backend_factory),
    ]
    if context.deferred_manager is not None:
        from src.infra.agent.middleware import ToolSearchMiddleware

        subagent_middleware.append(
            ToolSearchMiddleware(
                deferred_manager=context.deferred_manager,
                search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
            )
        )

    custom_subagents: list[SubAgent | CompiledSubAgent] = [
        {
            "name": "general-purpose",
            "description": "General-purpose agent for researching complex questions, searching for files and content, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you. This agent has access to all tools as the main agent.",
            "system_prompt": SUBAGENT_PROMPT,
            "middleware": subagent_middleware,
        }
    ]

    # 构建中间件栈：retry → binary → sandbox_mcp → skills+memory → memory_index → tool search → cache tag
    # Order: stable → semi-stable → dynamic → cache breakpoint
    # sandbox_mcp 在 skills 前使 memory_guide 紧挨 memory_index，形成连续 memory 区域
    user_middleware = create_retry_middleware(
        fallback_model=fallback_model_value, thinking=thinking_config
    )
    user_middleware.append(ToolResultBinaryMiddleware(base_url=search_base_url))
    # SandboxMCP: session-stable (30-min cache)
    if sandbox_backend:
        user_middleware.append(
            SandboxMCPMiddleware(backend=sandbox_backend, user_id=context.user_id or "default")
        )
    # Skills + memory guide: session-static (one SectionPromptMiddleware, multiple blocks)
    _prompt_sections = [s for s in (skills_prompt, memory_guide) if s]
    if _prompt_sections:
        user_middleware.append(SectionPromptMiddleware(sections=_prompt_sections))
    if settings.ENABLE_MEMORY and settings.NATIVE_MEMORY_INDEX_ENABLED and context.user_id:
        from src.infra.agent.middleware import MemoryIndexMiddleware

        user_middleware.append(MemoryIndexMiddleware(user_id=context.user_id))

    # Tool search: per-turn dynamic content
    if context.deferred_manager is not None:
        from src.infra.agent.middleware import ToolSearchMiddleware

        user_middleware.append(
            ToolSearchMiddleware(
                deferred_manager=context.deferred_manager,
                search_limit=settings.DEFERRED_TOOL_SEARCH_LIMIT,
            )
        )
        logger.info("[SearchAgent] Tool search middleware enabled (deferred MCP loading)")

    # KV cache: tag final system block + last tool AFTER all dynamic injection
    user_middleware.append(PromptCachingMiddleware())

    inner_graph = create_deep_agent(
        model=llm,
        system_prompt=system_prompt,
        backend=backend_factory,
        tools=filtered_tools,
        checkpointer=inner_checkpointer,
        store=store,  # 传递 PostgresStore
        skills=None,  # 禁用 SkillsMiddleware，使用 build_skills_prompt 代替
        subagents=custom_subagents,
        middleware=user_middleware,
    ).with_config({"recursion_limit": settings.SESSION_MAX_RUNS_PER_SESSION})
    graph_compile_time = time.time() - graph_compile_start
    logger.debug(f"[Agent] Graph compile: {graph_compile_time * 1000:.3f}ms")

    inner_config: RunnableConfig = {
        "configurable": {
            "thread_id": state.get("session_id", str(uuid.uuid4())),
            "backend": backend_factory,
            "context": context,  # 传递 context 以便工具访问 user_id
            "base_url": configurable.get("base_url", ""),  # 传递 base_url 给工具使用
            "presenter": presenter,  # 传递 presenter 给工具调用
        },
        "recursion_limit": config.get("recursion_limit", settings.SESSION_MAX_RUNS_PER_SESSION),
    }

    # 构建传入的新消息（包含附件）
    # 注意：checkpointer + add_messages reducer 会自动维护历史消息，
    # 只需传入新消息，避免与 checkpoint 中的历史消息重复。
    user_input = state.get("input", "")
    new_message = build_human_message(user_input, attachments)

    # 创建事件处理器（使用 AgentEventProcessor 处理 astream_events）
    logger.info("[SearchAgent] Creating AgentEventProcessor")
    event_processor = AgentEventProcessor(presenter, base_url=configurable.get("base_url", ""))

    logger.info("[SearchAgent] Starting astream_events")
    # 流式处理事件（不重试，直接调用）
    async for event in inner_graph.astream_events(
        {"messages": [new_message]},
        inner_config,
        version="v2",
    ):
        await event_processor.process_event(event)
    # Flush any remaining buffered chunks
    await event_processor.flush()

    if settings.ENABLE_MEMORY and context.user_id:
        from src.infra.memory.tools import schedule_auto_memory_capture

        schedule_auto_memory_capture(context.user_id, user_input)

    # 发送 token 使用统计事件
    await emit_token_usage(
        event_processor,
        presenter,
        start_time,
        model_id=model_id,
        model=selected_model,
    )

    # 获取内层 graph 的最终状态
    inner_state = await inner_graph.aget_state(inner_config)
    final_messages = inner_state.values.get("messages", [])

    # 持久化已发现的延迟工具名（跨 turn 恢复，分布式安全）
    session_id = state.get("session_id", "")
    if context.deferred_manager is not None and context.deferred_manager.discovered_count > 0:
        try:
            from src.infra.tool.deferred_manager import persist_discovered_tools

            await persist_discovered_tools(
                session_id,
                context.deferred_manager.discovered_names,
            )
        except Exception:
            pass  # 非关键路径，失败静默

    output_text = event_processor.output_text
    event_processor.clear()

    return {
        "output": output_text,
        "messages": final_messages,
    }


async def _create_backend_and_prompt(
    state: Dict[str, Any],
    context: SearchAgentContext,
    presenter: Presenter,
    assistant_id: str,
) -> tuple[Any, str, Any, Any]:
    """
    创建 Backend 工厂函数和系统提示

    根据是否启用沙箱模式，返回相应的 Backend 工厂和系统提示。
    skills 和 memory_guide 的注入由 SectionPromptMiddleware 在请求时完成（KV cache 友好）。

    Args:
        state: 状态字典
        context: Agent 上下文
        presenter: 输出处理器
        assistant_id: 助手 ID

    Returns:
        (backend_factory, system_prompt, store, sandbox_backend) 元组。
        sandbox_backend 在沙箱模式下为 CompositeBackend 实例，否则为 None。
    """
    # 创建 store（优先 PostgreSQL → MongoDB fallback）
    store = create_store()

    # 获取 user_id
    user_id = context.user_id or "default"

    if not settings.ENABLE_SANDBOX:
        # 非沙箱模式：使用持久化 backend（PostgreSQL 或 MongoDB，由 store 决定）
        logger.info(f"Sandbox disabled, using PersistentBackend for assistant: {assistant_id}")
        backend_factory = create_persistent_backend_factory(assistant_id, user_id=user_id)
        return backend_factory, DEFAULT_SYSTEM_PROMPT, store, None

    # 沙箱模式
    if not context.user_id:
        raise ValueError("Sandbox requires authenticated user (user_id is required)")

    sandbox_manager = get_session_sandbox_manager()

    # 发送沙箱开始初始化事件
    try:
        await presenter.emit_sandbox_starting()
    except Exception as e:
        logger.warning(f"Failed to emit sandbox:starting event: {e}")

    try:
        sandbox_backend, work_dir = await sandbox_manager.get_or_create(
            session_id=state.get("session_id", str(uuid.uuid4())),
            user_id=context.user_id,
        )

        # 发送沙箱就绪事件
        try:
            # 获取 sandbox_id：CompositeBackend.default 可能是 SandboxBackendProtocol
            # 需要安全地访问 id 属性
            sandbox_id = getattr(sandbox_backend.default, "id", "unknown")
            await presenter.emit_sandbox_ready(
                sandbox_id=sandbox_id,
                work_dir=work_dir,
            )
        except Exception as e:
            logger.warning(f"Failed to emit sandbox:ready event: {e}")

        logger.info(f"Sandbox enabled, using sandbox backend for assistant: {assistant_id}")

        # 格式化沙箱提示词，注入 work_dir（skills/memory_guide 由 SectionPromptMiddleware 注入）
        system_prompt = SANDBOX_SYSTEM_PROMPT.replace("{work_dir}", work_dir)

        return (
            create_sandbox_backend_factory(sandbox_backend.default, assistant_id, user_id=user_id),
            system_prompt,
            store,
            sandbox_backend,
        )

    except Exception as e:
        # 发送沙箱初始化失败事件
        try:
            await presenter.emit_sandbox_error(f"沙箱初始化失败: {str(e)}")
        except Exception as emit_err:
            logger.warning(f"Failed to emit sandbox:error event: {emit_err}")
        raise
