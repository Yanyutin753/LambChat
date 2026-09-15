"""响应 gzip 压缩接线。

历史事件等大 JSON 响应可达 20MB+，不压缩时下载 + JSON.parse 直接卡死
前端主线程。starlette GZipMiddleware 对流式响应用 Z_SYNC_FLUSH 逐块
冲刷，且默认排除 text/event-stream——SSE 的逐事件到达语义不受影响。
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.gzip import (
    DEFAULT_EXCLUDED_CONTENT_TYPES,
    GZipMiddleware,
)

# 在默认排除清单（SSE/图片/音视频/已压缩归档等）之上追加：
# 附件下载（upload/version 路由）多为已压缩二进制，gzip 纯耗 CPU
EXCLUDED_CONTENT_TYPES = (*DEFAULT_EXCLUDED_CONTENT_TYPES, "application/octet-stream")


def add_compression_middleware(app: FastAPI) -> None:
    """注册 gzip 压缩中间件（最后注册 = 最外层，压缩最终响应体）。"""
    app.add_middleware(
        GZipMiddleware,
        minimum_size=1024,
        compresslevel=6,
        exclude_content_types=EXCLUDED_CONTENT_TYPES,
    )
