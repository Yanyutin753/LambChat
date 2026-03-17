"""
Event Compactor - 合并已完成 run 的事件以减少存储和查询开销

后台扫描已完成(status != running)的 traces，将同一 session 的多个已完成 runs
合并到一个 archived trace 中，移除冗余 metadata 事件，只保留内容事件。

使用 Redis 分布式锁防止多实例重复处理。
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.infra.logging import get_logger
from src.infra.session.trace_storage import get_trace_storage
from src.infra.storage.redis import get_redis_client

logger = get_logger(__name__)

# Redis 分布式锁配置
_COMPACTOR_LOCK_KEY = "event_compactor:lock"
_COMPACTOR_LOCK_TTL = 300  # 5 分钟锁超时

# 扫描配置
_BATCH_SIZE = 50  # 每批处理的 session 数量
_SCAN_INTERVAL = 300  # 扫描间隔（秒）

# 需要排除的 metadata 类型事件（保留内容事件）
_METADATA_EVENT_TYPES = frozenset({"metadata", "token:usage", "heartbeat"})

# 需要 compact 的最小 run 数量（低于此数量不合并）
_MIN_RUNS_TO_COMPACT = 2


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


def _filter_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """过滤掉 metadata 类型事件，只保留内容事件"""
    return [e for e in events if e.get("event_type") not in _METADATA_EVENT_TYPES]


async def _get_sessions_needing_compaction() -> List[str]:
    """
    查找需要 compact 的 session 列表

    条件: 同一 session 有 >= _MIN_RUNS_TO_COMPACT 个已完成的非 archived traces
    """
    storage = get_trace_storage()

    # 使用聚合管道找出有多个已完成 traces 的 session
    pipeline: List[Dict[str, Any]] = [
        {
            "$match": {
                "status": {"$ne": "running"},
                "archived": {"$ne": True},
            }
        },
        {
            "$group": {
                "_id": "$session_id",
                "count": {"$sum": 1},
                "earliest_run": {"$min": "$started_at"},
            }
        },
        {"$match": {"count": {"$gte": _MIN_RUNS_TO_COMPACT}}},
        {"$sort": {"earliest_run": 1}},
        {"$limit": _BATCH_SIZE},
    ]

    try:
        results = await storage.collection.aggregate(pipeline).to_list(length=_BATCH_SIZE)
        return [r["_id"] for r in results]
    except Exception as e:
        logger.error(f"Failed to find sessions needing compaction: {e}")
        return []


async def _compact_session(session_id: str) -> bool:
    """
    合并单个 session 的所有已完成 runs 到一个 archived trace

    1. 获取该 session 所有已完成、非 archived 的 traces
    2. 合并事件，过滤 metadata 类型
    3. 创建 archived trace
    4. 标记原始 traces 为 archived
    """
    storage = get_trace_storage()
    now = _utc_now()

    # 获取所有已完成、非 archived 的 traces（包含完整 events）
    match_query: Dict[str, Any] = {
        "session_id": session_id,
        "status": {"$ne": "running"},
        "archived": {"$ne": True},
    }

    cursor = storage.collection.find(match_query).sort("started_at", 1)
    raw_traces = await cursor.to_list(length=200)

    if len(raw_traces) < _MIN_RUNS_TO_COMPACT:
        return False

    # 合并所有事件
    all_events: List[Dict[str, Any]] = []
    trace_ids: List[str] = []
    total_event_count = 0
    run_ids_archived: List[str] = []
    first_started_at = now

    for trace in raw_traces:
        trace_id = trace.get("trace_id", "")
        trace_ids.append(trace_id)
        total_event_count += trace.get("event_count", 0)

        if trace.get("started_at") and trace["started_at"] < first_started_at:
            first_started_at = trace["started_at"]

        run_id = trace.get("run_id", "")
        if run_id:
            run_ids_archived.append(run_id)

        events = trace.get("events", [])
        for event in events:
            all_events.append(
                {
                    "event_type": event.get("event_type"),
                    "data": event.get("data"),
                    "timestamp": event.get("timestamp"),
                    "run_id": run_id,
                }
            )

    # 过滤 metadata 事件
    filtered_events = _filter_events(all_events)

    if not filtered_events:
        # 没有内容事件，直接标记为 archived
        pass

    # 创建 archived trace
    archived_trace_id = f"archived_{session_id}"
    archived_doc: Dict[str, Any] = {
        "trace_id": archived_trace_id,
        "session_id": session_id,
        "agent_id": None,
        "run_id": None,
        "user_id": raw_traces[0].get("user_id") if raw_traces else None,
        "events": filtered_events,
        "event_count": len(filtered_events),
        "started_at": first_started_at,
        "updated_at": now,
        "completed_at": now,
        "status": "archived",
        "metadata": {
            "archived_from": trace_ids,
            "archived_run_ids": run_ids_archived,
            "original_event_count": total_event_count,
        },
        "archived": True,
    }

    try:
        # 使用 upsert 创建/更新 archived trace
        await storage.collection.update_one(
            {"trace_id": archived_trace_id},
            {
                "$set": archived_doc,
                "$setOnInsert": archived_doc,
            },
            upsert=True,
        )

        # 标记原始 traces 为已归档
        await storage.collection.update_many(
            {"trace_id": {"$in": trace_ids}},
            {
                "$set": {
                    "archived": True,
                    "archived_at": now,
                    "archived_into": archived_trace_id,
                }
            },
        )

        logger.info(
            f"Compacted session {session_id}: "
            f"{len(raw_traces)} traces -> 1 archived trace, "
            f"{total_event_count} -> {len(filtered_events)} events"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to compact session {session_id}: {e}")
        return False


async def run_compaction() -> int:
    """
    执行一次事件合并

    Returns:
        成功合并的 session 数量
    """
    if not await _acquire_lock():
        logger.debug("Compaction already running, skipping")
        return 0

    try:
        sessions = await _get_sessions_needing_compaction()
        if not sessions:
            logger.debug("No sessions need compaction")
            return 0

        logger.info(f"Found {len(sessions)} sessions to compact")
        compacted = 0

        for i, session_id in enumerate(sessions):
            try:
                if await _compact_session(session_id):
                    compacted += 1

                # 每处理 10 个 session 刷新一次锁
                if (i + 1) % 10 == 0:
                    await _refresh_lock()
            except Exception as e:
                logger.error(f"Error compacting session {session_id}: {e}")
                continue

        logger.info(f"Compaction completed: {compacted}/{len(sessions)} sessions")
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
            logger.error(f"Event compaction loop error: {e}")
            await asyncio.sleep(60)  # 出错后等待 1 分钟再重试
