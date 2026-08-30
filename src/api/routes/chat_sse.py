"""chat 路由的 SSE 事件序列化工具（从 chat.py 提取的纯函数）。"""

from __future__ import annotations

import json

CHAT_SSE_DATA_MAX_BYTES = 256 * 1024


def _estimated_json_data_bytes(data: object) -> int:
    if data is None or isinstance(data, (bool, int, float)):
        return len(json.dumps(data, default=str).encode("utf-8"))
    if isinstance(data, str):
        return len(data.encode("utf-8")) + 2
    if isinstance(data, dict):
        total = 2
        for index, (key, value) in enumerate(data.items()):
            if index:
                total += 1
            total += len(str(key).encode("utf-8")) + 3
            total += _estimated_json_data_bytes(value)
        return total
    if isinstance(data, (list, tuple)):
        total = 2
        for index, item in enumerate(data):
            if index:
                total += 1
            total += _estimated_json_data_bytes(item)
        return total
    return len(str(data).encode("utf-8")) + 2


def _chat_sse_payload_too_large_event(event_id: object | None) -> str:
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    # 标准错误事件形状：error 为原文、code 为稳定错误码
    payload = json.dumps(
        {"error": "event_payload_too_large", "code": "event_payload_too_large"},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"event: error\ndata: {payload}\n{id_line}\n"


def _json_dumps_chat_sse_data_limited(data: object) -> str | None:
    if _estimated_json_data_bytes(data) > CHAT_SSE_DATA_MAX_BYTES:
        return None

    encoder = json.JSONEncoder(ensure_ascii=False, default=str)
    chunks: list[str] = []
    total = 0
    for chunk in encoder.iterencode(data):
        total += len(chunk.encode("utf-8"))
        if total > CHAT_SSE_DATA_MAX_BYTES:
            return None
        chunks.append(chunk)
    return "".join(chunks)


def _format_sse_event(event: dict) -> str:
    event_data = event["data"]
    if isinstance(event_data, dict) and event.get("timestamp"):
        event_data = {**event_data, "_timestamp": event["timestamp"]}
    data_str = _json_dumps_chat_sse_data_limited(event_data)
    if data_str is None:
        return _chat_sse_payload_too_large_event(event.get("id"))
    return f"event: {event['event_type']}\ndata: {data_str}\nid: {event['id']}\n\n"
