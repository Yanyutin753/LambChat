"""全量历史响应的预渲染卸载。

FastAPI 对返回 dict 的 jsonable_encoder+json.dumps 跑在事件循环上，长会话
全量事件可达 20MB+，单请求内联可达数百 ms；gzip 侧 starlette GZipMiddleware
（≥128KiB）已自带线程卸载，这里补齐序列化这半。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from itertools import chain
from typing import Any

from fastapi import Response
from fastapi.encoders import jsonable_encoder

from src.infra.async_utils import run_long_blocking_io
from src.infra.session.history_compaction import compact_history_events

# 超过该事件数的响应预渲染卸载到慢道；小响应保持 dict 走 FastAPI 常规路径
HISTORY_JSON_OFFLOAD_EVENT_COUNT = 500
HISTORY_JSON_OFFLOAD_CONTENT_CHARS = 128 * 1024
HISTORY_JSON_OFFLOAD_VALUE_COUNT = 5000


def _large_history_payload(events: list[dict[str, Any]], threshold: int) -> bool:
    if len(events) >= threshold:
        return True
    # Bound the inspection itself, including nested tool results and attachments.
    stack: list[Iterator[Any]] = [iter(events)]
    content_chars = 0
    values = 0
    while stack:
        try:
            value = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        values += 1
        if values >= HISTORY_JSON_OFFLOAD_VALUE_COUNT:
            return True
        if isinstance(value, str):
            content_chars += len(value)
            if content_chars >= HISTORY_JSON_OFFLOAD_CONTENT_CHARS:
                return True
        elif isinstance(value, dict):
            stack.append(iter(chain(value.keys(), value.values())))
        elif isinstance(value, (list, tuple)):
            stack.append(iter(value))
    return False


async def prepare_history_events(
    events: list[dict[str, Any]],
    compact: bool,
    threshold: int = HISTORY_JSON_OFFLOAD_EVENT_COUNT,
) -> tuple[list[dict[str, Any]], bool]:
    """Keep the raw history size decision even after compaction reduces event count."""
    offload = _large_history_payload(events, threshold)
    if compact:
        events = (
            await run_long_blocking_io(compact_history_events, events)
            if offload
            else compact_history_events(events)
        )
    return events, offload


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


def parse_event_types_filter(event_types: str | None, limit: int = 100) -> list[str] | None:
    if not event_types:
        return None
    parsed: list[str] = []
    seen = set()
    for raw_type in event_types.split(","):
        event_type = raw_type.strip()
        if not event_type or event_type in seen:
            continue
        seen.add(event_type)
        parsed.append(event_type)
        if len(parsed) >= limit:
            break
    return parsed or None
