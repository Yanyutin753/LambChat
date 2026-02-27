"""
追踪中间件
"""

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.infra.logging import TraceContext


class TracingMiddleware(BaseHTTPMiddleware):
    """
    追踪中间件

    为每个请求添加追踪 ID 和计时。
    自动将追踪上下文注入到日志中。
    """

    async def dispatch(self, request: Request, call_next):
        # 从请求头获取或生成 trace_id（支持分布式追踪）
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())[:16]
        span_id = str(uuid.uuid4())[:8]

        # 设置追踪上下文
        TraceContext.set(trace_id=trace_id, span_id=span_id)
        request.state.trace_id = trace_id
        request.state.span_id = span_id

        # 记录开始时间
        start_time = time.time()

        try:
            # 处理请求
            response = await call_next(request)
        finally:
            # 清除追踪上下文
            TraceContext.clear()

        # 计算处理时间
        process_time = time.time() - start_time

        # 添加响应头
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Span-ID"] = span_id
        response.headers["X-Process-Time"] = f"{process_time:.3f}s"

        return response
