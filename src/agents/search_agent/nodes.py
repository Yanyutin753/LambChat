"""
Search Agent 节点

LangGraph 节点函数，使用 deep agent 执行任务。
后续可扩展：retrieve_node, summarize_node 等。
"""

import asyncio
import time
import uuid
from typing import Any, Dict

from deepagents import create_deep_agent
from deepagents.middleware.subagents import CompiledSubAgent, SubAgent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.core.base import get_presenter
from src.agents.core.subagent_prompts import SUBAGENT_PROMPT
from src.agents.search_agent.context import SearchAgentContext
from src.agents.search_agent.prompt import (
    DEFAULT_SYSTEM_PROMPT,
    EMPTY_MEMORY_SECTION,
    HINDSIGHT_MEMORY_SECTION,
    SANDBOX_SYSTEM_PROMPT,
)
from src.infra.agent import AgentEventProcessor
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
# 自动记忆存储
# ============================================================================


def _schedule_auto_retain(
    user_input: str,
    assistant_output: str,
    user_id: str | None,
) -> None:
    """
    调度自动记忆存储任务（异步，不阻塞响应）。

    只存储用户输入，助手回复由记忆后端自动关联。
    统一接口自动选择 Hindsight 或 memU 后端。
    """
    if not settings.ENABLE_MEMORY or not user_id:
        return

    # 只存用户输入（前 500 字符）
    user_input_clean = user_input.strip()
    if not user_input_clean or len(user_input_clean) < 10:
        return

    # 延迟导入避免循环依赖
    from src.infra.memory.tools import schedule_auto_retain

    schedule_auto_retain(
        user_id=user_id,
        conversation_summary=user_input_clean[:500],
        context="user_query",
    )


# ============================================================================
# 消息构建工具
# ============================================================================


def _build_human_message(text: str, attachments: list[dict] | None) -> HumanMessage:
    """
    构建 HumanMessage，将附件信息以文本形式附加到消息中

    Args:
        text: 用户输入的文本
        attachments: 附件列表，每个附件包含:
            - url: 文件访问链接
            - type: 文件类型 (image/video/audio/document)
            - name: 文件名
            - mime_type: MIME 类型 (可选)
            - size: 文件大小 (可选)

    Returns:
        HumanMessage: 包含文本和附件信息的消息
    """
    # 如果没有附件，直接返回纯文本消息
    if not attachments:
        return HumanMessage(content=text)

    # 构建包含附件信息的文本
    enhanced_text = text
    enhanced_text += "\n\n---\n**User Uploaded Attachments:**"

    for attachment in attachments:
        url = attachment.get("url", "")
        name = attachment.get("name", "未知文件")
        file_type = attachment.get("type", "document")
        mime_type = attachment.get("mime_type", "")
        size = attachment.get("size", 0)

        if not url:
            continue

        # 格式化文件大小
        size_str = ""
        if size:
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"

        # 构建附件信息
        enhanced_text += f"\n\n**[{name}]**"
        enhanced_text += f"\n- 类型: {file_type}"
        if mime_type:
            enhanced_text += f" ({mime_type})"
        if size_str:
            enhanced_text += f"\n- 大小: {size_str}"
        enhanced_text += f"\n- 链接: {url}"

    return HumanMessage(content=enhanced_text)


# ============================================================================
# LLM 重试工具
# ============================================================================


def _is_retryable_error(error: Exception) -> bool:
    """判断错误是否可重试（429、网络错误等）"""
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    retryable_patterns = [
        "429",  # rate limit
        "503",  # service unavailable
        "502",  # bad gateway
        "504",  # gateway timeout
        "timeout",
        "connection",
        "network",
        "reset",
        "refused",
        "overloaded",
    ]

    retryable_types = [
        "timeouterror",
        "connectionerror",
        "connectionreseterror",
    ]

    if any(pattern in error_str for pattern in retryable_patterns):
        return True
    if any(rt in error_type for rt in retryable_types):
        return True

    return False


async def _run_with_retry(
    graph,
    input_data: dict,
    config: RunnableConfig,
    event_processor: AgentEventProcessor,
    max_retries: int | None = None,
    base_delay: float | None = None,
) -> None:
    """带重试的 LLM 流式执行（使用 astream_events）"""
    if max_retries is None:
        max_retries = getattr(settings, "LLM_MAX_RETRIES", 3)
    if base_delay is None:
        base_delay = getattr(settings, "LLM_RETRY_DELAY", 1.0)

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            # 使用 astream_events API
            async for event in graph.astream_events(
                input_data,
                config,
                version="v2",
            ):
                # 使用 AgentEventProcessor 处理事件
                await event_processor.process_event(event)
            return
        except Exception as e:
            last_error = e
            if _is_retryable_error(e) and attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                raise

    if last_error is None:
        raise RuntimeError("Unexpected state: no error but loop exhausted")
    raise last_error


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
    enable_thinking = agent_options.get("enable_thinking", False)
    logger.info(f"agent_options: {agent_options}")

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
    logger.debug(f"[Agent] LLM init: {llm_init_time * 1000:.3f}ms")

    # 多租户隔离
    tenant_id = context.user_id or "default"
    assistant_id = f"assistant-{tenant_id}"
    logger.info(f"tenant_id: {tenant_id}")

    # 创建 Backend 工厂和获取系统提示
    backend_start = time.time()
    backend_factory, system_prompt, store = await _create_backend_and_prompt(
        state=state,
        context=context,
        presenter=presenter,
        assistant_id=assistant_id,
        skills=context.skills,
    )
    backend_init_time = time.time() - backend_start
    logger.debug(f"[Agent] Backend init: {backend_init_time * 1000:.3f}ms")

    # 过滤工具（懒加载 MCP 工具）
    filtered_tools = None
    if settings.ENABLE_MCP:
        await context.get_tools()
        filtered_tools = context.filter_tools() or None

    # 创建内层 graph (deep agent)
    checkpointer_start = time.time()
    inner_checkpointer = await get_async_checkpointer()
    checkpointer_init_time = time.time() - checkpointer_start
    logger.debug(f"[Agent] Checkpointer init: {checkpointer_init_time * 1000:.3f}ms")

    # 注意：不使用 SkillsMiddleware（skills=None）
    # SkillsStoreBackend 直接连接 MongoDB，LLM 可以通过 read_file/write_file 实时读写 skills
    # build_skills_prompt 只用于构建 skills 列表提示，告诉 LLM 有哪些 skills 可用

    # 创建 graph（带计时）
    graph_compile_start = time.time()

    # 自定义子代理配置 - 强制将所有中间信息保存到文件
    custom_subagents: list[SubAgent | CompiledSubAgent] = [
        {
            "name": "general-purpose",
            "description": "General-purpose agent for researching complex questions, searching for files and content, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you. This agent has access to all tools as the main agent.",
            "system_prompt": SUBAGENT_PROMPT,
        }
    ]

    inner_graph = create_deep_agent(
        model=llm,
        system_prompt=system_prompt,
        backend=backend_factory,
        tools=filtered_tools,
        checkpointer=inner_checkpointer,
        store=store,  # 传递 PostgresStore
        skills=None,  # 禁用 SkillsMiddleware，使用 build_skills_prompt 代替
        subagents=custom_subagents,
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

    # 从内层 graph 的 checkpoint 获取历史消息
    inner_state = await inner_graph.aget_state(inner_config)
    existing_messages = inner_state.values.get("messages", [])

    # 构建传入的消息列表（包含附件）
    user_input = state.get("input", "")
    new_message = _build_human_message(user_input, attachments)

    # 消息列表（记忆召回改为由 agent 通过 tool 主动触发）
    all_messages = existing_messages + [new_message]

    # 传递 messages
    inner_config["configurable"]["messages"] = existing_messages

    # 创建事件处理器（使用 AgentEventProcessor 处理 astream_events）
    logger.info("[SearchAgent] Creating AgentEventProcessor")
    event_processor = AgentEventProcessor(presenter)

    logger.info("[SearchAgent] Starting _run_with_retry (astream_events)")
    # 流式处理事件（带重试，使用 astream_events）
    await _run_with_retry(
        graph=inner_graph,
        input_data={
            "messages": all_messages,
        },
        config=inner_config,
        event_processor=event_processor,
    )

    # 发送 token 使用统计事件
    await _emit_token_usage(event_processor, presenter, start_time)

    # 获取内层 graph 的最终状态
    inner_state = await inner_graph.aget_state(inner_config)
    new_messages = inner_state.values.get("messages", [])

    final_messages = new_messages if len(new_messages) > len(all_messages) else all_messages

    # 自动记忆存储（异步，不阻塞响应）
    _schedule_auto_retain(user_input, event_processor.output_text, context.user_id)

    return {
        "output": event_processor.output_text,
        "messages": final_messages,
    }


async def _create_backend_and_prompt(
    state: Dict[str, Any],
    context: SearchAgentContext,
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

    # 构建记忆系统提示
    memory_guide = HINDSIGHT_MEMORY_SECTION if settings.ENABLE_MEMORY else EMPTY_MEMORY_SECTION

    # 创建 store（优先 PostgreSQL → MongoDB fallback）
    store = create_store()

    # 获取 user_id 用于 skills 读写
    user_id = context.user_id or "default"

    if not settings.ENABLE_SANDBOX:
        # 非沙箱模式：使用持久化 backend（PostgreSQL 或 MongoDB，由 store 决定）
        logger.info(f"Sandbox disabled, using PersistentBackend for assistant: {assistant_id}")
        backend_factory = create_persistent_backend_factory(assistant_id, user_id=user_id)
        return (
            backend_factory,
            DEFAULT_SYSTEM_PROMPT.replace("{skills}", skills_prompt).replace(
                "{memory_guide}", memory_guide
            ),
            store,
        )

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

        # 格式化沙箱提示词，注入 work_dir, skills 和 memory_guide
        system_prompt = (
            SANDBOX_SYSTEM_PROMPT.replace("{work_dir}", work_dir)
            .replace("{skills}", skills_prompt)
            .replace("{memory_guide}", memory_guide)
        )
        # sandbox_backend 是 CompositeBackend(default=DaytonaBackend)，需要提取出 DaytonaBackend
        return (
            create_sandbox_backend_factory(sandbox_backend.default, assistant_id, user_id=user_id),
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
    cache_creation_tokens = event_processor.total_cache_creation_tokens
    cache_read_tokens = event_processor.total_cache_read_tokens

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
                    cache_creation_tokens=cache_creation_tokens,
                    cache_read_tokens=cache_read_tokens,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to emit token:usage event: {e}")
