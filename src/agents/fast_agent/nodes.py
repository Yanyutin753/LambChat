"""
Fast Agent 节点 - 无沙箱，快速响应

基于 deep_agent/nodes.py 简化，移除沙箱相关逻辑。
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.core.base import get_presenter
from src.agents.fast_agent.context import FastAgentContext
from src.agents.fast_agent.prompt import FAST_SYSTEM_PROMPT
from src.infra.agent import AgentEventProcessor
from src.infra.backend.deepagent import create_memory_backend_factory
from src.infra.llm.client import LLMClient
from src.infra.skill.loader import build_skills_prompt
from src.infra.storage.checkpoint import get_async_checkpointer
from src.kernel.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# 消息构建工具
# ============================================================================


def _build_human_message(text: str, attachments: list[dict] | None) -> HumanMessage:
    """
    构建 HumanMessage，将附件信息以文本形式附加到消息中
    """
    if not attachments:
        return HumanMessage(content=text)

    enhanced_text = text
    enhanced_text += "\n\n---\n**用户上传的附件:**"

    for attachment in attachments:
        url = attachment.get("url", "")
        name = attachment.get("name", "未知文件")
        file_type = attachment.get("type", "document")
        mime_type = attachment.get("mime_type", "")
        size = attachment.get("size", 0)

        if not url:
            continue

        size_str = ""
        if size:
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"

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
        "429",
        "503",
        "502",
        "504",
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
    event_processor: "AgentEventProcessor",
    max_retries: int | None = None,
    base_delay: float = 1.0,
) -> None:
    """带重试的 LLM 流式执行"""
    if max_retries is None:
        max_retries = getattr(settings, "LLM_MAX_RETRIES", 3)

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async for event in graph.astream_events(input_data, config, version="v2"):
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

    # 构建 skills 提示
    skills_prompt = ""
    if settings.ENABLE_SKILLS and context.skills:
        try:
            skills_prompt = await build_skills_prompt(context.skills)
        except Exception as e:
            logger.warning(f"Failed to build skills prompt: {e}")

    # 构建系统提示
    system_prompt = FAST_SYSTEM_PROMPT.replace("{skills}", skills_prompt)

    # 使用内存 backend（无沙箱）
    backend_factory = create_memory_backend_factory(assistant_id)
    logger.info(f"[FastAgent] Using in-memory backend for assistant: {assistant_id}")

    # 过滤工具
    filtered_tools = None
    if settings.ENABLE_MCP:
        filtered_tools = context.filter_tools()

    # 创建内层 graph (deep agent)
    inner_checkpointer = await get_async_checkpointer()

    inner_graph = create_deep_agent(
        model=llm,
        system_prompt=system_prompt,
        backend=backend_factory,
        tools=filtered_tools if filtered_tools else None,
        checkpointer=inner_checkpointer,
        store=None,  # Fast Agent 不使用长期存储
        skills=None,
    ).with_config({"recursion_limit": settings.SESSION_MAX_RUNS_PER_SESSION})

    inner_config: RunnableConfig = {
        "configurable": {
            "thread_id": state.get("session_id", str(uuid.uuid4())),
            "backend": backend_factory,
            "context": context,
            "base_url": configurable.get("base_url", ""),
        },
        "recursion_limit": config.get("recursion_limit", settings.SESSION_MAX_RUNS_PER_SESSION),
    }

    # 从内层 graph 的 checkpoint 获取历史消息
    inner_state = await inner_graph.aget_state(inner_config)
    existing_messages = inner_state.values.get("messages", [])

    # 构建传入的消息列表（包含附件）
    new_message = _build_human_message(state.get("input", ""), attachments)
    all_messages = existing_messages + [new_message]

    # 传递 messages
    inner_config["configurable"]["messages"] = existing_messages

    # 创建事件处理器
    event_processor = AgentEventProcessor(presenter)

    # 流式处理事件（带重试）
    await _run_with_retry(
        graph=inner_graph,
        input_data={
            "messages": all_messages,
            "files": context.skill_files,
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

    return {
        "output": event_processor.output_text,
        "messages": final_messages,
    }


async def _emit_token_usage(
    event_processor: AgentEventProcessor,
    presenter,
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
