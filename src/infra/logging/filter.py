"""
Trace Filter - 日志过滤器

自动将追踪上下文注入到日志记录中。
"""

from __future__ import annotations

import logging

from src.infra.logging.context import TraceContext


class TraceFilter(logging.Filter):
    """
    追踪日志过滤器

    自动从 TraceContext 获取追踪信息并注入到 LogRecord 中。

    注入的属性:
        - record.trace_id: 追踪 ID
        - record.span_id: 跨度 ID
        - record.parent_span_id: 父跨度 ID
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

        # 注入追踪属性
        record.trace_id = info.trace_id or "-"
        record.span_id = info.span_id or "-"
        record.parent_span_id = info.parent_span_id or "-"
        record.trace_info = info.format()

        return True
