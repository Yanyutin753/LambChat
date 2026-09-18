"""
追踪中间件
"""

import logging
import re
import time
import uuid

from fastapi import Request
from starlette.datastructures import MutableHeaders

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


class TracingMiddleware:
    """
    追踪中间件

    为每个请求添加追踪 ID 和计时。
    自动将追踪上下文注入到日志中。

    纯 ASGI 实现（避免基类中间件每请求的 task 与流拷贝开销），
    通过包装 send 在 http.response.start 上注入响应头。
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
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
        status_code_holder: list[int] = []
        # 首字节时间（响应头写出时刻）：成功日志的 duration 语义与基类中间件版
        # 基类中间件版一致（≈TTFB），不随流式 body 拖长
        ttfb_holder: list[float] = []

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                status_code_holder.append(message["status"])
                process_time = time.time() - start_time
                ttfb_holder.append(process_time)
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Trace-ID"] = trace_id
                headers["X-Span-ID"] = span_id
                headers["X-Process-Time"] = f"{process_time:.3f}s"
                server_timing = serialize_server_timing()
                if server_timing:
                    headers["Server-Timing"] = server_timing
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
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
            # 计算处理时间：用首字节时刻（长连 SSE 的 body 流不拖长该值）
            process_time = ttfb_holder[0] if ttfb_holder else time.time() - start_time
            status_code = status_code_holder[0] if status_code_holder else 0
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
        finally:
            # 完成/失败日志需要在清理前写出，才能带上 request_id。
            TraceContext.clear_request_context()
            TraceContext.clear()
            reset_server_timing_request(server_timing_token)
