"""
Agent 节点共享工具函数

从 search_agent/nodes.py 和 fast_agent/nodes.py 中提取的公共逻辑。
"""

from langchain_core.messages import HumanMessage

from src.infra.agent import AgentEventProcessor
from src.infra.logging import get_logger

logger = get_logger(__name__)


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
