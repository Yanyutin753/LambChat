"""
Agent 节点共享工具函数

从 search_agent/nodes.py 和 fast_agent/nodes.py 中提取的公共逻辑。
"""

from langchain_core.messages import HumanMessage

from src.infra.agent import AgentEventProcessor
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# Patterns matching the standard assistant greeting boilerplate that should
# be stripped before sending to LLM memory extraction, since it repeats
# in every conversation and contains no user-specific information.
_ASSISTANT_BOILERPLATE_PATTERNS = (
    "我是 Deep Agent，一个 AI 助手",
    "我是 Deep Agent, an AI assistant",
    "我是 AI 助手",
)


def _strip_assistant_boilerplate(text: str) -> str:
    """Remove standard assistant greeting boilerplate from assistant output.

    Keeps only the substantive part of the response that contains
    actual information exchange with the user.
    """
    for pattern in _ASSISTANT_BOILERPLATE_PATTERNS:
        idx = text.find(pattern)
        if idx != -1:
            # Keep everything after the boilerplate (the real answer)
            after = text[idx + len(pattern) :]
            # Skip past common separators (newline, colon, etc.)
            for sep in ("\n", "。", "！", "!", "，", ",", ":", ":"):
                if after.startswith(sep):
                    after = after[len(sep) :]
                    break
            text = after.strip()
            if not text:
                # Nothing meaningful after boilerplate
                return ""
            break
    return text


def schedule_auto_retain(
    user_input: str,
    assistant_output: str,
    user_id: str | None,
    session_id: str | None = None,
) -> None:
    """
    调度自动记忆存储任务（异步，不阻塞响应）。

    组合用户输入和助手回复作为对话摘要，传递给记忆后端进行自动存储。
    统一接口自动选择 Hindsight 或 memU 后端。
    """
    if not settings.ENABLE_MEMORY or not user_id:
        return

    user_input_clean = user_input.strip()
    if not user_input_clean or len(user_input_clean) < 2:
        return

    # Combine user input + assistant output for richer context
    parts = [user_input_clean[:500]]
    if assistant_output and assistant_output.strip():
        # Strip standard assistant greeting boilerplate to reduce noise for LLM extraction.
        # The template "你好{name}！我是 Deep Agent，一个 AI 助手。" is repeated in every
        # conversation and contains no user-specific information worth remembering.
        cleaned_output = _strip_assistant_boilerplate(assistant_output.strip())
        if cleaned_output:
            parts.append(cleaned_output[:500])
    conversation_summary = "\n\n".join(parts)

    if len(conversation_summary.strip()) < 5:
        return

    from src.infra.memory.tools import schedule_auto_retain

    schedule_auto_retain(
        user_id=user_id,
        conversation_summary=conversation_summary,
        context="conversation_turn",
        session_id=session_id,
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
