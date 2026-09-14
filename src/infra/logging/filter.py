"""
Trace Filter - 日志过滤器

自动将追踪上下文注入到日志记录中。
"""

from __future__ import annotations

import logging
import time
from typing import Protocol, cast

from src.infra.logging.context import TraceContext


class KeywordRateLimitFilter(logging.Filter):
    """Emit matching records at most once per window.

    Third-party clients can spam the same warning for every retry (LangSmith
    logged hundreds of "Rate limit exceeded" 429 warnings per task once the
    monthly quota ran out). The first matching record passes; further matches
    are dropped until the window elapses. Non-matching records are unaffected.
    """

    def __init__(self, keywords: tuple[str, ...], window_seconds: float = 600.0) -> None:
        super().__init__()
        self._keywords = keywords
        self._window_seconds = window_seconds
        self._last_emit: float = -window_seconds

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if not any(keyword in message for keyword in self._keywords):
            return True
        now = time.monotonic()
        if now - self._last_emit < self._window_seconds:
            return False
        self._last_emit = now
        return True


class _TraceLogRecord(Protocol):
    request_id: str
    trace_id: str
    span_id: str
    parent_span_id: str
    user_id: str
    session_id: str
    run_id: str
    trace_info: str
    trace_context: str


def _build_trace_context(parts: dict[str, str]) -> str:
    rendered = [f"{key}={value}" for key, value in parts.items() if value and value != "-"]
    return " ".join(rendered) + " " if rendered else ""


class TraceFilter(logging.Filter):
    """
    追踪日志过滤器

    自动从 TraceContext 获取追踪信息并注入到 LogRecord 中。

    注入的属性:
        - record.request_id: 请求 ID
        - record.trace_id: 追踪 ID
        - record.span_id: 跨度 ID
        - record.parent_span_id: 父跨度 ID
        - record.session_id: 会话 ID
        - record.run_id: 运行 ID
        - record.user_id: 用户 ID
        - record.trace_info: 格式化的追踪信息字符串

    Usage:
        handler = logging.StreamHandler()
        handler.addFilter(TraceFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        注入追踪上下文到日志记录

        Args:
            record: 日志记录对象

        Returns:
            总是返回 True（允许所有记录通过）
        """
        info = TraceContext.get()
        request_context = TraceContext.get_request_context()
        trace_record = cast(_TraceLogRecord, record)

        # 注入追踪属性
        trace_record.request_id = info.request_id or request_context.request_id or "-"
        trace_record.trace_id = info.trace_id or request_context.trace_id or "-"
        trace_record.span_id = info.span_id or "-"
        trace_record.parent_span_id = info.parent_span_id or "-"
        trace_record.session_id = request_context.session_id or "-"
        trace_record.run_id = request_context.run_id or "-"
        trace_record.user_id = request_context.user_id or "-"
        trace_record.trace_info = info.format()
        trace_record.trace_context = _build_trace_context(
            {
                "request_id": trace_record.request_id,
                "trace_id": trace_record.trace_id,
                "span_id": trace_record.span_id,
                "user_id": trace_record.user_id,
                "session_id": trace_record.session_id,
                "run_id": trace_record.run_id,
            }
        )

        return True
