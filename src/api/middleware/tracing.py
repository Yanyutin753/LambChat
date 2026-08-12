"""
追踪中间件
"""

import logging
import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.server_timing import (
    begin_server_timing_request,
    reset_server_timing_request,
    serialize_server_timing,
)
from src.infra.logging import TraceContext

logger = logging.getLogger(__name__)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _make_request_id(raw_request_id: str | None) -> str:
    if raw_request_id and REQUEST_ID_PATTERN.fullmatch(raw_request_id):
        return raw_request_id
    return uuid.uuid4().hex


def _current_log_context(request: Request | None = None) -> dict[str, str]:
    info = TraceContext.get()
    request_context = TraceContext.get_request_context()
    return {
        "request_id": info.request_id or request_context.request_id or "-",
        "trace_id": info.trace_id or request_context.trace_id or "-",
        "span_id": info.span_id or "-",
        "parent_span_id": info.parent_span_id or "-",
        "session_id": request_context.session_id
        or (getattr(request.state, "logging_session_id", None) if request else None)
        or "-",
        "run_id": request_context.run_id or "-",
        "user_id": request_context.user_id
        or (getattr(request.state, "logging_user_id", None) if request else None)
        or "-",
    }


class TracingMiddleware(BaseHTTPMiddleware):
    """
    追踪中间件

    为每个请求添加追踪 ID 和计时。
    自动将追踪上下文注入到日志中。
    """

    async def dispatch(self, request: Request, call_next):
        # request_id 用于单次 HTTP 请求日志关联；trace_id 保留分布式追踪语义。
        request_id = _make_request_id(request.headers.get("X-Request-ID"))
        # 从请求头获取或生成 trace_id（支持分布式追踪）
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())[:16]
        span_id = str(uuid.uuid4())[:8]

        # 设置追踪上下文
        TraceContext.set(trace_id=trace_id, span_id=span_id, request_id=request_id)
        TraceContext.set_request_context(request_id=request_id, trace_id=trace_id)
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        request.state.span_id = span_id
        server_timing_token = begin_server_timing_request()

        # 记录开始时间
        start_time = time.time()

        try:
            # 处理请求
            response = await call_next(request)
        except Exception:
            process_time = time.time() - start_time
            client_host = request.client.host if request.client else "-"
            logger.exception(
                "http_request_failed method=%s path=%s status_code=500 duration_ms=%.2f client=%s",
                request.method,
                request.url.path,
                process_time * 1000,
                client_host,
                extra=_current_log_context(request),
            )
            raise
        else:
            # 计算处理时间
            process_time = time.time() - start_time
            status_code = getattr(response, "status_code", 0)
            client_host = request.client.host if request.client else "-"

            logger.info(
                "http_request_completed method=%s path=%s status_code=%s duration_ms=%.2f client=%s",
                request.method,
                request.url.path,
                status_code,
                process_time * 1000,
                client_host,
                extra=_current_log_context(request),
            )

            # 添加响应头
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Span-ID"] = span_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}s"
            server_timing = serialize_server_timing()
            if server_timing:
                response.headers["Server-Timing"] = server_timing

            return response
        finally:
            # 完成/失败日志需要在清理前写出，才能带上 request_id。
            TraceContext.clear_request_context()
            TraceContext.clear()
            reset_server_timing_request(server_timing_token)
