"""
Trace Context - 分布式追踪上下文

使用 contextvars 存储追踪信息，支持跨异步调用传递。
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass
class TraceInfo:
    """追踪信息数据类"""

    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None

    def is_set(self) -> bool:
        """检查是否设置了追踪信息"""
        return self.trace_id is not None

    def format(self) -> str:
        """格式化为日志字符串"""
        if not self.is_set():
            return "-"
        parts = [f"trace_id={self.trace_id}"]
        if self.span_id:
            parts.append(f"span_id={self.span_id}")
        return " ".join(parts)


@dataclass
class RequestContext:
    """请求上下文数据类"""

    session_id: Optional[str] = None
    run_id: Optional[str] = None
    user_id: Optional[str] = None


class TraceContext:
    """
    追踪上下文管理器

    使用 contextvars 存储追踪信息，支持跨异步调用传递。

    Usage:
        # 设置追踪上下文
        TraceContext.set(trace_id="abc123", span_id="def456")

        # 获取追踪信息
        info = TraceContext.get()

        # 清除追踪上下文
        TraceContext.clear()
    """

    _trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
    _span_id: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
    _parent_span_id: ContextVar[Optional[str]] = ContextVar("parent_span_id", default=None)

    # 请求上下文 - 用于工具等需要访问 session_id/run_id 的场景
    _session_id: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
    _run_id: ContextVar[Optional[str]] = ContextVar("run_id", default=None)
    _user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)

    @classmethod
    def set(
        cls,
        trace_id: str,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ) -> None:
        """
        设置追踪上下文

        Args:
            trace_id: 追踪 ID（跨请求唯一）
            span_id: 当前跨度 ID
            parent_span_id: 父跨度 ID（用于嵌套调用）
        """
        cls._trace_id.set(trace_id)
        cls._span_id.set(span_id)
        cls._parent_span_id.set(parent_span_id)

    @classmethod
    def get(cls) -> TraceInfo:
        """
        获取当前追踪信息

        Returns:
            TraceInfo 包含 trace_id, span_id, parent_span_id
        """
        return TraceInfo(
            trace_id=cls._trace_id.get(),
            span_id=cls._span_id.get(),
            parent_span_id=cls._parent_span_id.get(),
        )

    @classmethod
    def clear(cls) -> None:
        """清除追踪上下文"""
        cls._trace_id.set(None)
        cls._span_id.set(None)
        cls._parent_span_id.set(None)

    @classmethod
    def new_span(cls, span_id: str) -> str:
        """
        创建新的子跨度

        保存当前 span_id 为 parent_span_id，设置新的 span_id。

        Args:
            span_id: 新的跨度 ID

        Returns:
            之前的 span_id（可作为新的 parent_span_id）
        """
        old_span = cls._span_id.get()
        cls._parent_span_id.set(old_span)
        cls._span_id.set(span_id)
        return old_span or ""

    # ==================== 请求上下文方法 ====================

    @classmethod
    def set_request_context(
        cls,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """
        设置请求上下文

        用于在 Agent 执行期间传递 session_id、run_id 等信息给工具。

        Args:
            session_id: 会话 ID
            run_id: 运行 ID
            user_id: 用户 ID
        """
        if session_id is not None:
            cls._session_id.set(session_id)
        if run_id is not None:
            cls._run_id.set(run_id)
        if user_id is not None:
            cls._user_id.set(user_id)

    @classmethod
    def get_request_context(cls) -> RequestContext:
        """
        获取当前请求上下文

        Returns:
            RequestContext 包含 session_id, run_id, user_id
        """
        return RequestContext(
            session_id=cls._session_id.get(),
            run_id=cls._run_id.get(),
            user_id=cls._user_id.get(),
        )

    @classmethod
    def clear_request_context(cls) -> None:
        """清除请求上下文"""
        cls._session_id.set(None)
        cls._run_id.set(None)
        cls._user_id.set(None)

    @classmethod
    def get_session_id(cls) -> Optional[str]:
        """获取当前 session_id"""
        return cls._session_id.get()

    @classmethod
    def get_run_id(cls) -> Optional[str]:
        """获取当前 run_id"""
        return cls._run_id.get()

    @classmethod
    def get_user_id(cls) -> Optional[str]:
        """获取当前 user_id"""
        return cls._user_id.get()
