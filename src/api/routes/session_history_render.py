"""全量历史响应的预渲染卸载。

FastAPI 对返回 dict 的 jsonable_encoder+json.dumps 跑在事件循环上，长会话
全量事件可达 20MB+，单请求内联可达数百 ms；gzip 侧 starlette GZipMiddleware
（≥128KiB）已自带线程卸载，这里补齐序列化这半。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Response
from fastapi.encoders import jsonable_encoder

from src.infra.async_utils import run_long_blocking_io

# 超过该事件数的响应预渲染卸载到慢道；小响应保持 dict 走 FastAPI 常规路径
HISTORY_JSON_OFFLOAD_EVENT_COUNT = 500


def _render_history_json_bytes(payload: dict[str, Any]) -> bytes:
    """与 FastAPI JSONResponse 渲染语义一致：jsonable_encoder → 紧凑 dumps。"""
    return json.dumps(
        jsonable_encoder(payload),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


async def render_history_response_offloaded(payload: dict[str, Any]) -> Response:
    body = await run_long_blocking_io(_render_history_json_bytes, payload)
    return Response(content=body, media_type="application/json")
