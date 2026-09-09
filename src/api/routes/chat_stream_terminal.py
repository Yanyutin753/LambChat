"""chat 流式路由的终态合成助手（从 chat.py 拆出，守 1000 行守门）。

run 到终态后 Redis stream 会被 60s 终态 TTL 清掉；客户端再连
``/stream?run_id=`` 时重放 0 条事件且端点不查任务状态，只能挂着发 24h
心跳——断线重连的客户端在途工具卡因此永远转圈。stream 为空且 run 已终态
时用这里合成 done/error 终态事件立即返回。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.infra.logging import get_logger

logger = get_logger(__name__)


async def resolve_terminal_stream_status(session: Any, run_id: str) -> str | None:
    """终态 stream 过期后的 run 终态判定；非终态/查不到返回 None（维持现状）。

    优先按 run_id 查 trace（会话级 metadata 的 task_status 在多 run 并存时
    会串到别的 run）；trace 无记录时回落 session metadata，但仅当
    current_run_id 与请求的 run_id 一致才可信。
    """
    from src.infra.session.trace_storage import get_trace_storage

    try:
        cursor = (
            get_trace_storage()
            .collection.find({"run_id": run_id}, {"status": 1, "_id": 0})
            .sort("started_at", -1)
            .limit(1)
        )
        traces = await cursor.to_list(length=1)
        if traces:
            status = traces[0].get("status")
            if status in ("completed", "error"):
                return status
            return None  # running 等非终态：孤儿接管/续跑窗口期，继续等
    except Exception as e:  # noqa: BLE001 - 状态查询尽力而为，失败维持现状
        logger.warning("[SSE] Terminal status lookup via trace failed: %s", e)

    try:
        metadata = getattr(session, "metadata", None) or {}
        if metadata.get("current_run_id") == run_id:
            task_status = metadata.get("task_status")
            if task_status == "completed":
                return "completed"
            if task_status in ("error", "failed", "cancelled"):
                return "error"
    except Exception as e:  # noqa: BLE001 - 同上
        logger.warning("[SSE] Terminal status lookup via session metadata failed: %s", e)
    return None


def synthesize_terminal_stream_event(run_id: str, session: Any, terminal: str) -> dict:
    """合成终态 SSE 事件（stream 已过期、无法重放真实终态事件时的替身）。"""
    timestamp = datetime.now(timezone.utc).isoformat()
    if terminal == "completed":
        return {
            "event_type": "done",
            "data": {"status": "completed", "run_id": run_id},
            "id": f"synthetic:{run_id}:done",
            "timestamp": timestamp,
        }
    metadata = getattr(session, "metadata", None) or {}
    message = metadata.get("task_error") or "This run has already ended."
    return {
        "event_type": "error",
        "data": {
            "error": message,
            "type": "task_failed",
            "run_id": run_id,
            "code": "run_already_ended",
        },
        "id": f"synthetic:{run_id}:error",
        "timestamp": timestamp,
    }
