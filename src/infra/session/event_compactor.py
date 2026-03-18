"""
Event Compactor - 合并 trace 内的流式事件以减少存储和查询开销

后台扫描已完成(status != running)的 traces，将每个 trace 内部连续的流式事件
（如 message:chunk、thinking）合并为完整的事件，过滤 heartbeat 冗余事件，
然后更新回原 trace 文档。

使用 Redis 分布式锁防止多实例重复处理。
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.infra.logging import get_logger
from src.infra.session.trace_storage import get_trace_storage
from src.infra.storage.redis import get_redis_client

logger = get_logger(__name__)

# Redis 分布式锁配置
_COMPACTOR_LOCK_KEY = "event_compactor:lock"
_COMPACTOR_LOCK_TTL = 300  # 5 分钟锁超时

# 扫描配置
_BATCH_SIZE = 100  # 每批处理的 trace 数量
_SCAN_INTERVAL = 300  # 扫描间隔（秒）

# 需要排除的事件类型（只排除心跳）
_EXCLUDED_EVENT_TYPES = frozenset({"heartbeat"})

# 支持流式合并的事件类型（data.content 是文本片段，需要拼接）
_STREAM_EVENT_TYPES = frozenset({"message:chunk", "thinking"})

# 合并后的最小事件数缩减比例（低于此比例不值得合并）
_MIN_REDUCTION_RATIO = 0.2  # 至少减少 20% 的事件数


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _acquire_lock() -> bool:
    """获取 Redis 分布式锁"""
    redis = get_redis_client()
    return await redis.set(
        _COMPACTOR_LOCK_KEY,
        "1",
        nx=True,
        ex=_COMPACTOR_LOCK_TTL,
    )


async def _release_lock() -> None:
    """释放 Redis 分布式锁"""
    redis = get_redis_client()
    await redis.delete(_COMPACTOR_LOCK_KEY)


async def _refresh_lock() -> None:
    """刷新锁的 TTL（长时间运行时续期）"""
    redis = get_redis_client()
    await redis.expire(_COMPACTOR_LOCK_KEY, _COMPACTOR_LOCK_TTL)


def _get_merge_key(event_type: str, data: Dict[str, Any]) -> Optional[str]:
    """
    获取事件的合并分组 key

    - thinking: 按 thinking_id 分组（同一个 thinking 块）
    - message:chunk: 按连续性分组（相邻的 chunk 合并）
    - 其他: 不合并
    """
    if event_type == "thinking":
        thinking_id = data.get("thinking_id")
        return f"thinking:{thinking_id}" if thinking_id else None
    elif event_type == "message:chunk":
        return "message:chunk"
    return None


def _merge_consecutive_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    合并连续的流式事件

    规则:
    - 连续的 message:chunk 事件合并为一条（content 拼接）
    - 相同 thinking_id 的连续 thinking 事件合并为一条（content 拼接）
    - 其他事件类型断开合并
    """
    if not events:
        return events

    result: List[Dict[str, Any]] = []
    current_event: Optional[Dict[str, Any]] = None
    current_key: Optional[str] = None

    for event in events:
        event_type = event.get("event_type", "")
        data = event.get("data", {}) or {}

        if event_type not in _STREAM_EVENT_TYPES:
            current_event = None
            current_key = None
            result.append(event)
            continue

        merge_key = _get_merge_key(event_type, data)

        if merge_key is None:
            current_event = None
            current_key = None
            result.append(event)
            continue

        if current_event is not None and current_key == merge_key:
            current_data = current_event.get("data", {})
            current_data["content"] = current_data.get("content", "") + data.get("content", "")
            if event.get("timestamp"):
                current_event["timestamp"] = event["timestamp"]
        else:
            if current_event is not None:
                result.append(current_event)
            current_event = {
                "event_type": event_type,
                "data": dict(data),
                "timestamp": event.get("timestamp"),
                "run_id": event.get("run_id"),
                "trace_id": event.get("trace_id"),
            }
            current_key = merge_key

    if current_event is not None:
        result.append(current_event)

    return result


def _compact_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    压缩事件列表

    1. 过滤 heartbeat 事件
    2. 合并连续的流式事件
    """
    filtered = [e for e in events if e.get("event_type") not in _EXCLUDED_EVENT_TYPES]

    if not filtered:
        return filtered

    return _merge_consecutive_events(filtered)


async def _get_traces_needing_compaction() -> List[Dict[str, Any]]:
    """
    查找需要 compact 的 trace 列表

    条件: 已完成(status != running) 且 未被压缩过的
    """
    storage = get_trace_storage()

    match_query: Dict[str, Any] = {
        "status": {"$ne": "running"},
        "compact": {"$ne": True},
    }

    try:
        cursor = (
            storage.collection.find(match_query, {"_id": 1, "trace_id": 1, "event_count": 1})
            .sort("completed_at", 1)
            .limit(_BATCH_SIZE)
        )
        return await cursor.to_list(length=_BATCH_SIZE)
    except Exception as e:
        logger.error(f"Failed to find traces needing compaction: {e}")
        return []


async def _compact_trace(trace_info: Dict[str, Any]) -> bool:
    """
    压缩单个 trace 内的流式事件

    1. 获取完整 trace（含 events）
    2. 合并连续的 message:chunk / thinking 事件
    3. 过滤 heartbeat 事件
    4. 更新回原 trace 文档
    """
    storage = get_trace_storage()
    trace_id = trace_info.get("trace_id", "")
    original_count = trace_info.get("event_count", 0)

    if not trace_id or original_count < 5:
        return False

    trace = await storage.get_trace(trace_id)
    if not trace:
        return False

    events = trace.get("events", [])
    if not events:
        return False

    compacted_events = _compact_events(events)
    new_count = len(compacted_events)

    reduction = original_count - new_count
    if reduction < max(2, original_count * _MIN_REDUCTION_RATIO):
        try:
            await storage.collection.update_one(
                {"trace_id": trace_id},
                {"$set": {"compact": True, "updated_at": _utc_now()}},
            )
        except Exception:
            pass
        return False

    run_id = trace.get("run_id", "")
    for event in compacted_events:
        if "run_id" not in event or not event.get("run_id"):
            event["run_id"] = run_id

    try:
        await storage.collection.update_one(
            {"trace_id": trace_id},
            {
                "$set": {
                    "events": compacted_events,
                    "event_count": new_count,
                    "compact": True,
                    "updated_at": _utc_now(),
                    "metadata.compacted": {
                        "original_event_count": original_count,
                        "compacted_event_count": new_count,
                        "compacted_at": _utc_now().isoformat(),
                        "reduction": reduction,
                    },
                }
            },
        )

        logger.info(
            f"Compacted trace {trace_id}: "
            f"{original_count} -> {new_count} events (reduced {reduction})"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to compact trace {trace_id}: {e}")
        return False


async def run_compaction() -> int:
    """
    执行一次事件合并

    Returns:
        成功压缩的 trace 数量
    """
    if not await _acquire_lock():
        logger.debug("Compaction already running, skipping")
        return 0

    try:
        traces = await _get_traces_needing_compaction()
        if not traces:
            logger.debug("No traces need compaction")
            return 0

        logger.info(f"Found {len(traces)} traces to compact")
        compacted = 0

        for i, trace_info in enumerate(traces):
            try:
                if await _compact_trace(trace_info):
                    compacted += 1

                if (i + 1) % 10 == 0:
                    await _refresh_lock()
            except Exception as e:
                logger.error(f"Error compacting trace {trace_info.get('trace_id')}: {e}")
                continue

        logger.info(f"Compaction completed: {compacted}/{len(traces)} traces")
        return compacted
    except Exception as e:
        logger.error(f"Compaction failed: {e}")
        return 0
    finally:
        await _release_lock()


async def start_compaction_loop() -> None:
    """启动后台定期合并循环"""
    logger.info(f"Event compaction loop started (interval={_SCAN_INTERVAL}s)")

    while True:
        try:
            await asyncio.sleep(_SCAN_INTERVAL)
            await run_compaction()
        except asyncio.CancelledError:
            logger.info("Event compaction loop stopped")
            break
        except Exception as e:
            logger.error(f"Compaction loop error: {e}")
            await asyncio.sleep(60)
