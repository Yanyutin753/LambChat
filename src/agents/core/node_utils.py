"""
Agent 节点共享工具函数

从 search_agent/nodes.py 和 fast_agent/nodes.py 中提取的公共逻辑。
"""

import asyncio

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.infra.agent import AgentEventProcessor
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)


def schedule_auto_retain(
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

    user_input_clean = user_input.strip()
    if not user_input_clean or len(user_input_clean) < 10:
        return

    from src.infra.memory.tools import schedule_auto_retain

    schedule_auto_retain(
        user_id=user_id,
        conversation_summary=user_input_clean[:500],
        context="user_query",
    )


def build_human_message(text: str, attachments: list[dict] | None) -> HumanMessage:
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
    if not attachments:
        return HumanMessage(content=text)

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


def is_retryable_error(error: Exception) -> bool:
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


async def run_with_retry(
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
            async for event in graph.astream_events(
                input_data,
                config,
                version="v2",
            ):
                await event_processor.process_event(event)
            # Flush any remaining buffered chunks
            await event_processor._flush_chunk_buffer()
            return
        except Exception as e:
            last_error = e
            # Flush any buffered chunks before retrying (avoid data loss)
            await event_processor._flush_chunk_buffer()
            if is_retryable_error(e) and attempt < max_retries - 1:
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


async def emit_token_usage(
    event_processor: AgentEventProcessor,
    presenter,
    start_time: float,
) -> None:
    """发送 token 使用统计事件"""
    import time

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
