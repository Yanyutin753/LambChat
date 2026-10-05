"""渠道投递文本提取（定时任务与任务完成通知共用）。

从 trace 事件流中提取 assistant 输出文本：message:chunk 就近拼接、
非 chunk 的 assistant 消息独立成段，user 事件全部跳过。
"""

from typing import Any

_ASSISTANT_EVENT_TYPES = {
    "message",
    "assistant:message",
    "ai:message",
    "assistant",
    "ai",
    "content",
    "message:chunk",
    "summary",
}
_ASSISTANT_ROLES = {"assistant", "ai"}

DEFAULT_MAX_DELIVERY_CHARS = 4000


def extract_delivery_text(
    events: list[dict[str, Any]],
    max_chars: int = DEFAULT_MAX_DELIVERY_CHARS,
) -> str:
    """Extract assistant text from trace events for channel delivery."""
    parts: list[str] = []
    chunk_parts: list[str] = []

    def flush_chunks() -> None:
        if not chunk_parts:
            return
        chunk_text = "".join(chunk_parts).strip()
        if chunk_text:
            parts.append(chunk_text)
        chunk_parts.clear()

    for event in events:
        event_type = str(event.get("event_type") or "")
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        role = str(data.get("role") or "").lower()
        if role in {"user", "human"}:
            continue
        if event_type == "message" and role not in _ASSISTANT_ROLES:
            continue
        if event_type not in _ASSISTANT_EVENT_TYPES and role not in _ASSISTANT_ROLES:
            continue

        content = data.get("content")
        if content is None:
            content = data.get("message")
        if not isinstance(content, str) or not content.strip():
            continue

        if event_type == "message:chunk":
            chunk_parts.append(content)
        else:
            flush_chunks()
            parts.append(content.strip())

    flush_chunks()
    text = "\n".join(parts).strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip()
    return text
