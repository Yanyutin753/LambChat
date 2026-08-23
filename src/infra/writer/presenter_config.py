"""Presenter 配置与工具函数"""

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.infra.utils.datetime import utc_now

ATTACHMENT_KEYS_MAX = 100


def should_increment_unread_for_trace_status(status: str) -> bool:
    """Return whether a trace terminal status should require user attention."""
    return status in {"completed", "error"}


def _extract_attachment_keys(
    attachments: Optional[List[Dict[str, Any]]],
    *,
    limit: int | None = ATTACHMENT_KEYS_MAX,
) -> list[str]:
    """Extract unique storage keys from attachment payloads."""
    if not attachments:
        return []
    keys: list[str] = []
    seen = set()
    for attachment in attachments:
        key = str(attachment.get("key", "")).strip() if attachment.get("key") else ""
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
        if limit is not None and len(keys) >= limit:
            break
    return keys


def _bounded_attachments(
    attachments: Optional[List[Dict[str, Any]]],
    *,
    limit: int = ATTACHMENT_KEYS_MAX,
) -> list[Dict[str, Any]]:
    if not attachments:
        return []
    return list(attachments[:limit])


def _generate_trace_id() -> str:
    """生成唯一 trace_id (时间戳 + 完整 UUID，确保不重复)"""
    ts = utc_now().strftime("%Y%m%d%H%M%S%f")
    return f"trace_{ts}_{uuid.uuid4().hex}"


def _generate_run_id() -> str:
    """生成唯一 run_id (时间戳 + 完整 UUID，用于 LangSmith 关联)"""
    ts = utc_now().strftime("%Y%m%d%H%M%S%f")
    return f"run_{ts}_{uuid.uuid4().hex}"


@dataclass
class PresenterConfig:
    """Presenter 配置"""

    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_name: str = "Agent"
    user_id: Optional[str] = None  # 用户 ID，用于绑定 session
    run_id: Optional[str] = None  # 运行 ID
    trace_id: Optional[str] = None  # Trace ID (自动生成或手动指定)
    chunk_delay: float = 0.0  # 流式输出延迟 (秒)
    max_result_length: int = 100000  # 结果最大长度
    enable_storage: bool = True  # 是否启用事件存储
    model_id: Optional[str] = None  # 本次运行使用的模型配置 ID（失败时 usage 日志仍可归属模型）
    model: Optional[str] = None  # 本次运行使用的模型值
