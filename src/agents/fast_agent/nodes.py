"""
Fast Agent 节点 - 无沙箱，快速响应

基于 deep_agent/nodes.py 简化，移除沙箱相关逻辑。
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
    schedule_auto_retain,
)
from src.agents.core.subagent_prompts import SUBAGENT_PROMPT, get_memory_guide
from src.agents.fast_agent.context import FastAgentContext
from src.agents.fast_agent.prompt import FAST_SYSTEM_PROMPT
from src.infra.agent import AgentEventProcessor
from src.infra.agent.middleware import (
    AppPromptMiddleware,
    PromptCachingMiddleware,
    SubagentActivityMiddleware,
    ToolResultBinaryMiddleware,
    create_retry_middleware,
)
from src.infra.backend.deepagent import create_persistent_backend_factory
from src.infra.llm.client import LLMClient
from src.infra.logging import get_logger
from src.infra.skill.loader import build_skills_prompt
from src.infra.storage.checkpoint import get_async_checkpointer
from src.infra.storage.mongodb_store import create_store
from src.kernel.config import settings

logger = get_logger(__name__)


# ============================================================================
# 节点函数
# ============================================================================


async def fast_agent_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Fast Agent 主节点 - 无沙箱，快速响应

    特点：
    - 不使用沙箱（直接使用内存 backend）
    - 支持技能（Skills）
    - 支持长期存储（可选）
    - 流式输出
    """
    start_time = time.time()

    presenter = get_presenter(config)
    configurable = config.get("configurable", {})
    context: FastAgentContext = configurable.get("context", FastAgentContext())

    # 获取 agent_options
    agent_options = configurable.get("agent_options") or {}
    enable_thinking = agent_options.get("enable_thinking", False)

    # 获取附件
    attachments = state.get("attachments", [])

    # 创建 LLM
    llm_start = time.time()
    llm = LLMClient.get_model(
        api_base=settings.LLM_API_BASE,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        thinking={"type": "enabled"} if enable_thinking else None,
    )
    llm_init_time = time.time() - llm_start
    logger.debug(f"[FastAgent] LLM init: {llm_init_time * 1000:.3f}ms")

    # 多租户隔离
    tenant_id = context.user_id or "default"
    assistant_id = f"assistant-{tenant_id}"

    # 构建 skills 提示
    skills_prompt = ""
    if settings.ENABLE_SKILLS and context.skills:
        try:
            skills_start = time.time()
            skills_prompt = await build_skills_prompt(context.skills)
            skills_init_time = time.time() - skills_start
            logger.debug(f"[FastAgent] Skills prompt init: {skills_init_time * 1000:.3f}ms")
        except Exception as e:
            logger.warning(f"Failed to build skills prompt: {e}")

    # 构建记忆系统提示
    memory_guide = get_memory_guide(settings.MEMORY_PERFORM) if settings.ENABLE_MEMORY else ""

    # 构建系统提示（skills/memory_guide 由 AppPromptMiddleware 在请求时注入）
    system_prompt = FAST_SYSTEM_PROMPT

    # 创建 backend（无沙箱，PostgreSQL 或 MongoDB 由 store 决定）
    backend_start = time.time()
    backend_factory = create_persistent_backend_factory(
        assistant_id=assistant_id, user_id=context.user_id
    )
    logger.info(f"[FastAgent] Using PersistentBackend for assistant: {assistant_id}")
    backend_init_time = time.time() - backend_start
    logger.debug(f"[FastAgent] Backend init: {backend_init_time * 1000:.3f}ms")

    # 创建 store（优先 PostgreSQL → MongoDB fallback）
    store = create_store()

    # 过滤工具（懒加载 MCP 工具）
    filtered_tools = None
    if settings.ENABLE_MCP:
        await context.get_tools()
        filtered_tools = context.filter_tools() or None

    # 创建内层 graph (deep agent)
    checkpointer_start = time.time()
    inner_checkpointer = await get_async_checkpointer()
    checkpointer_init_time = time.time() - checkpointer_start
    logger.debug(f"[FastAgent] Checkpointer init: {checkpointer_init_time * 1000:.3f}ms")

    graph_compile_start = time.time()

    # 自定义子代理配置 - 强制将所有中间信息保存到文件
    subagent_base_url = configurable.get("base_url", "")
    custom_subagents: list[SubAgent | CompiledSubAgent] = [
        {
            "name": "general-purpose",
            "description": "General-purpose agent for researching complex questions, searching for files and content, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you. This agent has access to all tools as the main agent.",
            "system_prompt": SUBAGENT_PROMPT,
            "middleware": [
                *create_retry_middleware(),
                ToolResultBinaryMiddleware(base_url=subagent_base_url),
                SubagentActivityMiddleware(backend=backend_factory),
            ],
        }
    ]

    # 构建中间件栈：retry → binary upload → app prompt (skills/memory) → memory index → cache tag
    user_middleware = create_retry_middleware()
    user_middleware.append(ToolResultBinaryMiddleware(base_url=subagent_base_url))
    user_middleware.append(
        AppPromptMiddleware(skills_prompt=skills_prompt, memory_guide=memory_guide)
    )
    if (
        settings.ENABLE_MEMORY
        and settings.MEMORY_PERFORM == "native"
        and settings.NATIVE_MEMORY_INDEX_ENABLED
        and context.user_id
    ):
        from src.infra.agent.middleware import MemoryIndexMiddleware

        user_middleware.append(MemoryIndexMiddleware(user_id=context.user_id))

    # KV cache: tag final system block + last tool AFTER all dynamic injection
    user_middleware.append(PromptCachingMiddleware())

    inner_graph = create_deep_agent(
        model=llm,
        system_prompt=system_prompt,
        backend=backend_factory,
        tools=filtered_tools,
        checkpointer=inner_checkpointer,
        store=store,
        skills=None,
        subagents=custom_subagents,
        middleware=user_middleware,
    ).with_config({"recursion_limit": settings.SESSION_MAX_RUNS_PER_SESSION})
    graph_compile_time = time.time() - graph_compile_start
    logger.debug(f"[FastAgent] Graph compile: {graph_compile_time * 1000:.3f}ms")

    inner_config: RunnableConfig = {
        "configurable": {
            "thread_id": state.get("session_id", str(uuid.uuid4())),
            "backend": backend_factory,
            "context": context,
            "base_url": configurable.get("base_url", ""),
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
    logger.info("[FastAgent] Creating AgentEventProcessor")
    event_processor = AgentEventProcessor(presenter, base_url=configurable.get("base_url", ""))

    logger.info("[FastAgent] Starting astream_events")
    # 流式处理事件（不重试，直接调用）
    async for event in inner_graph.astream_events(
        {"messages": [new_message], "files": {}},
        inner_config,
        version="v2",
    ):
        await event_processor.process_event(event)
    # Flush any remaining buffered chunks
    await event_processor._flush_chunk_buffer()
    logger.info("[FastAgent] astream_events completed")

    # 发送 token 使用统计事件
    await emit_token_usage(event_processor, presenter, start_time)

    # 获取内层 graph 的最终状态
    inner_state = await inner_graph.aget_state(inner_config)
    final_messages = inner_state.values.get("messages", [])

    # 自动记忆存储（异步，不阻塞响应）
    session_id = state.get("session_id")
    schedule_auto_retain(
        user_input, event_processor.output_text, context.user_id, session_id=session_id
    )

    return {
        "output": event_processor.output_text,
        "messages": final_messages,
    }
