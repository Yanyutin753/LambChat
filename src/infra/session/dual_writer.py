"""
Dual Event Writer - 双写事件到 Redis Stream + MongoDB

所有事件按 trace_id 聚合到 MongoDB，大幅减少文档数量。
- Redis: 所有事件立即写入，保证 SSE 实时性
- MongoDB: 批量缓冲写入，确保数据不丢失

性能优化:
- 使用 bulk_write 批量更新 MongoDB，减少 DB 往返
- 分离 Redis/Mongo 锁，减少锁竞争
- 使用 asyncio.Event 替代轮询标志
"""

import asyncio
import json
import time
from collections import OrderedDict, defaultdict
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.session.trace_storage import TraceStorage, get_trace_storage
from src.infra.storage.redis import RedisStorage
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

logger = get_logger(__name__)


# MongoDB 批量写入配置
_MONGO_FLUSH_INTERVAL = 1.0  # 每 1000ms 刷新一次
_MONGO_BATCH_SIZE = 200  # 每 200 条立即刷新
_MONGO_BUFFER_MAX = 10000  # buffer 上限，防止 MongoDB 慢/宕机时 OOM
_TTL_SET_KEYS_MAX = 5000  # _ttl_set_keys 上限，防止内存泄漏
_LIVE_STREAM_READ_TIMEOUT_SECONDS = 24 * 60 * 60
_SSE_HEARTBEAT_INTERVAL_SECONDS = 15
_REDIS_XREAD_BLOCK_MS = 5000
_REDIS_REPLAY_BATCH_SIZE = 500
MongoBufferItem = tuple[Any, ...]


def _get_max_events_per_trace() -> int:
    """获取单个 trace 最多保留的事件数（可配置）"""
    return getattr(settings, "SESSION_MAX_EVENTS_PER_TRACE", 50000)


def _get_mongo_buffer_max() -> int:
    return max(int(getattr(settings, "SESSION_EVENT_MONGO_BUFFER_MAX", _MONGO_BUFFER_MAX) or 0), 1)


def _get_ttl_set_keys_max() -> int:
    return max(int(getattr(settings, "SESSION_EVENT_TTL_CACHE_MAX", _TTL_SET_KEYS_MAX) or 0), 1)


def _get_ttl_refresh_interval() -> float:
    ttl_seconds = max(int(getattr(settings, "SSE_CACHE_TTL", 86400) or 0), 1)
    return max(min(ttl_seconds / 2, 300.0), 1.0)


def _get_redis_replay_batch_size() -> int:
    return max(
        int(
            getattr(settings, "SESSION_EVENT_REDIS_REPLAY_BATCH_SIZE", _REDIS_REPLAY_BATCH_SIZE)
            or 0
        ),
        1,
    )


async def _serialize_event_data_for_redis(data: Any) -> str:
    if isinstance(data, dict):
        return await run_blocking_io(json.dumps, data, ensure_ascii=False)
    return str(data)


async def _parse_event_data_from_redis(data: Any) -> Any:
    if isinstance(data, str):
        try:
            return await run_blocking_io(json.loads, data)
        except json.JSONDecodeError:
            return data
    return data


def _is_cancel_error_event(event: dict[str, Any]) -> bool:
    if event.get("event_type") != "error":
        return False
    data = event.get("data")
    if not isinstance(data, dict):
        return False
    return data.get("type") in {"CancelledError", "TaskInterruptedError"}


def _should_stop_stream_on_event(event: dict[str, Any]) -> bool:
    event_type = event.get("event_type")
    if event_type in ("complete", "done"):
        return True
    if event_type == "error":
        return not _is_cancel_error_event(event)
    return False


def _build_mongo_bulk_operations(
    batch: list[MongoBufferItem],
    *,
    now: datetime,
    max_events: int,
) -> list[UpdateOne]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    trace_context: dict[str, tuple[str, Optional[str]]] = {}

    for item in batch:
        if _buffer_item_skip_legacy(item):
            continue
        trace_id, event_type, data, session_id, run_id, timestamp = _buffer_item_base(item)
        grouped[trace_id].append(
            {
                "event_type": event_type,
                "data": data,
                "timestamp": timestamp,
            }
        )
        if trace_id not in trace_context:
            trace_context[trace_id] = (session_id, run_id)

    operations: list[UpdateOne] = []
    for trace_id, events in grouped.items():
        session_id, run_id = trace_context.get(trace_id, ("", None))
        operations.append(
            UpdateOne(
                {"trace_id": trace_id},
                {
                    "$push": {
                        "events": {
                            "$each": events,
                            "$slice": -max_events,
                        }
                    },
                    "$inc": {"event_count": len(events)},
                    "$set": {"updated_at": now},
                    "$setOnInsert": {
                        "session_id": session_id,
                        "run_id": run_id or "",
                        "status": "running",
                        "started_at": now,
                    },
                },
                upsert=True,
            )
        )
    return operations


def _buffer_item_base(
    item: MongoBufferItem,
) -> tuple[str, str, dict, str, Optional[str], datetime]:
    trace_id, event_type, data, session_id, run_id, timestamp = item[:6]
    return trace_id, event_type, data, session_id, run_id, timestamp


def _buffer_item_reserved_start_seq(item: MongoBufferItem) -> int | None:
    if len(item) < 7 or item[6] is None:
        return None
    return int(item[6])


def _buffer_item_skip_legacy(item: MongoBufferItem) -> bool:
    return bool(len(item) >= 8 and item[7])


def _buffer_item_skip_chunk(item: MongoBufferItem) -> bool:
    return bool(len(item) >= 9 and item[8])


def _with_chunk_retry_metadata(
    item: MongoBufferItem,
    *,
    reserved_start_seq: int,
    skip_legacy: bool,
    skip_chunk: bool = False,
) -> MongoBufferItem:
    base = (*_buffer_item_base(item), reserved_start_seq, skip_legacy)
    if skip_chunk:
        return (*base, True)
    return base


def _group_mongo_buffer_events(
    batch: list[MongoBufferItem],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in batch:
        trace_id, event_type, data, _session_id, _run_id, timestamp = _buffer_item_base(item)
        grouped[trace_id].append(
            {
                "event_type": event_type,
                "data": data,
                "timestamp": timestamp,
            }
        )
    return grouped


def _operation_trace_id(operation: Any) -> str | None:
    try:
        return operation._filter.get("trace_id")  # type: ignore[attr-defined]
    except AttributeError:
        return None


def _failed_bulk_write_trace_ids(
    error: BulkWriteError,
    operations: list[UpdateOne],
) -> set[str] | None:
    failed_trace_ids: set[str] = set()
    for write_error in error.details.get("writeErrors", []) or []:
        try:
            index = int(write_error.get("index"))
        except (TypeError, ValueError):
            return None
        if index < 0 or index >= len(operations):
            return None
        trace_id = _operation_trace_id(operations[index])
        if trace_id is None:
            return None
        failed_trace_ids.add(trace_id)
    return failed_trace_ids or None


def _iter_chunk_write_groups(
    batch: list[MongoBufferItem],
) -> list[tuple[str, list[MongoBufferItem], list[dict[str, Any]], int | None]]:
    groups: list[tuple[str, list[MongoBufferItem], list[dict[str, Any]], int | None]] = []
    current_trace_id: str | None = None
    current_reserved_start_seq: int | None = None
    current_items: list[MongoBufferItem] = []
    current_events: list[dict[str, Any]] = []

    def flush_current() -> None:
        nonlocal current_trace_id, current_reserved_start_seq, current_items, current_events
        if current_trace_id is not None and current_items:
            groups.append(
                (
                    current_trace_id,
                    current_items,
                    current_events,
                    current_reserved_start_seq,
                )
            )
        current_trace_id = None
        current_reserved_start_seq = None
        current_items = []
        current_events = []

    for item in batch:
        if _buffer_item_skip_chunk(item):
            continue
        trace_id, event_type, data, _session_id, _run_id, timestamp = _buffer_item_base(item)
        reserved_start_seq = _buffer_item_reserved_start_seq(item)
        if current_items and (
            trace_id != current_trace_id or reserved_start_seq != current_reserved_start_seq
        ):
            flush_current()
        current_trace_id = trace_id
        current_reserved_start_seq = reserved_start_seq
        current_items.append(item)
        current_events.append(
            {
                "event_type": event_type,
                "data": data,
                "timestamp": timestamp,
            }
        )
    flush_current()
    return groups


class DualEventWriter:
    """
    双写事件到 Redis Stream + MongoDB (Trace 模式)

    - Redis: 所有事件立即写入，保证 SSE 实时性
    - MongoDB: 批量缓冲写入，使用 Lock 保护，确保数据不丢失

    性能优化:
    - Redis 和 MongoDB 操作使用不同的锁，减少争用
    - 使用 asyncio.Event 替代轮询标志，避免 busy wait
    - 使用 bulk_write 批量更新 MongoDB
    """

    def __init__(self):
        self._redis = None
        self._trace = None
        self._ttl_set_keys: OrderedDict[str, float] = OrderedDict()
        # MongoDB 批量写入缓冲
        # (trace_id, event_type, data, session_id, run_id, timestamp)
        self._mongo_buffer: list[MongoBufferItem] = []
        self._mongo_lock = asyncio.Lock()  # 只保护 buffer 和 flush 操作
        self._flush_event = asyncio.Event()  # 使用 Event 替代轮询标志
        self._flush_event.set()  # 初始状态为已就绪
        self._flush_task: asyncio.Task[None] | None = None
        self._flush_task_waiting = False
        self._mongo_buffer_dropped_total = 0
        self._mongo_buffer_last_drop: dict[str, Any] | None = None

    @property
    def redis(self) -> RedisStorage:
        if self._redis is None:
            self._redis = RedisStorage()
        return self._redis

    @property
    def trace(self) -> TraceStorage:
        if self._trace is None:
            self._trace = get_trace_storage()
        return self._trace

    def _stream_key(self, session_id: str, run_id: Optional[str] = None) -> str:
        if run_id:
            return f"session:{session_id}:run:{run_id}:events"
        return f"session:{session_id}:events"

    async def create_trace(
        self,
        trace_id: str,
        session_id: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return await self.trace.create_trace(
            trace_id=trace_id,
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            user_id=user_id,
            metadata=metadata,
        )

    async def write_event(
        self,
        session_id: str,
        event_type: str,
        data: Dict[str, Any],
        trace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> bool:
        """
        双写事件到 Redis + MongoDB

        - Redis: 立即写入（无锁）
        - MongoDB: 缓冲写入，批量刷新（使用 Event 触发）
        """
        # 统一时间戳，确保 Redis 和 MongoDB 使用相同的时间
        timestamp = utc_now()

        # ---- Redis 写入（立即，无锁） ----
        stream_key = self._stream_key(session_id, run_id)
        fields = {
            "event_type": event_type,
            "data": await _serialize_event_data_for_redis(data),
            "timestamp": timestamp.isoformat(),
        }
        redis_success = await self._write_to_redis_direct(stream_key, fields)

        # ---- MongoDB 写入（缓冲，使用 Event 触发） ----
        if trace_id:
            mongo_buffer_max = _get_mongo_buffer_max()
            async with self._mongo_lock:
                buffer_size = len(self._mongo_buffer)
            if buffer_size >= mongo_buffer_max:
                logger.warning(
                    "MongoDB event buffer reached %s entries; flushing before accepting more",
                    mongo_buffer_max,
                )
                await self.flush_mongo_buffer()

            should_flush_now = False
            buffer_size = 0
            async with self._mongo_lock:
                buffer_size = len(self._mongo_buffer)
                # 当缓冲区达到 80% 时发出警告
                if buffer_size >= int(mongo_buffer_max * 0.8):
                    logger.warning(
                        f"MongoDB buffer at {buffer_size}/{mongo_buffer_max} ({buffer_size * 100 // mongo_buffer_max}%). "
                        f"Consider checking MongoDB performance."
                    )
                self._mongo_buffer.append(
                    (trace_id, event_type, data, session_id, run_id, timestamp)
                )
                # 达到批量大小立即刷新
                if len(self._mongo_buffer) >= _MONGO_BATCH_SIZE:
                    should_flush_now = True
                # 使用 Event 触发延迟刷新
                elif self._flush_event.is_set():
                    self._flush_event.clear()
                    self._flush_task = asyncio.create_task(self._schedule_flush())
                    self._flush_task.add_done_callback(self._on_flush_task_done)

            if should_flush_now:
                await self.flush_mongo_buffer()
            elif event_type in ("complete", "error", "done"):
                await self.flush_mongo_buffer()

        return redis_success

    def get_diagnostics(self) -> dict[str, Any]:
        """Return lightweight writer diagnostics for health checks and tests."""
        return {
            "mongo_buffer_size": len(self._mongo_buffer),
            "mongo_buffer_max": _get_mongo_buffer_max(),
            "mongo_buffer_dropped_total": self._mongo_buffer_dropped_total,
            "mongo_buffer_last_drop": self._mongo_buffer_last_drop,
            "ttl_tracked_streams": len(self._ttl_set_keys),
        }

    def _on_flush_task_done(self, task: asyncio.Task[None]) -> None:
        if self._flush_task is task:
            self._flush_task = None
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.warning("Scheduled MongoDB event flush failed: %s", exc)

    async def _schedule_flush(self) -> None:
        """调度延迟刷新"""
        try:
            self._flush_task_waiting = True
            await asyncio.sleep(_MONGO_FLUSH_INTERVAL)
        finally:
            self._flush_task_waiting = False
        await self._do_flush()

    async def _drain_scheduled_flush_task(self) -> bool:
        task = self._flush_task
        if task is None:
            return False
        if task is asyncio.current_task():
            return False
        if task.done():
            if self._flush_task is task:
                self._flush_task = None
            return False

        if self._flush_task_waiting:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            if self._flush_task is task:
                self._flush_task = None
            return False

        try:
            await task
        except asyncio.CancelledError:
            return False
        except Exception as e:
            logger.warning("Scheduled MongoDB event flush failed while draining: %s", e)
            return False
        finally:
            if self._flush_task is task:
                self._flush_task = None
        return True

    async def _do_flush(self) -> None:
        """实际执行批量写入，使用 bulk_write 优化"""
        async with self._mongo_lock:
            if not self._mongo_buffer:
                self._flush_event.set()
                return

            batch = self._mongo_buffer
            self._mongo_buffer = []

        now = utc_now()
        max_events = _get_max_events_per_trace()
        chunk_storage_enabled = bool(
            getattr(settings, "SESSION_EVENT_CHUNK_STORAGE_ENABLED", False)
        )
        dual_write_legacy = bool(getattr(settings, "SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY", False))

        if chunk_storage_enabled:
            failed_chunk_items: list[MongoBufferItem] = []
            for trace_id, items, events, reserved_start_seq in _iter_chunk_write_groups(batch):
                trace_doc: dict[str, Any] | None = None
                start_seq = reserved_start_seq
                try:
                    if start_seq is None:
                        trace_doc = await self.trace.reserve_event_sequence_range(
                            trace_id,
                            len(events),
                        )
                        if not trace_doc:
                            logger.warning(
                                "Chunk write skipped because trace %s was not found", trace_id
                            )
                            failed_chunk_items.extend(items)
                            continue
                        start_seq = int(trace_doc.get("event_count", 0)) - len(events) + 1
                    else:
                        trace_doc = {
                            "trace_id": trace_id,
                            "session_id": items[0][3],
                            "run_id": items[0][4],
                        }
                    await self.trace.append_events_to_chunks(trace_doc, events, start_seq)
                except Exception as e:
                    if start_seq is not None:
                        failed_chunk_items.extend(
                            _with_chunk_retry_metadata(
                                item,
                                reserved_start_seq=start_seq + offset,
                                skip_legacy=dual_write_legacy or _buffer_item_skip_legacy(item),
                            )
                            for offset, item in enumerate(items)
                        )
                    else:
                        failed_chunk_items.extend(items)
                    logger.warning(
                        "Chunk write failed for trace %s with %s events: %s",
                        trace_id,
                        len(events),
                        e,
                    )

            if not dual_write_legacy:
                if failed_chunk_items:
                    async with self._mongo_lock:
                        self._mongo_buffer = failed_chunk_items + self._mongo_buffer
                self._flush_event.set()
                return
            if failed_chunk_items:
                async with self._mongo_lock:
                    self._mongo_buffer = failed_chunk_items + self._mongo_buffer

        operations = await run_blocking_io(
            _build_mongo_bulk_operations,
            batch,
            now=now,
            max_events=max_events,
        )

        # 批量执行
        if operations:
            try:
                result = await self.trace.collection.bulk_write(operations, ordered=False)
                logger.debug(
                    f"Bulk write: {result.modified_count} modified, {result.upserted_count} upserted"
                )
            except BulkWriteError as e:
                logger.warning(f"Bulk write failed: {e}")
                failed_trace_ids = _failed_bulk_write_trace_ids(e, operations)
                if failed_trace_ids is None:
                    retry_source_items = batch
                else:
                    retry_source_items = [
                        item for item in batch if _buffer_item_base(item)[0] in failed_trace_ids
                    ]
                if chunk_storage_enabled and dual_write_legacy:
                    retry_items = [
                        _with_chunk_retry_metadata(
                            item,
                            reserved_start_seq=_buffer_item_reserved_start_seq(item) or 0,
                            skip_legacy=False,
                            skip_chunk=True,
                        )
                        for item in retry_source_items
                        if not _buffer_item_skip_legacy(item)
                    ]
                else:
                    retry_items = retry_source_items
                async with self._mongo_lock:
                    self._mongo_buffer = retry_items + self._mongo_buffer
            except Exception as e:
                logger.warning(f"Bulk write failed: {e}")
                if chunk_storage_enabled and dual_write_legacy:
                    retry_items = [
                        _with_chunk_retry_metadata(
                            item,
                            reserved_start_seq=_buffer_item_reserved_start_seq(item) or 0,
                            skip_legacy=False,
                            skip_chunk=True,
                        )
                        for item in batch
                        if not _buffer_item_skip_legacy(item)
                    ]
                else:
                    retry_items = batch
                async with self._mongo_lock:
                    self._mongo_buffer = retry_items + self._mongo_buffer

        # 标记完成，允许下次刷新
        self._flush_event.set()

    async def flush_mongo_buffer(self, *, require_empty: bool = False) -> None:
        """强制刷新缓冲（外部调用）"""
        flushed_by_scheduled_task = await self._drain_scheduled_flush_task()
        if not flushed_by_scheduled_task:
            await self._do_flush()
        if require_empty:
            async with self._mongo_lock:
                remaining = len(self._mongo_buffer)
            if remaining:
                raise RuntimeError(f"MongoDB event buffer still has {remaining} pending events")

    async def _flush_redis_buffer(self) -> None:
        """保留兼容性"""
        pass

    async def complete_trace(
        self,
        trace_id: str,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        标记 trace 完成

        Args:
            trace_id: Trace ID
            status: 最终状态 (completed/error)
            metadata: 额外元数据

        Returns:
            是否更新成功
        """
        return await self.trace.complete_trace(trace_id, status, metadata)

    async def _write_to_redis_direct(
        self,
        stream_key: str,
        fields: Dict[str, str],
    ) -> bool:
        """
        单条立即写入 Redis Stream（用于流式事件，保证实时性）

        Args:
            stream_key: Redis Stream key
            fields: 已序列化的字段 dict

        Returns:
            是否写入成功
        """
        try:
            await self.redis.xadd(
                stream_key,
                fields,
            )

            now = time.monotonic()
            next_ttl_refresh_at = self._ttl_set_keys.get(stream_key)
            if next_ttl_refresh_at is None:
                ttl = await self.redis.ttl(stream_key)
                if ttl == -1:
                    await self.redis.expire(stream_key, settings.SSE_CACHE_TTL)
                self._ttl_set_keys[stream_key] = now + _get_ttl_refresh_interval()
            elif now >= next_ttl_refresh_at:
                await self.redis.expire(stream_key, settings.SSE_CACHE_TTL)
                self._ttl_set_keys[stream_key] = now + _get_ttl_refresh_interval()
            else:
                self._ttl_set_keys.move_to_end(stream_key)

            if next_ttl_refresh_at is None or now >= next_ttl_refresh_at:
                self._ttl_set_keys.move_to_end(stream_key)
                # LRU eviction
                while len(self._ttl_set_keys) > _get_ttl_set_keys_max():
                    self._ttl_set_keys.popitem(last=False)
            return True
        except Exception as e:
            logger.warning(f"Redis xadd failed (streaming event): {e}")
            return False

    async def read_from_redis(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        overall_timeout: float = _LIVE_STREAM_READ_TIMEOUT_SECONDS,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        从 Redis Stream 读取事件（阻塞读取，直到流结束）

        通过定期发送 SSE 心跳注释检测客户端断开，避免僵尸连接占用资源。
        SSE 注释（以 : 开头的行）会被 EventSource 客户端自动忽略。

        Args:
            session_id: 会话 ID
            run_id: 运行 ID（用于隔离多轮对话）
            overall_timeout: 整体超时（秒），默认 24 小时，防止无限等待

        Yields:
            事件字典，包含 id, event_type, data
            心跳事件: event_type="heartbeat"（用于检测死连接）
        """
        stream_key = self._stream_key(session_id, run_id)
        last_id = "0"
        block = _REDIS_XREAD_BLOCK_MS
        heartbeat_interval = _SSE_HEARTBEAT_INTERVAL_SECONDS
        start_time = asyncio.get_event_loop().time()
        last_heartbeat = start_time
        logger.info(f"[Redis] Reading from stream: {stream_key}")

        try:
            replay_min = "-"
            replay_batch_size = _get_redis_replay_batch_size()
            replayed_count = 0
            while True:
                entries = await self.redis.xrange(
                    stream_key,
                    min=replay_min,
                    max="+",
                    count=replay_batch_size,
                )
                if not entries:
                    break
                replayed_count += len(entries)
                logger.debug(
                    "[Redis] Initial xrange replayed %d entries from %s",
                    len(entries),
                    stream_key,
                )
                for entry_id, fields in entries:
                    event = {
                        "id": entry_id,
                        "event_type": fields.get("event_type"),
                        "data": await _parse_event_data_from_redis(fields.get("data", "{}")),
                        "timestamp": fields.get("timestamp"),
                    }
                    yield event
                    last_id = entry_id
                    if _should_stop_stream_on_event(event):
                        return
                replay_min = f"({last_id}"
                if len(entries) < replay_batch_size:
                    break
            logger.info(
                f"[Redis] Initial xrange replayed {replayed_count} entries from {stream_key}"
            )

            logger.info(f"[Redis] Entering blocking xread loop for {stream_key}")
            while True:
                now = asyncio.get_event_loop().time()

                # 整体超时检查，防止 producer 崩溃导致无限等待
                elapsed = now - start_time
                if elapsed >= overall_timeout:
                    logger.warning(
                        f"[Redis] SSE read timed out after {overall_timeout}s for {stream_key}"
                    )
                    yield {
                        "id": "timeout",
                        "event_type": "error",
                        "data": {"error": "Stream read timed out"},
                        "timestamp": utc_now().isoformat(),
                    }
                    return

                # 心跳检测：定期 yield，如果客户端已断开，FastAPI 会在写入时
                # 抛出 CancelledError，从而提前释放资源
                if now - last_heartbeat >= heartbeat_interval:
                    last_heartbeat = now
                    yield {
                        "id": "heartbeat",
                        "event_type": "heartbeat",
                        "data": {},
                        "timestamp": utc_now().isoformat(),
                    }

                try:
                    results = await self.redis.xread(
                        {stream_key: last_id},
                        count=replay_batch_size,
                        block=block,
                    )
                    if results:
                        logger.debug(
                            f"[Redis] xread returned {len(results)} results from {stream_key}"
                        )
                        for _, entries in results:
                            for entry_id, fields in entries:
                                event = {
                                    "id": entry_id,
                                    "event_type": fields.get("event_type"),
                                    "data": await _parse_event_data_from_redis(
                                        fields.get("data", "{}")
                                    ),
                                    "timestamp": fields.get("timestamp"),
                                }
                                yield event
                                last_id = entry_id
                                if _should_stop_stream_on_event(event):
                                    return
                except Exception as xread_error:
                    logger.warning(f"xread failed (non-fatal): {xread_error}")
                    await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Redis read failed: {e}")
            return

    async def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """获取完整的 trace"""
        return await self.trace.get_trace(trace_id)

    async def get_trace_events(
        self,
        trace_id: str,
        event_types: Optional[List[str]] = None,
        max_events: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """获取 trace 的事件列表"""
        return await self.trace.get_trace_events(trace_id, event_types, max_events=max_events)

    async def list_traces(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """列出 traces"""
        return await self.trace.list_traces(
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            status=status,
            limit=limit,
            skip=skip,
        )

    async def read_session_events(
        self,
        session_id: str,
        event_types: Optional[List[str]] = None,
        run_id: Optional[str] = None,
        exclude_run_id: Optional[str] = None,
        completed_only: bool = True,
        run_ids: Optional[List[str]] = None,
        max_events: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        从 MongoDB 读取会话的所有事件（跨 traces 聚合）

        Args:
            session_id: 会话 ID
            event_types: 可选的事件类型过滤
            run_id: 可选的运行 ID 过滤（用于隔离多轮对话）
            exclude_run_id: 可选的运行 ID 排除（用于排除正在运行的 run）
            completed_only: 是否只返回完成的 trace 中的事件（默认 True）
            run_ids: 可选的运行 ID 列表过滤
            max_events: 可选的最大返回事件数

        Returns:
            事件列表
        """
        return await self.trace.get_session_events(
            session_id,
            event_types,
            run_id=run_id,
            exclude_run_id=exclude_run_id,
            completed_only=completed_only,
            run_ids=run_ids,
            max_events=max_events,
        )

    async def get_stream_length(self, session_id: str, run_id: Optional[str] = None) -> int:
        """
        获取 Redis Stream 长度

        Args:
            session_id: 会话 ID
            run_id: 运行 ID（可选）
        """
        stream_key = self._stream_key(session_id, run_id)
        try:
            return await self.redis.xlen(stream_key)
        except Exception:
            return 0

    async def clear_stream(self, session_id: str, run_id: Optional[str] = None) -> None:
        """
        清除 Redis Stream

        Args:
            session_id: 会话 ID
            run_id: 运行 ID（可选）
        """
        stream_key = self._stream_key(session_id, run_id)
        try:
            await self.redis.delete(stream_key)
        except Exception as e:
            logger.warning(f"Failed to clear stream: {e}")

    async def expire_stream(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        ttl_seconds: int = 60,
    ) -> bool:
        """
        Shorten Redis Stream TTL after a run reaches a terminal state.

        Keeping a short grace period avoids racing active SSE readers that still
        need the terminal event, while preventing completed runs from occupying
        Redis for the full live-stream TTL.
        """
        stream_key = self._stream_key(session_id, run_id)
        try:
            ttl = max(int(ttl_seconds), 1)
            success = await self.redis.expire(stream_key, ttl)
            self._ttl_set_keys.pop(stream_key, None)
            return bool(success)
        except Exception as e:
            logger.warning(f"Failed to expire stream: {e}")
            return False


# Singleton instance
_dual_writer: Optional[DualEventWriter] = None


def get_dual_writer() -> DualEventWriter:
    """获取 DualEventWriter 单例"""
    global _dual_writer
    if _dual_writer is None:
        _dual_writer = DualEventWriter()
    return _dual_writer


async def close_dual_writer() -> None:
    """Flush and release the DualEventWriter singleton without creating it."""
    global _dual_writer
    writer = _dual_writer
    _dual_writer = None
    if writer is not None:
        await writer.flush_mongo_buffer()
