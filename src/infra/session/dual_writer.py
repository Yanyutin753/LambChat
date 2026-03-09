"""
Dual Event Writer - 双写事件到 Redis Stream + MongoDB

所有事件按 trace_id 聚合到 MongoDB，大幅减少文档数量。
- Redis: 所有事件立即写入，保证 SSE 实时性
- MongoDB: 从 Redis 读取后批量写入（保证顺序）

写入流程:
1. 事件写入 Redis Stream（立即）
2. 记录 stream_key 到 buffer，追踪 Redis entry_id
3. 达到批量大小或延迟超时后触发 flush
4. flush 时从 Redis 读取新数据，按 Redis 顺序写入 MongoDB

读取流程（按 run 顺序合并）:
1. 按 started_at 获取所有 traces
2. 每个 trace 内的 events 保持 Redis 写入顺序
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.infra.session.trace_storage import TraceStorage, get_trace_storage
from src.infra.storage.redis import RedisStorage
from src.kernel.config import settings

logger = logging.getLogger(__name__)


# MongoDB 批量写入配置
_MONGO_FLUSH_INTERVAL = 1.0  # 每 1000ms 刷新一次
_MONGO_BATCH_SIZE = 200  # 每 200 条立即刷新


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DualEventWriter:
    """
    双写事件到 Redis Stream + MongoDB

    - Redis: 所有事件立即写入，保证 SSE 实时性
    - MongoDB: 从 Redis 读取后批量写入（保证顺序）
    """

    def __init__(self):
        self._redis = None
        self._trace = None
        self._ttl_set_keys: set[str] = set()
        # MongoDB 批量写入缓冲（只记录 stream_key，flush 时从 Redis 读取）
        self._mongo_buffer: list[str] = []
        self._mongo_lock = asyncio.Lock()  # 保护 buffer 和 flush 操作
        self._flush_scheduled = False  # 是否已调度刷新
        # 追踪每个 stream 的最后读取位置，用于 flush 时从 Redis 读取
        self._stream_last_ids: dict[str, str] = {}  # stream_key -> last entry_id

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

        - Redis: 立即写入，保证 SSE 实时性
        - MongoDB: 记录 stream_key 触发延迟 flush，flush 时从 Redis 读取写入（保证顺序）
        """
        # 统一时间戳，确保 Redis 和 MongoDB 使用相同的时间
        timestamp = _utc_now()

        # ---- Redis 写入（立即） ----
        stream_key = self._stream_key(session_id, run_id)
        fields = {
            "event_type": event_type,
            "data": (json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)),
            "timestamp": timestamp.isoformat(),
            "trace_id": trace_id or "",
            "session_id": session_id,
            "run_id": run_id or "",
        }
        redis_entry_id = await self._write_to_redis_direct(stream_key, fields)
        redis_success = redis_entry_id is not None

        # ---- MongoDB 写入（记录触发条件，flush 时统一从 Redis 读取） ----
        if trace_id:
            should_flush_now = False
            async with self._mongo_lock:
                # 达到批量大小立即刷新
                if len(self._mongo_buffer) >= _MONGO_BATCH_SIZE:
                    should_flush_now = True
                else:
                    self._mongo_buffer.append(
                        stream_key
                    )  # 只记录 stream_key，触发 flush 时从 Redis 读取
                    # 调度延迟刷新（如果还没调度）
                    if not self._flush_scheduled:
                        self._flush_scheduled = True
                        asyncio.create_task(self._schedule_flush())

            if should_flush_now:
                await self._do_flush()

        return redis_success

    async def _schedule_flush(self) -> None:
        """调度延迟刷新"""
        try:
            await asyncio.sleep(_MONGO_FLUSH_INTERVAL)
        except asyncio.CancelledError:
            # 被取消时也要执行刷新，确保数据不丢失
            pass
        await self._do_flush()

    async def _do_flush(self) -> None:
        """实际执行批量写入 - 统一从 Redis 读取保证顺序"""
        async with self._mongo_lock:
            if not self._mongo_buffer and not self._stream_last_ids:
                self._flush_scheduled = False
                return

            # 收集需要 flush 的 stream_keys（去重）
            stream_keys = set(self._mongo_buffer)
            self._mongo_buffer = []
            self._flush_scheduled = False

        # 从每个 stream 读取新数据写入 MongoDB
        for stream_key in stream_keys:
            last_id = self._stream_last_ids.get(stream_key, "0")
            await self._flush_stream_to_mongo(stream_key, last_id)

    async def _flush_stream_to_mongo(self, stream_key: str, last_id: str) -> None:
        """从 Redis Stream 读取新数据写入 MongoDB（保证顺序）"""
        try:
            # 从 last_id 之后读取所有新数据
            if last_id == "0":
                entries = await self.redis.xrange(stream_key, min="-", max="+")
            else:
                # 从 last_id 的下一个开始读取
                entries = await self.redis.xrange(stream_key, min=f"({last_id}", max="+")

            if not entries:
                return

            # 按 trace_id 分组，保持 Redis 的顺序
            grouped: dict[str, list[dict]] = defaultdict(list)
            trace_context: dict[str, tuple[str, Optional[str]]] = {}
            new_last_id = last_id

            for entry_id, fields in entries:
                event_type = fields.get("event_type")
                data_str = fields.get("data", "{}")
                timestamp_str = fields.get("timestamp")
                trace_id = fields.get("trace_id") or ""
                session_id = fields.get("session_id", "")
                run_id = fields.get("run_id") or ""

                # 解析 data
                try:
                    data = json.loads(data_str) if isinstance(data_str, str) else data_str
                except json.JSONDecodeError:
                    data = data_str

                # 解析 timestamp
                timestamp = (
                    datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    if timestamp_str
                    else _utc_now()
                )

                if trace_id:
                    grouped[trace_id].append(
                        {
                            "event_type": event_type,
                            "data": data,
                            "timestamp": timestamp,
                        }
                    )
                    if trace_id not in trace_context:
                        trace_context[trace_id] = (session_id, run_id)

                new_last_id = entry_id

            # 更新 last_id
            self._stream_last_ids[stream_key] = new_last_id

            # 批量写入 MongoDB
            for trace_id, events in grouped.items():
                try:
                    session_id, run_id = trace_context.get(trace_id, ("", None))
                    await self.trace.collection.update_one(
                        {"trace_id": trace_id},
                        {
                            "$push": {"events": {"$each": events}},
                            "$inc": {"event_count": len(events)},
                            "$set": {"updated_at": _utc_now()},
                            "$setOnInsert": {
                                "session_id": session_id,
                                "run_id": run_id or "",
                                "status": "running",
                                "started_at": _utc_now(),
                            },
                        },
                        upsert=True,
                    )
                except Exception as e:
                    logger.warning(f"Failed to write {len(events)} events to trace {trace_id}: {e}")

        except Exception as e:
            logger.warning(f"Failed to flush stream {stream_key}: {e}")

    async def flush_mongo_buffer(self) -> None:
        """强制刷新缓冲（外部调用）"""
        await self._do_flush()

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
        # 先刷新 Redis 缓冲，确保所有事件都已写入 MongoDB
        await self._do_flush()
        return await self.trace.complete_trace(trace_id, status, metadata)

    async def _write_to_redis_direct(
        self,
        stream_key: str,
        fields: Dict[str, str],
    ) -> Optional[str]:
        """
        单条立即写入 Redis Stream（用于流式事件，保证实时性）

        Args:
            stream_key: Redis Stream key
            fields: 已序列化的字段 dict

        Returns:
            写入的 entry_id，失败返回 None
        """
        try:
            entry_id = await self.redis.xadd(stream_key, fields)

            # 追踪 stream 的最后位置，用于 flush
            self._stream_last_ids[stream_key] = entry_id

            if stream_key not in self._ttl_set_keys:
                ttl = await self.redis.ttl(stream_key)
                if ttl == -1:
                    await self.redis.expire(stream_key, settings.SSE_CACHE_TTL)
                self._ttl_set_keys.add(stream_key)
            return entry_id
        except Exception as e:
            logger.warning(f"Redis xadd failed (streaming event): {e}")
            return None

    async def read_from_redis(
        self,
        session_id: str,
        run_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        从 Redis Stream 读取事件（阻塞读取，直到流结束）

        Args:
            session_id: 会话 ID
            run_id: 运行 ID（用于隔离多轮对话）

        Yields:
            事件字典，包含 id, event_type, data
        """
        stream_key = self._stream_key(session_id, run_id)
        last_id = "0"
        block = 500  # 500ms 阻塞超时
        logger.info(f"[Redis] Reading from stream: {stream_key}")

        def parse_data(data_str):
            if isinstance(data_str, str):
                try:
                    return json.loads(data_str)
                except json.JSONDecodeError:
                    return data_str
            return data_str

        try:
            entries = await self.redis.xrange(
                stream_key,
                min="-",
                max="+",
            )
            logger.info(f"[Redis] Initial xrange returned {len(entries)} entries from {stream_key}")
            for entry_id, fields in entries:
                event = {
                    "id": entry_id,
                    "event_type": fields.get("event_type"),
                    "data": parse_data(fields.get("data", "{}")),
                    "timestamp": fields.get("timestamp"),
                }
                yield event
                last_id = entry_id
                if event["event_type"] in ("complete", "error", "done"):
                    return

            logger.info(f"[Redis] Entering blocking xread loop for {stream_key}")
            while True:
                try:
                    results = await self.redis.xread(
                        {stream_key: last_id},
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
                                    "data": parse_data(fields.get("data", "{}")),
                                    "timestamp": fields.get("timestamp"),
                                }
                                yield event
                                last_id = entry_id
                                if event["event_type"] in (
                                    "complete",
                                    "error",
                                    "done",
                                ):
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
    ) -> List[Dict[str, Any]]:
        """获取 trace 的事件列表"""
        return await self.trace.get_trace_events(trace_id, event_types)

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
    ) -> List[Dict[str, Any]]:
        """
        从 MongoDB 读取会话的所有事件（跨 traces 聚合）

        Args:
            session_id: 会话 ID
            event_types: 可选的事件类型过滤
            run_id: 可选的运行 ID 过滤（用于隔离多轮对话）
            exclude_run_id: 可选的运行 ID 排除（用于排除正在运行的 run）
            completed_only: 是否只返回完成的 trace 中的事件（默认 True）

        Returns:
            事件列表
        """
        return await self.trace.get_session_events(
            session_id,
            event_types,
            run_id=run_id,
            exclude_run_id=exclude_run_id,
            completed_only=completed_only,
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


# Singleton instance
_dual_writer: Optional[DualEventWriter] = None


def get_dual_writer() -> DualEventWriter:
    """获取 DualEventWriter 单例"""
    global _dual_writer
    if _dual_writer is None:
        _dual_writer = DualEventWriter()
    return _dual_writer
